"""The one-call site update used by the Refresh button, scripts/build_dashboard.py
and the scheduled GitHub Actions run (.github/workflows/site.yml)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src import config as cfg
from src.model import PredictorBundle, train_and_save
from src.predict import load_fixtures_from_csv
from src.prediction_log import append_predictions, load_log
from src.sync import sync_for_notebook
from src.web.data import build_dashboard
from src.web.render import ASSETS_DIR, render_html


def update_site(sync: bool = True, log: bool = True, pull: bool = False) -> str:
    """[git pull | sync] -> [retrain] -> predict -> [log] -> write dashboard/index.html.

    ``pull`` fetches the data the cloud run committed (cfg.CLOUD_SYNC mode);
    ``sync`` calls the API directly. Either one retrains. Never raises on API or
    git trouble; returns a short human-readable status for the console / toast.
    """
    lines = []
    if pull:
        lines.append(pull_latest())
    if sync:
        lines.append(sync_for_notebook())
    if sync or pull:
        cfg.LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
        cfg.LAST_SYNC_FILE.write_text(pd.Timestamp.now().isoformat(), encoding="utf-8")
    if sync or pull or not cfg.MODEL_FILE.exists():
        bundle = train_and_save()
    else:
        bundle = PredictorBundle.load()
    data, preds = build_dashboard(bundle)
    if log:
        append_predictions(preds)
    cfg.DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.DASHBOARD_FILE.write_text(render_html(data), encoding="utf-8")
    write_site_files(cfg.DASHBOARD_FILE.parent)
    lines.append(f"Dashboard written ({len(preds)} next-round prediction(s)).")
    return "\n".join(lines)


def write_site_files(out_dir: Path, mode: str | None = None) -> None:
    """Files the hosting serves next to index.html: share card, robots, sitemap.

    The live site invites search engines (robots.txt + sitemap.xml pointing at
    SITE_URL); preview builds forbid crawling, on top of their noindex header.
    """
    mode = mode or cfg.SITE_MODE
    shutil.copyfile(ASSETS_DIR / cfg.SHARE_CARD_FILE, out_dir / cfg.SHARE_CARD_FILE)
    if mode == "live":
        robots = f"User-agent: *\nAllow: /\nSitemap: {cfg.SITE_URL}/sitemap.xml\n"
    else:
        robots = "User-agent: *\nDisallow: /\n"
    (out_dir / "robots.txt").write_text(robots, encoding="utf-8")
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    (out_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{cfg.SITE_URL}/</loc><lastmod>{today}</lastmod>"
        "<changefreq>daily</changefreq></url>\n</urlset>\n",
        encoding="utf-8",
    )


def local_refresh_kwargs() -> dict[str, bool]:
    """What the desktop app's Refresh does: pull from the cloud, or sync itself."""
    if cfg.CLOUD_SYNC:
        return {"sync": False, "log": False, "pull": True}
    return {"sync": True, "log": True, "pull": False}


CLOUD_BRANCH = "main"  # where the scheduled cloud run commits its data


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cfg.PROJECT_ROOT, capture_output=True, text=True, timeout=60
    )


def _last_line(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    return lines[-1] if lines else "git error"


def pull_latest(attempts: int = 2) -> str:
    """Fast-forward to the data the cloud run committed. Never raises.

    ``fetch origin main`` + ``merge --ff-only origin/main`` instead of a bare
    ``git pull``: pull reads .git/FETCH_HEAD, which an editor's background
    auto-fetch (VS Code) can rewrite mid-pull ("Cannot fast-forward to
    multiple branches"). One retry covers any other transient failure. Only
    on the main branch: a feature branch must not silently absorb data commits.
    """
    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        if branch.returncode != 0:
            return "Pull: skipped — " + _last_line(branch)
        if branch.stdout.strip() != CLOUD_BRANCH:
            return f"Pull: skipped — on branch {branch.stdout.strip()!r}, not {CLOUD_BRANCH!r}"
        error = "git error"
        for _ in range(attempts):
            step = _git("fetch", "--quiet", "origin", CLOUD_BRANCH)
            if step.returncode == 0:
                step = _git("merge", "--ff-only", "--quiet", f"origin/{CLOUD_BRANCH}")
                if step.returncode == 0:
                    return "Pull: up to date with GitHub."
            error = _last_line(step)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Pull: skipped — {exc}"
    return "Pull: skipped — " + error


def sync_due(
    today: pd.Timestamp,
    fixture_dates: Iterable[pd.Timestamp],
    unlogged_dates: Iterable[pd.Timestamp],
) -> str | None:
    """Why the scheduled run should call the API today, or None to skip it.

    The free plan has 500 requests a month, so the daily cloud run only syncs
    when something can have changed: a fixture in the last few days (its result
    should be in), an upcoming game whose prediction isn't logged yet, or the
    weekly check that picks up reschedules and newly published fixtures.
    """
    today = today.normalize()
    if today.weekday() == cfg.SYNC_WEEKLY_WEEKDAY:
        return "weekly check"
    lookback = today - pd.Timedelta(days=cfg.SYNC_RESULTS_LOOKBACK_DAYS)
    if any(lookback <= d <= today for d in fixture_dates):
        return "results due"
    horizon = today + pd.Timedelta(days=cfg.SYNC_LOG_LOOKAHEAD_DAYS)
    if any(today < d <= horizon for d in unlogged_dates):
        return "upcoming game not logged yet"
    return None


def scheduled_sync_reason(today: pd.Timestamp | None = None) -> str | None:
    """sync_due() for the files on disk, with today in the league's time zone."""
    if today is None:
        today = pd.Timestamp.now(tz=cfg.SITE_TIMEZONE).tz_localize(None)
    fixtures, dates = load_fixtures_from_csv()
    logged = load_log()
    logged_keys = set(
        zip(
            pd.to_datetime(logged["fixture_date"], dayfirst=True),
            logged["home"],
            logged["away"],
            strict=True,
        )
    )
    unlogged = [
        d for f, d in zip(fixtures, dates, strict=True) if (d, f.home, f.away) not in logged_keys
    ]
    return sync_due(today, dates, unlogged)


def hours_since_last_sync() -> float:
    """Hours since update_site last synced or pulled (infinity if never)."""
    try:
        last = pd.Timestamp(cfg.LAST_SYNC_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return float("inf")
    return (pd.Timestamp.now() - last).total_seconds() / 3600
