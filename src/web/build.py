"""The one-call site update used by the Refresh button, scripts/build_dashboard.py
and the scheduled GitHub Actions run (.github/workflows/site.yml)."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable

import pandas as pd

from src import config as cfg
from src.model import PredictorBundle, train_and_save
from src.predict import load_fixtures_from_csv
from src.prediction_log import append_predictions, load_log
from src.sync import sync_for_notebook
from src.web.data import build_dashboard
from src.web.render import render_html


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
    lines.append(f"Dashboard written ({len(preds)} next-round prediction(s)).")
    return "\n".join(lines)


def local_refresh_kwargs() -> dict[str, bool]:
    """What the desktop app's Refresh does: pull from the cloud, or sync itself."""
    if cfg.CLOUD_SYNC:
        return {"sync": False, "log": False, "pull": True}
    return {"sync": True, "log": True, "pull": False}


def pull_latest() -> str:
    """``git pull --ff-only`` the data the cloud run committed. Never raises."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only", "--quiet"],
            cwd=cfg.PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Pull: skipped — {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return "Pull: skipped — " + (detail[-1] if detail else "git error")
    return "Pull: up to date with GitHub."


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
