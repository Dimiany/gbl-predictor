"""Static HTML dashboard — a single-file, client-side "website" for the predictor.

``build_dashboard()`` gathers every number into one JSON-able dict;
``render_html()`` wraps it in a page whose JavaScript renders the views
(Home, Predictions, Standings, Teams, Team page, Schedule, Model) with
hash routing, filters, sortable tables and hover tooltips. No server, no CDN:
open ``dashboard/index.html`` in any browser.

Every game shows the model's exact pre-game call (score + probability) next
to the real result: the logged prediction when one exists, otherwise the
walk-forward one (also out-of-sample — that model never saw the game).

Run it via ``python scripts/build_dashboard.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections import defaultdict

import pandas as pd
import requests

from src import config as cfg
from src.features import build_features, elo_update, season_of, team_state_snapshot
from src.model import PredictorBundle, train_and_save
from src.predict import Prediction, load_fixtures_from_csv, next_round, predict_fixtures
from src.prediction_log import RESCHEDULE_TOLERANCE_DAYS, append_predictions, build_accuracy_view
from src.sync import sync_for_notebook

# The team highlighted by default until the viewer picks their own.
DEFAULT_FOCUS_TEAM = "PAOK"


def _season_label(season: int) -> str:
    return f"{season}/{str(season + 1)[-2:]}"


def _num(x, nd: int = 3):
    """JSON-safe number: NaN/None -> None (JSON.parse rejects NaN)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, nd)


def _int(x):
    v = _num(x, 0)
    return None if v is None else int(v)


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------


def _standings(history: pd.DataFrame, season: int, elo: dict[str, float]) -> list[dict]:
    """League table for ``season``: same ordering rule as the model's rank feature."""
    games = history[history["_season"] == season].sort_values(cfg.COL_DATE, kind="stable")
    table: dict[str, dict] = defaultdict(
        lambda: {
            "gp": 0,
            "w": 0,
            "l": 0,
            "pf": 0,
            "pa": 0,
            "hw": 0,
            "hl": 0,
            "aw": 0,
            "al": 0,
            "form": [],
        }
    )
    for _, g in games.iterrows():
        hs, as_ = int(g[cfg.COL_HOME_SCORE]), int(g[cfg.COL_AWAY_SCORE])
        for team, scored, conceded, at_home in (
            (g[cfg.COL_HOME], hs, as_, True),
            (g[cfg.COL_AWAY], as_, hs, False),
        ):
            row = table[team]
            won = scored > conceded
            row["gp"] += 1
            row["w"] += int(won)
            row["l"] += int(not won)
            row["pf"] += scored
            row["pa"] += conceded
            row[("h" if at_home else "a") + ("w" if won else "l")] += 1
            row["form"].append("W" if won else "L")

    rows = []
    for team, r in table.items():
        streak = 0
        for res in reversed(r["form"]):
            if res != r["form"][-1]:
                break
            streak += 1
        rows.append(
            {
                "team": team,
                **r,
                "diff": r["pf"] - r["pa"],
                "pct": r["w"] / r["gp"] if r["gp"] else 0.0,
                "form": r["form"][-cfg.ROLLING_WINDOW :],
                "streak": f"{r['form'][-1]}{streak}" if r["form"] else "",
                "elo": round(elo.get(team, cfg.ELO_INITIAL)),
            }
        )
    rows.sort(key=lambda r: (-r["pct"], -r["diff"], r["team"]))
    for i, r in enumerate(rows, start=1):
        r["pos"] = i
    return rows


def _elo_history(history: pd.DataFrame) -> dict[str, list[list[list]]]:
    """Per team: one segment per season, each a list of [iso_date, elo] points.

    A segment opens with the pre-game rating of the team's first game that
    season (already regressed toward 1500) and then records the post-game
    rating after every game, so the chart can break the line over the summer.
    """
    feats = build_features(history)
    series: dict[str, list[list[list]]] = defaultdict(list)
    current_season: dict[str, int] = {}
    for _, g in feats.iterrows():
        date = g[cfg.COL_DATE]
        season = season_of(date)
        iso = date.strftime("%Y-%m-%d")
        home_pre, away_pre = float(g["home_elo_pre"]), float(g["away_elo_pre"])
        home_post, away_post = elo_update(home_pre, away_pre, int(g[cfg.COL_HOME_WIN]))
        for team, pre, post in (
            (g[cfg.COL_HOME], home_pre, home_post),
            (g[cfg.COL_AWAY], away_pre, away_post),
        ):
            if current_season.get(team) != season:
                current_season[team] = season
                series[team].append([[iso, round(pre, 1)]])
            series[team][-1].append([iso, round(post, 1)])
    return dict(series)


def _log_rows(log_view: pd.DataFrame) -> list[dict]:
    """Every logged prediction with its graded outcome (actuals None if pending)."""
    rows = []
    if log_view.empty:
        return rows
    for _, r in log_view.iterrows():
        d = pd.to_datetime(r["fixture_date"], dayfirst=True)
        played = pd.notna(r.get("actual_home_score"))
        rows.append(
            {
                "d": d.strftime("%Y-%m-%d"),
                "s": _season_label(season_of(d)),
                "home": r["home"],
                "away": r["away"],
                "phs": _int(r["predicted_home_score"]),
                "pas": _int(r["predicted_away_score"]),
                "p": _num(r["home_win_probability"]),
                "w": r["predicted_winner"],
                "v": r["model_version"],
                "at": str(r["prediction_made_at"]),
                "ahs": _int(r["actual_home_score"]) if played else None,
                "aas": _int(r["actual_away_score"]) if played else None,
                "ok": bool(r["winner_correct"]) if played else None,
            }
        )
    return rows


def _games(history: pd.DataFrame, log_rows: list[dict], walk_forward: pd.DataFrame) -> list[dict]:
    """All played games, newest first, each with the model's pre-game pick.

    Logged predictions win over walk-forward ones; a logged fixture matches a
    game with the same teams up to RESCHEDULE_TOLERANCE_DAYS apart.
    """
    logged: dict[tuple, list[dict]] = defaultdict(list)
    for r in log_rows:
        logged[(r["home"], r["away"])].append(r)
    wf: dict[tuple, dict] = {}
    if walk_forward is not None and not walk_forward.empty:
        for _, r in walk_forward.iterrows():
            date = pd.Timestamp(r[cfg.COL_DATE]).strftime("%Y-%m-%d")
            wf[(date, r[cfg.COL_HOME], r[cfg.COL_AWAY])] = {
                "src": "wf",
                "phs": _int(r["predicted_home_score"]),
                "pas": _int(r["predicted_away_score"]),
                "p": _num(r["home_win_probability"]),
                "w": r["predicted_winner"],
                "v": cfg.MODEL_VERSION,
            }

    out = []
    for _, g in history.sort_values(cfg.COL_DATE, ascending=False, kind="stable").iterrows():
        date = g[cfg.COL_DATE]
        iso = date.strftime("%Y-%m-%d")
        home, away = g[cfg.COL_HOME], g[cfg.COL_AWAY]
        pick = None
        best_gap = RESCHEDULE_TOLERANCE_DAYS + 1
        for r in logged.get((home, away), []):
            gap = abs((pd.Timestamp(r["d"]) - date).days)
            if gap < best_gap:
                best_gap = gap
                pick = {k: r[k] for k in ("phs", "pas", "p", "w", "v")} | {"src": "log"}
        if pick is None:
            pick = wf.get((iso, home, away))
        out.append(
            {
                "d": iso,
                "s": _season_label(int(g["_season"])),
                "home": home,
                "away": away,
                "hs": int(g[cfg.COL_HOME_SCORE]),
                "as": int(g[cfg.COL_AWAY_SCORE]),
                "pick": pick,
            }
        )
    return out


def _image_data_uri(url: str) -> str | None:
    """Download an image once (cached next to the dashboard) and inline it.

    Inlining keeps index.html a single self-contained file that works offline.
    Returns None if the image can't be fetched — the page then falls back to
    initials, so a CDN hiccup never breaks the build.
    """
    if not url:
        return None
    cache = cfg.DASHBOARD_FILE.parent / "assets" / (hashlib.sha1(url.encode()).hexdigest() + ".png")
    if not cache.exists():
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(resp.content)
    return "data:image/png;base64," + base64.b64encode(cache.read_bytes()).decode("ascii")


def _team_logos() -> dict[str, str]:
    """Canonical team name -> inlined crest, for every team with a known logo URL."""
    if not cfg.TEAM_LOGOS_CSV.exists():
        return {}
    logos = pd.read_csv(cfg.TEAM_LOGOS_CSV)
    out = {}
    for team, url in zip(logos["team"], logos["logo_url"], strict=True):
        uri = _image_data_uri(url)
        if uri:
            out[team] = uri
    return out


def _prediction_dict(p: Prediction, elo: dict[str, float]) -> dict:
    d = pd.to_datetime(p.date, dayfirst=True)
    return {
        "d": d.strftime("%Y-%m-%d"),
        "t": p.time,
        "home": p.home,
        "away": p.away,
        "phs": p.predicted_home_score,
        "pas": p.predicted_away_score,
        "margin": round(p.predicted_margin, 1),
        "p": round(p.home_win_probability, 3),
        "p_elo": round(p.home_win_probability_elo, 3),
        "band": round(p.score_uncertainty_pts),
        "w": p.winner,
        "v": p.model_version,
        "home_elo": round(elo.get(p.home, cfg.ELO_INITIAL)),
        "away_elo": round(elo.get(p.away, cfg.ELO_INITIAL)),
        "notes": p.adjustment_notes,
    }


def build_dashboard(
    bundle: PredictorBundle | None = None,
    history: pd.DataFrame | None = None,
) -> tuple[dict, list[Prediction]]:
    """Assemble every number the site shows. Returns (data, next-round predictions)."""
    if bundle is None:
        bundle = PredictorBundle.load()
    if history is None:
        history = pd.read_csv(cfg.RAW_GAMES_CSV)
    history = history.copy()
    history[cfg.COL_DATE] = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    history["_season"] = history[cfg.COL_DATE].map(season_of)

    fixtures, dates = load_fixtures_from_csv()
    round_fx, round_dates = next_round(fixtures, dates)
    season = int(history["_season"].max())
    if dates:
        season = max(season, season_of(min(dates)))

    states, _ = team_state_snapshot(history)
    elo = {t: s.elo for t, s in states.items() if s.season == season}

    preds = predict_fixtures(round_fx, round_dates, bundle=bundle) if round_fx else []
    next_keys = {(p.date, p.home, p.away): i for i, p in enumerate(preds)}
    log_rows = _log_rows(build_accuracy_view())
    standings = _standings(history, season, elo)
    m = bundle.metrics

    data = {
        "season": _season_label(season),
        "updated": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M"),
        "last_game": history[cfg.COL_DATE].max().strftime("%Y-%m-%d"),
        "focus": DEFAULT_FOCUS_TEAM
        if any(r["team"] == DEFAULT_FOCUS_TEAM for r in standings)
        else (standings[0]["team"] if standings else ""),
        "standings": standings,
        "games": _games(history, log_rows, bundle.test_predictions),
        "log": log_rows,
        "next": [_prediction_dict(p, elo) for p in preds],
        "upcoming": [
            {
                "d": d.strftime("%Y-%m-%d"),
                "t": f.time,
                "home": f.home,
                "away": f.away,
                "pi": next_keys.get((f.date, f.home, f.away), -1),
            }
            for f, d in zip(fixtures, dates, strict=True)
        ],
        "logos": _team_logos(),
        "league_logo": _image_data_uri(cfg.LEAGUE_LOGO_URL),
        "elo_history": _elo_history(history.drop(columns=["_season"])),
        "season_starts": sorted(
            history.groupby("_season")[cfg.COL_DATE].min().dt.strftime("%Y-%m-%d").tolist()
        ),
        "model": {
            "version": bundle.version,
            "sigma": _num(bundle.margin_sigma, 1),
            "n_test": _int(m.get("n_test")),
            "warmup": _int(m.get("n_train")),
            "acc": _num(m.get("accuracy")),
            "ll": _num(m.get("log_loss")),
            "brier": _num(m.get("brier_score")),
            "margin_mae": _num(m.get("margin_mae"), 1),
            "margin_r2": _num(m.get("margin_r2")),
            "total_mae": _num(m.get("total_mae"), 1),
            "elo_acc": _num(m.get("elo_baseline_accuracy")),
            "elo_ll": _num(m.get("elo_baseline_log_loss")),
            "elo_brier": _num(m.get("elo_baseline_brier")),
            "home_rate": _num(m.get("home_win_rate")),
            "coef": [round(float(c), 3) for c in bundle.margin_reg.coef_],
            "intercept": round(float(bundle.margin_reg.intercept_), 2),
        },
    }
    return data, preds


def update_site(sync: bool = True, log: bool = True) -> str:
    """The whole refresh in one call: [sync + retrain] -> predict -> [log] -> write page.

    Used by scripts/build_dashboard.py and by the Refresh button (scripts/serve.py).
    Never raises on API trouble (sync_for_notebook swallows it); returns a
    short human-readable status.
    """
    lines = []
    if sync or not cfg.MODEL_FILE.exists():
        if sync:
            lines.append(sync_for_notebook())
            cfg.LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            cfg.LAST_SYNC_FILE.write_text(pd.Timestamp.now().isoformat(), encoding="utf-8")
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


def hours_since_last_sync() -> float:
    """Hours since update_site last synced (infinity if never)."""
    try:
        last = pd.Timestamp(cfg.LAST_SYNC_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return float("inf")
    return (pd.Timestamp.now() - last).total_seconds() / 3600


# ---------------------------------------------------------------------------
# HTML shell
# ---------------------------------------------------------------------------


def render_html(d: dict) -> str:
    """Return the full single-file site."""
    payload = json.dumps(d, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="el">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GBL Predictor · {d["season"]}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="viz-root">
  <header class="site-head">
    <a class="brand" href="#/"><span class="brand-badge" id="brand-badge" aria-hidden="true"></span><span class="brand-text"><b>GBL Predictor</b><small id="brand-season"></small></span></a>
    <nav id="nav" aria-label="Κύρια πλοήγηση"></nav>
    <div class="head-tools">
      <button id="refresh" class="btn btn-primary" type="button" title="Φέρνει νέα αποτελέσματα και ξαναβγάζει τις προβλέψεις">⟳ Ανανέωση</button>
      <label class="focus-pick"><span>Η ομάδα μου</span><select id="focus"></select></label>
      <button id="theme" type="button" aria-label="Αλλαγή θέματος" title="Light / dark">◐</button>
    </div>
  </header>
  <main id="app" tabindex="-1"></main>
  <footer class="site-foot"><div class="foot-inner"><span class="foot-brand" id="foot-brand"></span><span id="foot"></span></div></footer>
</div>
<div id="tip" class="tip" role="tooltip" hidden></div>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
<script id="data" type="application/json">{payload}</script>
<script>{_JS}</script>
</body>
</html>"""


_CSS = """
.viz-root{color-scheme:light;
  --brand-navy:#0b1647;--brand-navy-2:#1a2d6f;--brand-blue:#0033ff;--brand-cyan:#3ebedf;
  --page:#f2f4f9;--surface-1:#ffffff;--surface-2:#f4f6fb;--text-primary:#0d1433;--text-secondary:#4a5272;--muted:#7c839e;
  --grid:#e4e7f0;--axis:#c6cbdb;--border:rgba(15,29,88,.10);--shadow:0 1px 2px rgba(15,29,88,.05),0 6px 20px rgba(15,29,88,.05);
  --accent:#0033ff;--accent-strong:#0029cc;--accent-track:#d3dcff;--accent-wash:rgba(0,51,255,.06);
  --neg:#e34948;--context:#c6cbdb;--good:#0ca30c;--good-text:#006300;--bad:#d03b3b;--bad-text:#b42626;--crest-bg:transparent}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
  --page:#080d24;--surface-1:#121a3d;--surface-2:#19224a;--text-primary:#fff;--text-secondary:#c4c9de;--muted:#8a91ad;
  --grid:#232c55;--axis:#343e6c;--border:rgba(255,255,255,.09);--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.25);
  --accent:#4f8cff;--accent-strong:#8fb4ff;--accent-track:#22357a;--accent-wash:rgba(79,140,255,.14);
  --neg:#e66767;--context:#38426e;--good-text:#2bbf2b;--bad:#e66767;--bad-text:#ff8a8a;--crest-bg:#fff}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;
  --page:#080d24;--surface-1:#121a3d;--surface-2:#19224a;--text-primary:#fff;--text-secondary:#c4c9de;--muted:#8a91ad;
  --grid:#232c55;--axis:#343e6c;--border:rgba(255,255,255,.09);--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.25);
  --accent:#4f8cff;--accent-strong:#8fb4ff;--accent-track:#22357a;--accent-wash:rgba(79,140,255,.14);
  --neg:#e66767;--context:#38426e;--good-text:#2bbf2b;--bad:#e66767;--bad-text:#ff8a8a;--crest-bg:#fff}
*{box-sizing:border-box}
html,body{margin:0}
.viz-root{min-height:100vh;background:var(--page);color:var(--text-primary);overflow-x:hidden;
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;display:flex;flex-direction:column}
a{color:inherit;text-decoration:none}
:focus-visible{outline:2px solid var(--brand-cyan);outline-offset:2px;border-radius:4px}
/* ---- crests & team links */
.crest{display:inline-block;flex:none;object-fit:contain;border-radius:50%;background:var(--crest-bg);vertical-align:middle}
.crest-fallback{display:inline-grid;place-items:center;background:var(--brand-navy-2);color:#fff;font-weight:700;letter-spacing:.02em}
a.tlink{display:inline-flex;align-items:center;gap:7px;min-width:0;max-width:100%;vertical-align:middle}
a.tlink .tname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-bottom:1px solid transparent}
a.tlink:hover .tname{border-bottom-color:currentColor}
/* ---- header */
.site-head{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:22px;padding:0 clamp(16px,4vw,40px);height:62px;
  background:linear-gradient(90deg,#081038,var(--brand-navy-2));color:#fff;box-shadow:0 2px 12px rgba(8,16,56,.25)}
.brand{display:flex;align-items:center;gap:11px;white-space:nowrap}
.brand-badge{width:40px;height:40px;border-radius:10px;background:#fff;display:grid;place-items:center;overflow:hidden;flex:none}
.brand-badge img{width:36px;height:36px;object-fit:contain}
.brand-text{display:flex;flex-direction:column;line-height:1.15}
.brand-text b{font-size:15.5px;font-weight:750;letter-spacing:.01em}
.brand-text small{font-size:11.5px;color:var(--brand-cyan);font-weight:600;letter-spacing:.06em}
nav{display:flex;gap:2px;overflow-x:auto;flex:1;scrollbar-width:none;align-self:stretch}
nav a{display:flex;align-items:center;padding:0 13px;color:rgba(255,255,255,.72);white-space:nowrap;font-size:13.5px;font-weight:500;border-bottom:3px solid transparent;border-top:3px solid transparent}
nav a:hover{color:#fff;background:rgba(255,255,255,.06)}
nav a.active{color:#fff;border-bottom-color:var(--brand-cyan);font-weight:650}
.head-tools{display:flex;gap:8px;align-items:center}
.focus-pick{display:flex;gap:8px;align-items:center;color:rgba(255,255,255,.7);font-size:12.5px}
select,.btn,#theme{font:inherit;font-size:13px;border-radius:9px;padding:7px 11px;cursor:pointer}
select{color:var(--text-primary);background:var(--surface-1);border:1px solid var(--border)}
.site-head select,.site-head #theme{background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.22)}
.site-head select option{color:#0d1433}
#theme{width:36px;padding:7px 0}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary);font-weight:600}
.btn:disabled{cursor:default}
.btn-primary{background:var(--brand-cyan);border-color:var(--brand-cyan);color:#081038;font-weight:700}
.btn-primary:hover{filter:brightness(1.07)}
.btn-primary:disabled{opacity:.75;cursor:progress}
.btn-cta{background:#fff;color:var(--brand-navy);border-color:#fff;padding:10px 18px;font-size:14px}
.btn-ghost{background:transparent;color:#fff;border-color:rgba(255,255,255,.35);padding:10px 18px;font-size:14px}
.btn-cta:hover,.btn-ghost:hover{filter:brightness(1.1)}
.btn-outline{background:transparent;color:#fff;border-color:rgba(255,255,255,.4)}
.btn-outline:disabled{color:var(--brand-cyan);border-color:var(--brand-cyan)}
@media (max-width:820px){.site-head{flex-wrap:wrap;height:auto;padding-top:8px;gap:8px}.focus-pick span{display:none}nav{order:3;flex-basis:100%;height:42px}}
/* ---- layout */
main{width:100%;max-width:1240px;margin:0 auto;padding:26px clamp(16px,4vw,40px) 48px;display:flex;flex-direction:column;gap:28px;outline:none;flex:1}
main.enter>*{animation:enter .25s ease-out both}
@keyframes enter{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){main.enter>*{animation:none}}
h1{margin:0;font-size:30px;font-weight:780;letter-spacing:-.015em;line-height:1.15}
h2{margin:0;font-size:17px;font-weight:700;letter-spacing:-.005em}
.sub{color:var(--text-secondary);font-size:13px}
.muted{color:var(--muted)} .small{font-size:12px} .strong{font-weight:650}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.section-head h2::before{content:"";display:inline-block;width:4px;height:17px;border-radius:2px;background:var(--brand-cyan);margin-right:10px;vertical-align:-3px}
.section-head a{color:var(--accent-strong);font-size:13px;font-weight:600}
.panel{background:var(--surface-1);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
.grid-2{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:28px;align-items:start}
.grid-2-even{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;align-items:start}
@media (max-width:960px){.grid-2,.grid-2-even{grid-template-columns:1fr}}
.stack{display:flex;flex-direction:column;gap:28px}
.foot-note{margin:12px 0 0;color:var(--muted);font-size:12px}
.lede{margin:0;color:var(--text-secondary);max-width:820px}
/* ---- banners */
.banner{position:relative;width:100vw;margin-left:calc(50% - 50vw);margin-top:-26px;color:#fff;overflow:hidden;
  background:
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='400' viewBox='0 0 1200 400'%3E%3Cg fill='none' stroke='%23ffffff' stroke-opacity='.07' stroke-width='2'%3E%3Ccircle cx='600' cy='200' r='90'/%3E%3Cline x1='600' y1='0' x2='600' y2='400'/%3E%3Cpath d='M1200 50h-170a150 150 0 0 0 0 300h170'/%3E%3Cpath d='M0 50h170a150 150 0 0 1 0 300H0'/%3E%3Crect x='1030' y='130' width='170' height='140'/%3E%3Crect x='0' y='130' width='170' height='140'/%3E%3C/g%3E%3C/svg%3E") center/cover no-repeat,
    radial-gradient(1200px 400px at 85% -10%,rgba(62,190,223,.28),transparent 60%),
    linear-gradient(120deg,#081038 0%,var(--brand-navy-2) 55%,#0033ff 130%)}
.banner-inner{max-width:1240px;margin:0 auto;padding:34px clamp(16px,4vw,40px) 36px;display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}
.eyebrow{font-size:11.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand-cyan);margin-bottom:8px}
.hero-sub{margin:8px 0 0;color:rgba(255,255,255,.78);font-size:14px;max-width:640px}
.crumb{font-size:12.5px;color:rgba(255,255,255,.65);margin-bottom:10px}
.crumb a:hover{color:#fff}
.hero .banner-inner{padding-top:44px;padding-bottom:48px;align-items:center}
.hero h1{font-size:40px}
.hero-cta{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}
.feature{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:18px;padding:18px 22px 16px;min-width:min(440px,100%);backdrop-filter:blur(6px)}
.feature-when{font-size:12px;color:rgba(255,255,255,.75);margin-bottom:12px;display:flex;justify-content:space-between;gap:10px}
.feature-when b{color:var(--brand-cyan);font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:11px}
.feature-match{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px}
.feature-team{display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;font-weight:650;font-size:14px}
.feature-team .crest{background:#fff;padding:5px;border-radius:50%;box-sizing:content-box}
.feature-team.fav span{color:#fff} .feature-team:not(.fav) span{color:rgba(255,255,255,.75)}
.feature-score{display:flex;gap:6px;font-size:38px;font-weight:780;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.feature-score .dash{color:rgba(255,255,255,.45);font-weight:400}
.prob-hero{display:flex;gap:2px;height:8px;margin:16px 0 6px}
.prob-hero .seg.accent{background:var(--brand-cyan)} .prob-hero .seg.track{background:rgba(255,255,255,.2)}
.feature .prob-labels{color:rgba(255,255,255,.85)}
.team-banner-row{display:flex;align-items:center;gap:18px}
.team-banner-row .crest{background:#fff;padding:8px;box-sizing:content-box;box-shadow:0 6px 20px rgba(0,0,0,.25)}
/* ---- ticker */
.ticker{display:flex;gap:10px;overflow-x:auto;padding-bottom:4px;scrollbar-width:thin;margin-top:-6px}
.tick{flex:none;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:center;background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:9px 12px;box-shadow:var(--shadow);font-size:12.5px;min-width:190px}
.tick .t-date{grid-column:1/-1;color:var(--muted);font-size:11px;display:flex;justify-content:space-between}
.tick .t-team{display:flex;align-items:center;gap:7px;min-width:0}
.tick .t-team span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tick .t-pts{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
.tick .lost{color:var(--muted);font-weight:500}
/* ---- KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
.kpi{background:var(--surface-1);border:1px solid var(--border);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.kpi::after{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:linear-gradient(var(--brand-cyan),var(--brand-blue))}
.kpi-label{color:var(--text-secondary);font-size:11.5px;font-weight:650;text-transform:uppercase;letter-spacing:.06em}
.kpi-value{font-size:30px;font-weight:750;margin:6px 0 2px;letter-spacing:-.01em}
.kpi-sub{color:var(--muted);font-size:12px}
/* ---- prediction cards */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(272px,1fr));gap:14px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:16px;padding:0 0 14px;box-shadow:var(--shadow);transition:box-shadow .18s,transform .18s;overflow:hidden}
.card:hover{transform:translateY(-2px);box-shadow:0 12px 28px rgba(15,29,88,.12)}
.card.is-focus{box-shadow:0 0 0 2px var(--brand-cyan),var(--shadow)}
.card-when{color:var(--text-secondary);font-size:11.5px;font-weight:600;padding:9px 16px;margin-bottom:10px;display:flex;justify-content:space-between;gap:8px;background:var(--surface-2);border-bottom:1px solid var(--border)}
.card-when .muted{font-weight:500}
.board,.card>.prob,.card>.prob-labels,.card>.card-note{margin-left:16px;margin-right:16px}
.board{display:flex;flex-direction:column;gap:6px}
.board-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px}
.board-row .tlink{font-weight:500;font-size:14.5px}
.board-row .pts{font-size:22px;font-weight:500;font-variant-numeric:tabular-nums;color:var(--muted);min-width:34px;text-align:right}
.board-row.fav .tlink{font-weight:700}
.board-row.fav .pts{font-weight:750;color:var(--text-primary)}
.elo{color:var(--muted);font-size:11px;white-space:nowrap}
.prob{display:flex;gap:2px;height:8px;margin-top:14px;margin-bottom:5px}
.seg{height:100%;min-width:2px}
.seg:first-child{border-radius:4px 0 0 4px} .seg:last-child{border-radius:0 4px 4px 0}
.seg.accent{background:var(--accent)} .seg.track{background:var(--accent-track)}
.prob-labels{display:flex;justify-content:space-between;font-size:12px;font-variant-numeric:tabular-nums}
.card-note{margin-top:8px;font-size:12px;color:var(--text-secondary);border-top:1px solid var(--grid);padding-top:6px}
/* ---- tables */
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-weight:650;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:.05em;padding:8px;border-bottom:1px solid var(--axis);white-space:nowrap;user-select:none}
th.sortable{cursor:pointer} th.sortable:hover{color:var(--text-primary)}
th .arrow{display:inline-block;width:10px;color:var(--accent-strong)}
td{padding:8px;border-bottom:1px solid var(--grid);white-space:nowrap}
tbody tr{transition:background .12s}
tbody tr:hover td{background:var(--surface-2)}
.num{text-align:right;font-variant-numeric:tabular-nums}
tr.is-focus td{background:var(--accent-wash)} tr.is-focus .tlink{font-weight:700}
tr.is-focus td:first-child{box-shadow:inset 3px 0 0 var(--brand-cyan)}
.form{display:inline-flex;gap:3px;vertical-align:middle}
.chip{display:inline-grid;place-items:center;width:19px;height:19px;border-radius:5px;font-size:10px;font-weight:800;color:#fff}
.chip.win{background:var(--good)} .chip.loss{background:var(--bad)}
.verdict{font-weight:700;font-size:12px;white-space:nowrap} .verdict.good{color:var(--good-text)} .verdict.bad{color:var(--bad-text)} .verdict.pending{color:var(--muted);font-weight:500}
.badge{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:999px;border:1px solid var(--border);color:var(--text-secondary);margin-left:6px;vertical-align:1px;background:var(--surface-2)}
.pred{font-variant-numeric:tabular-nums;color:var(--text-secondary)}
.pred b{color:var(--text-primary);font-weight:700}
.score-cell{font-weight:750}
.pos{display:inline-grid;place-items:center;min-width:24px;height:22px;border-radius:6px;font-weight:700;font-size:12px;color:var(--text-secondary)}
.pos.top{background:var(--accent-wash);color:var(--accent-strong)}
/* ---- filters */
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.seg-ctrl{display:inline-flex;border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--surface-1);flex-wrap:wrap}
.seg-ctrl button{font:inherit;font-size:12.5px;border:0;background:transparent;color:var(--text-secondary);padding:7px 12px;cursor:pointer}
.seg-ctrl button+button{border-left:1px solid var(--border)}
.seg-ctrl button[aria-pressed=true]{background:var(--brand-navy-2);color:#fff;font-weight:650}
.summary-line{color:var(--text-secondary);font-size:13px;margin:-4px 0 12px}
/* ---- team tiles */
.team-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.team-tile{display:block;background:var(--surface-1);border:1px solid var(--border);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow);transition:transform .18s,box-shadow .18s;position:relative;overflow:hidden}
.team-tile:hover{transform:translateY(-3px);box-shadow:0 14px 30px rgba(15,29,88,.12)}
.team-tile.is-focus{box-shadow:0 0 0 2px var(--brand-cyan),var(--shadow)}
.tile-top{display:flex;justify-content:space-between;align-items:center}
.tile-pos{font-size:12px;font-weight:700;color:var(--text-secondary)}
.tile-name{display:flex;align-items:center;gap:12px;font-weight:750;font-size:15.5px;margin:12px 0 4px;min-width:0}
.tile-name span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tile-row{display:flex;justify-content:space-between;align-items:center;color:var(--text-secondary);font-size:12.5px;margin-top:9px;gap:8px}
/* ---- schedule */
.sched-day{padding:12px 0;border-bottom:1px solid var(--grid)}
.sched-day:last-child{border-bottom:0}
.sched-date{font-weight:700;font-size:12px;color:var(--accent-strong);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
.sched-game{display:grid;grid-template-columns:56px minmax(0,1fr) auto;gap:10px;align-items:center;padding:5px 0;font-size:13.5px}
.sched-game .vs{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap}
.sched-game.is-focus{font-weight:700}
.pchip{font-size:11.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap;background:var(--surface-2);border:1px solid var(--border);border-radius:999px;padding:2px 9px}
.pchip:empty{display:none}
.pchip .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:6px;vertical-align:1px}
/* ---- charts */
.chart{width:100%;position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart text{fill:var(--text-secondary);font-size:11px;font-family:inherit}
.chart .axis-label{fill:var(--muted)}
.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .baseline{stroke:var(--axis);stroke-width:1}
.bar-pos{fill:var(--accent)} .bar-neg{fill:var(--neg)}
.bar-hit{fill:transparent;cursor:pointer}
.bar-row:hover .bar-pos,.bar-row:hover .bar-neg{opacity:.82}
.bar-row.is-focus text{fill:var(--text-primary);font-weight:700}
.line-ctx{fill:none;stroke:var(--context);stroke-width:1.25;stroke-linejoin:round;stroke-linecap:round}
.line-focus{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.end-dot{fill:var(--accent);stroke:var(--surface-1);stroke-width:2}
.crosshair{stroke:var(--axis);stroke-width:1}
.season-mark{stroke:var(--axis);stroke-width:1}
.diag{stroke:var(--axis);stroke-width:1}
.cal-dot{fill:var(--accent);stroke:var(--surface-1);stroke-width:2}
.tip{position:fixed;z-index:20;pointer-events:none;background:var(--surface-1);color:var(--text-primary);
  border:1px solid var(--border);border-radius:10px;padding:8px 11px;font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;
  box-shadow:0 10px 28px rgba(8,16,56,.2);max-width:280px}
.tip .t-val{font-weight:700;font-size:13px}
.tip .t-row{display:flex;align-items:center;gap:6px;font-variant-numeric:tabular-nums}
.tip .key{display:inline-block;width:12px;height:2px;border-radius:1px;flex:none}
.tip .t-sub{color:var(--text-secondary)}
.empty{color:var(--muted);padding:12px 0}
/* ---- footer */
.site-foot{background:linear-gradient(90deg,#081038,var(--brand-navy-2));color:rgba(255,255,255,.7);font-size:12px;margin-top:auto}
.foot-inner{max-width:1240px;margin:0 auto;padding:18px clamp(16px,4vw,40px);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.foot-brand{display:flex;align-items:center;gap:10px;color:#fff;font-weight:700}
.foot-brand img{width:30px;height:30px;background:#fff;border-radius:8px;padding:2px}
details summary{cursor:pointer;color:var(--text-secondary);padding:2px 0;font-weight:600}
details[open] summary{margin-bottom:10px}
dl.glossary{display:grid;grid-template-columns:max-content 1fr;gap:9px 18px;margin:0}
dl.glossary dt{font-weight:700} dl.glossary dd{margin:0;color:var(--text-secondary)}
.toast{position:fixed;right:20px;bottom:20px;z-index:30;max-width:380px;background:var(--surface-1);color:var(--text-primary);
  border:1px solid var(--border);border-left:4px solid var(--brand-cyan);border-radius:12px;padding:12px 14px;box-shadow:0 14px 36px rgba(8,16,56,.25);font-size:13px;white-space:pre-line}
.toast.bad{border-left-color:var(--bad)} .toast.good{border-left-color:var(--good)}
.steps{margin:0;padding-left:22px;display:flex;flex-direction:column;gap:10px}
.steps li{padding-left:4px} .steps b{color:var(--text-primary)}
.howto{color:var(--text-secondary)}
.howto p{margin:0 0 8px;max-width:820px}
.kbd{display:inline-block;padding:1px 8px;border:1px solid var(--border);border-bottom-width:2px;border-radius:6px;background:var(--surface-2);font-size:12px;color:var(--text-primary);font-weight:600}
@media print{.site-head{position:static}.head-tools{display:none}}
"""

_JS = r"""
(() => {
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const app = document.getElementById('app');
const tip = document.getElementById('tip');
const root = document.documentElement;
const NS = 'http://www.w3.org/2000/svg';
const DAYS = ['Κυρ', 'Δευ', 'Τρι', 'Τετ', 'Πεμ', 'Παρ', 'Σαβ'];
const MONTHS = ['Ιαν', 'Φεβ', 'Μαρ', 'Απρ', 'Μάι', 'Ιουν', 'Ιουλ', 'Αυγ', 'Σεπ', 'Οκτ', 'Νοε', 'Δεκ'];
const STANDING = Object.fromEntries(D.standings.map(r => [r.team, r]));
const TEAMS = D.standings.map(r => r.team);
let focus = localStorage.getItem('gbl-focus');
if (!STANDING[focus]) focus = D.focus;

// ---------------------------------------------------------------- helpers
// DOM builder. Strings become text nodes: names from CSV/API never touch innerHTML.
function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false && c !== '') n.append(c instanceof Node ? c : String(c));
  return n;
}
function s(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function stext(parent, x, y, str, attrs) { const t = s('text', {x, y, ...(attrs || {})}, parent); t.textContent = str; return t; }
const parse = iso => new Date(iso + 'T12:00:00');
const dayLabel = iso => { const d = parse(iso); return `${DAYS[d.getDay()]} ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`; };
const fullDate = iso => { const d = parse(iso); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; };
const pct = x => x == null ? '–' : Math.round(x * 100) + '%';
const fx = (x, n = 3) => x == null ? '–' : x.toFixed(n);
const signed = x => (x > 0 ? '+' : '') + x;
const teamHref = t => '#/team/' + encodeURIComponent(t);
const LOGOS = D.logos || {};
function crest(team, size = 20) {
  const st = `width:${size}px;height:${size}px`;
  if (LOGOS[team]) return h('img', {class: 'crest', src: LOGOS[team], alt: '', 'aria-hidden': 'true', style: st});
  const ini = team.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return h('span', {class: 'crest crest-fallback', 'aria-hidden': 'true', style: `${st};font-size:${Math.round(size * 0.4)}px`}, ini);
}
const tlink = (t, size = 18) => h('a', {class: 'tlink', href: teamHref(t), title: t}, crest(t, size), h('span', {class: 'tname'}, t));
const roundNo = Math.max(0, ...D.standings.map(r => r.gp)) + 1;
function pageBanner(title, sub, extra, crumb) {
  return h('section', {class: 'banner'}, h('div', {class: 'banner-inner'},
    h('div', null, crumb || null, h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${D.season}`), h('h1', null, title), sub ? h('p', {class: 'hero-sub'}, sub) : null),
    extra || null));
}
const css = name => getComputedStyle(document.querySelector('.viz-root')).getPropertyValue(name).trim();
const isFocus = (...teams) => teams.includes(focus);
const streakGr = st => st.replace('W', 'Ν').replace('L', 'Η');
const winnerOf = g => g.hs > g.as ? g.home : g.away;
const marginErr = (pk, hs, as) => Math.abs((pk.phs - pk.pas) - (hs - as));

// ---------------------------------------------------------------- tooltip
function showTip(evt, rows) {
  tip.replaceChildren(...rows.map((r, i) => {
    const d = h('div', {class: r.cls || (i === 0 ? 't-val' : 't-sub')});
    if (r.key) { d.classList.add('t-row'); d.append(h('span', {class: 'key', style: `background:${r.key}`})); }
    d.append(r.text);
    return d;
  }));
  tip.hidden = false;
  const pad = 14, w = tip.offsetWidth, ht = tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > innerWidth - 8) x = evt.clientX - w - pad;
  if (y + ht > innerHeight - 8) y = evt.clientY - ht - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
const hideTip = () => { tip.hidden = true; };
function hover(node, rowsFn) {
  node.addEventListener('pointermove', e => showTip(e, rowsFn()));
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', () => { const b = node.getBoundingClientRect(); showTip({clientX: b.left + b.width / 2, clientY: b.top}, rowsFn()); });
  node.addEventListener('blur', hideTip);
}

// ---------------------------------------------------------------- components
function kpi(label, value, sub) {
  return h('div', {class: 'kpi'}, h('div', {class: 'kpi-label'}, label), h('div', {class: 'kpi-value'}, value), h('div', {class: 'kpi-sub'}, sub));
}
function formChips(form) {
  return h('span', {class: 'form'}, form.map(r => h('span', {class: 'chip ' + (r === 'W' ? 'win' : 'loss'), title: r === 'W' ? 'Νίκη' : 'Ήττα'}, r === 'W' ? 'Ν' : 'Η')));
}
function sectionHead(title, sub, link) {
  return h('div', {class: 'section-head'}, h('h2', null, title, sub ? h('span', {class: 'sub', style: 'margin-left:8px;font-weight:400'}, sub) : null), link || null);
}
const record = t => STANDING[t] ? `${STANDING[t].w}-${STANDING[t].l}` : '';
function predCard(p) {
  const homeFav = p.p >= 0.5, hp = Math.round(p.p * 100), ap = 100 - hp;
  const bar = h('div', {class: 'prob', tabindex: 0, role: 'img', 'aria-label': `Πιθανότητα νίκης: ${p.home} ${hp}%, ${p.away} ${ap}%`},
    h('div', {class: 'seg ' + (homeFav ? 'accent' : 'track'), style: `width:${hp}%`}),
    h('div', {class: 'seg ' + (homeFav ? 'track' : 'accent'), style: `width:${ap}%`}));
  hover(bar, () => [
    {text: `${p.w} ${Math.max(hp, ap)}%`},
    {text: `Προβλεπόμενη διαφορά ${signed(p.margin)} για τον γηπεδούχο (±${p.band})`},
    {text: `Elo μόνο του: ${p.home} ${Math.round(p.p_elo * 100)}%`},
  ]);
  return h('article', {class: 'card' + (isFocus(p.home, p.away) ? ' is-focus' : '')},
    h('div', {class: 'card-when'}, h('span', null, `${dayLabel(p.d)} · ${p.t || '–'}`), h('span', {class: 'muted'}, `Elo ${p.home_elo} – ${p.away_elo}`)),
    h('div', {class: 'board'},
      h('div', {class: 'board-row' + (homeFav ? ' fav' : '')}, tlink(p.home), h('span', {class: 'elo', title: 'Γηπεδούχος'}, record(p.home)), h('span', {class: 'pts'}, p.phs)),
      h('div', {class: 'board-row' + (homeFav ? '' : ' fav')}, tlink(p.away), h('span', {class: 'elo'}, record(p.away)), h('span', {class: 'pts'}, p.pas))),
    bar,
    h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', {class: 'muted'}, `±${p.band} πόντοι`), h('span', null, ap + '%')),
    (p.notes || []).map(n => h('div', {class: 'card-note'}, n)));
}
function verdict(ok) {
  if (ok == null) return h('span', {class: 'verdict pending'}, '⏳ εκκρεμεί');
  return h('span', {class: 'verdict ' + (ok ? 'good' : 'bad')}, ok ? '✓ Σωστό' : '✗ Λάθος');
}
function predCell(pk, home) {
  if (!pk) return h('span', {class: 'muted'}, '–');
  const pw = pk.w === home ? pk.p : 1 - pk.p;
  return h('span', {class: 'pred'}, h('b', null, `${pk.phs}–${pk.pas}`), ` · ${pk.w} ${pct(pw)}`,
    h('span', {class: 'badge', title: pk.src === 'log' ? `Καταγράφηκε πριν από τον αγώνα · μοντέλο ${pk.v}` : 'Walk-forward: μοντέλο εκπαιδευμένο μόνο σε προηγούμενους αγώνες'}, pk.src === 'log' ? 'πριν τον αγώνα' : 'walk-forward'));
}

// Sortable table. cols: {label, num?, sort?(row), render(row), title?}
function table(cols, rows, opts = {}) {
  let sortIdx = opts.sortIdx ?? -1, dir = opts.dir ?? 1;
  const wrap = h('div', {class: 'table-wrap'});
  function draw() {
    const data = rows.slice();
    if (sortIdx >= 0 && cols[sortIdx].sort) {
      const f = cols[sortIdx].sort;
      data.sort((a, b) => { const x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : 0) * dir; });
    }
    const head = h('tr', null, cols.map((c, i) => {
      const th = h('th', {class: (c.num ? 'num ' : '') + (c.sort ? 'sortable' : ''), title: c.title || null, scope: 'col',
        'aria-sort': i === sortIdx ? (dir > 0 ? 'ascending' : 'descending') : null, tabindex: c.sort ? 0 : null},
        c.label, c.sort ? h('span', {class: 'arrow'}, i === sortIdx ? (dir > 0 ? '▲' : '▼') : ' ') : null);
      if (c.sort) {
        const act = () => { if (sortIdx === i) dir = -dir; else { sortIdx = i; dir = c.num ? -1 : 1; } draw(); };
        th.addEventListener('click', act);
        th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
      }
      return th;
    }));
    const body = data.length
      ? data.map(r => h('tr', {class: opts.rowClass ? opts.rowClass(r) : null}, cols.map(c => h('td', {class: c.num ? 'num' : null}, c.render(r)))))
      : [h('tr', null, h('td', {colspan: cols.length, class: 'empty'}, opts.empty || 'Δεν υπάρχουν δεδομένα.'))];
    wrap.replaceChildren(h('table', null, h('thead', null, head), h('tbody', null, body)));
  }
  draw();
  return wrap;
}
function segCtrl(options, value, onChange) {
  const box = h('div', {class: 'seg-ctrl', role: 'group'});
  const draw = () => box.replaceChildren(...options.map(([v, label]) => h('button', {type: 'button', 'aria-pressed': String(v === value), onclick: () => { value = v; draw(); onChange(v); }}, label)));
  draw();
  return box;
}
function selectEl(options, value, onChange, label) {
  return h('select', {'aria-label': label, onchange: e => onChange(e.target.value)}, options.map(([v, t]) => h('option', {value: v, selected: v === value}, t)));
}

// Results with the model's exact pre-game call next to the real score.
function resultsTable(games, opts = {}) {
  return table([
    {label: 'Ημέρα', sort: g => g.d, render: g => dayLabel(g.d)},
    {label: 'Γηπεδούχος', sort: g => g.home, render: g => h('span', {class: g.hs > g.as ? 'strong' : null}, tlink(g.home))},
    {label: 'Σκορ', num: true, render: g => h('span', {class: 'score-cell'}, `${g.hs} – ${g.as}`)},
    {label: 'Φιλοξενούμενος', sort: g => g.away, render: g => h('span', {class: g.as > g.hs ? 'strong' : null}, tlink(g.away))},
    {label: 'Πρόβλεψη μοντέλου', render: g => predCell(g.pick, g.home)},
    {label: 'Απόκλιση', num: true, title: 'Πόσους πόντους απείχε η προβλεπόμενη διαφορά από την πραγματική', sort: g => g.pick ? marginErr(g.pick, g.hs, g.as) : 999, render: g => g.pick ? marginErr(g.pick, g.hs, g.as) + ' π.' : ''},
    {label: '', render: g => g.pick ? verdict(g.pick.w === winnerOf(g)) : ''},
  ], games, {sortIdx: 0, dir: -1, rowClass: g => isFocus(g.home, g.away) ? 'is-focus' : null, empty: opts.empty});
}

// ---------------------------------------------------------------- charts
function eloBars(host) {
  host.replaceChildren();
  const rows = [...D.standings].sort((a, b) => b.elo - a.elo);
  const W = Math.max(host.clientWidth, 300), rowH = 26, barH = 16, top = 8, labelW = Math.min(160, W * 0.34), valW = 44;
  const H = top + rows.length * rowH + 22;
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Elo ανά ομάδα σε σχέση με το 1500'}, host);
  const ext = Math.max(50, ...rows.map(r => Math.abs(r.elo - 1500)));
  const x0 = labelW + valW, x1 = W - valW, sx = v => x0 + (v + ext) / (2 * ext) * (x1 - x0), mid = sx(0);
  [-ext, -ext / 2, ext / 2, ext].forEach(v => {
    s('line', {x1: sx(v), x2: sx(v), y1: top - 4, y2: H - 20, class: 'grid'}, svg);
    stext(svg, sx(v), H - 6, String(1500 + Math.round(v)), {'text-anchor': 'middle', class: 'axis-label'});
  });
  stext(svg, mid, H - 6, '1500', {'text-anchor': 'middle', class: 'axis-label'});
  rows.forEach((r, i) => {
    const y = top + i * rowH, d = r.elo - 1500;
    const g = s('g', {class: 'bar-row' + (r.team === focus ? ' is-focus' : '')}, svg);
    stext(g, labelW - 8, y + barH - 3, r.team, {'text-anchor': 'end'});
    const w = Math.max(1, Math.abs(sx(d) - mid)), rad = Math.min(4, w);
    const xs = d >= 0 ? mid : mid - w;
    // Rounded at the data end, square at the baseline.
    const path = d >= 0
      ? `M${xs},${y} h${w - rad} a${rad},${rad} 0 0 1 ${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 1 -${rad},${rad} h-${w - rad} z`
      : `M${xs + w},${y} h-${w - rad} a${rad},${rad} 0 0 0 -${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 0 ${rad},${rad} h${w - rad} z`;
    s('path', {d: path, class: d >= 0 ? 'bar-pos' : 'bar-neg'}, g);
    stext(g, d >= 0 ? mid + w + 6 : mid - w - 6, y + barH - 3, String(r.elo), {'text-anchor': d >= 0 ? 'start' : 'end'});
    const hit = s('rect', {x: 0, y: y - 4, width: W, height: rowH, class: 'bar-hit', tabindex: 0}, g);
    hover(hit, () => [{text: `Elo ${r.elo}`}, {text: `${r.team} · ${signed(d)} από τον μέσο όρο`}, {text: `${r.pos}ος · ${r.w}-${r.l} · κλικ για τη σελίδα της`}]);
    hit.addEventListener('click', () => { location.hash = teamHref(r.team); });
    hit.addEventListener('keydown', e => { if (e.key === 'Enter') location.hash = teamHref(r.team); });
  });
  s('line', {x1: mid, x2: mid, y1: top - 4, y2: H - 20, class: 'baseline'}, svg);
}

function eloAt(team, t) {
  let v = null;
  for (const seg of D.elo_history[team] || []) for (const [d, e] of seg) { if (parse(d) <= t) v = e; else return v; }
  return v;
}
function eloLines(host, team) {
  host.replaceChildren();
  const W = Math.max(host.clientWidth, 300), H = 270, m = {l: 40, r: 74, t: 16, b: 26};
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Εξέλιξη Elo, ${team}`}, host);
  const all = Object.values(D.elo_history).flat(2);
  // Ordinal x: one slot per game day so summers don't eat the width; 3-slot gap per new season.
  const dates = [...new Set(all.map(p => p[0]))].sort();
  const starts = new Set(D.season_starts.slice(1));
  const pos = {}; let k = 0;
  dates.forEach(d => { if (starts.has(d)) k += 3; pos[d] = k++; });
  const sx = d => m.l + pos[d] / Math.max(1, k - 1) * (W - m.l - m.r);
  let lo = Math.min(...all.map(p => p[1])), hi = Math.max(...all.map(p => p[1]));
  lo = Math.floor((lo - 10) / 50) * 50; hi = Math.ceil((hi + 10) / 50) * 50;
  const sy = v => m.t + (hi - v) / (hi - lo) * (H - m.t - m.b);
  for (let v = lo; v <= hi; v += 50) {
    s('line', {x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: v === 1500 ? 'baseline' : 'grid'}, svg);
    stext(svg, m.l - 6, sy(v) + 4, String(v), {'text-anchor': 'end', class: 'axis-label'});
  }
  let prevMonth = '', prevX = -Infinity;
  dates.forEach(d => {
    const mo = d.slice(0, 7), x = sx(d);
    if (mo !== prevMonth && x - prevX > 46) { const dt = parse(d); stext(svg, x, H - 8, MONTHS[dt.getMonth()] + " '" + String(dt.getFullYear()).slice(2), {class: 'axis-label'}); prevX = x; }
    prevMonth = mo;
  });
  D.season_starts.slice(1).forEach(st => {
    const i = dates.indexOf(st), x = i > 0 ? (sx(st) + sx(dates[i - 1])) / 2 : sx(st);
    s('line', {x1: x, x2: x, y1: m.t, y2: H - m.b, class: 'season-mark'}, svg);
    stext(svg, x + 4, m.t - 4, 'νέα σεζόν', {class: 'axis-label'});
  });
  const pathOf = seg => seg.map((p, i) => (i ? 'L' : 'M') + sx(p[0]).toFixed(1) + ',' + sy(p[1]).toFixed(1)).join('');
  for (const [t, segs] of Object.entries(D.elo_history)) if (t !== team) segs.forEach(sg => s('path', {d: pathOf(sg), class: 'line-ctx'}, svg));
  const fsegs = D.elo_history[team] || [];
  fsegs.forEach(sg => s('path', {d: pathOf(sg), class: 'line-focus'}, svg));
  const last = fsegs.length ? fsegs[fsegs.length - 1].slice(-1)[0] : null;
  if (last) {
    s('circle', {cx: sx(last[0]), cy: sy(last[1]), r: 4.5, class: 'end-dot'}, svg);
    stext(svg, sx(last[0]) + 8, sy(last[1]) + 4, `${team} ${Math.round(last[1])}`, {style: 'fill:var(--text-primary);font-weight:600'});
  }
  const cross = s('line', {y1: m.t, y2: H - m.b, class: 'crosshair', visibility: 'hidden'}, svg);
  const overlay = s('rect', {x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent'}, svg);
  overlay.addEventListener('pointermove', e => {
    const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) * W / b.width;
    let best = dates[0], bd = Infinity;
    for (const d of dates) { const dd = Math.abs(sx(d) - px); if (dd < bd) { bd = dd; best = d; } }
    const t = parse(best), x = sx(best);
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('visibility', 'visible');
    const vals = Object.keys(D.elo_history).map(tm => [tm, eloAt(tm, t)]).filter(v => v[1] !== null).sort((a, b) => b[1] - a[1]);
    const fv = eloAt(team, t);
    showTip(e, [{text: fv === null ? team : `${team} ${Math.round(fv)}`, cls: 't-val'}, {text: fullDate(best), cls: 't-sub'},
      ...vals.map(([tm, v]) => ({text: `${Math.round(v)}  ${tm}`, key: tm === team ? css('--accent') : css('--context'), cls: 't-sub'}))]);
  });
  overlay.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
}

// Calibration: when the model gives the favourite 70%, does it win ~70% of the time?
function calibrationBins(games) {
  const bins = [[0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.01]].map(([a, b]) => ({a, b, n: 0, sp: 0, won: 0}));
  for (const g of games) {
    const pf = Math.max(g.pick.p, 1 - g.pick.p), favHome = g.pick.p >= 0.5;
    const bin = bins.find(x => pf >= x.a && pf < x.b); if (!bin) continue;
    bin.n++; bin.sp += pf; bin.won += (favHome === (g.hs > g.as)) ? 1 : 0;
  }
  return bins.filter(b => b.n);
}
function calibration(host, games) {
  host.replaceChildren();
  const bins = calibrationBins(games);
  const W = Math.max(host.clientWidth, 280), H = Math.min(300, W * 0.78), m = {l: 44, r: 20, t: 12, b: 36};
  const svg = s('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Βαθμονόμηση πιθανοτήτων'}, host);
  const sx = v => m.l + (v - 0.5) / 0.5 * (W - m.l - m.r), sy = v => m.t + (1 - v) / 0.6 * (H - m.t - m.b);
  [0.4, 0.6, 0.8, 1.0].forEach(v => { s('line', {x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: 'grid'}, svg); stext(svg, m.l - 6, sy(v) + 4, pct(v), {'text-anchor': 'end', class: 'axis-label'}); });
  [0.5, 0.6, 0.7, 0.8, 0.9, 1.0].forEach(v => stext(svg, sx(v), H - 18, pct(v), {'text-anchor': 'middle', class: 'axis-label'}));
  stext(svg, (m.l + W - m.r) / 2, H - 2, 'πιθανότητα που έδωσε το μοντέλο στο φαβορί', {'text-anchor': 'middle', class: 'axis-label'});
  s('line', {x1: sx(0.5), y1: sy(0.5), x2: sx(1), y2: sy(1), class: 'diag'}, svg);
  stext(svg, sx(0.6) + 6, sy(0.6) + 16, 'τέλεια βαθμονόμηση', {class: 'axis-label'});
  bins.forEach(b => {
    const px = b.sp / b.n, py = Math.max(0.4, b.won / b.n);
    s('circle', {cx: sx(px), cy: sy(py), r: 5, class: 'cal-dot'}, svg);
    stext(svg, sx(px) + 9, sy(py) + 4, String(b.n), {class: 'axis-label'});
    const hit = s('circle', {cx: sx(px), cy: sy(py), r: 14, fill: 'transparent', tabindex: 0}, svg);
    hover(hit, () => [{text: `${pct(b.won / b.n)} νίκες του φαβορί`}, {text: `μέση πρόβλεψη ${pct(px)} · ${b.n} αγώνες`}]);
  });
}

// ---------------------------------------------------------------- pages
const played = D.games;
const season = D.season;
const seasonGames = played.filter(g => g.s === season);
const pages = {};

function hero(p) {
  const nr = D.next;
  const copy = h('div', null,
    h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${season}`),
    h('h1', null, nr.length ? `${roundNo}η αγωνιστική` : `Basket League ${season}`),
    h('p', {class: 'hero-sub'}, nr.length
      ? `${dayLabel(nr[0].d)} – ${dayLabel(nr[nr.length - 1].d)} · ${nr.length} αγώνες · ενημέρωση ${D.updated}`
      : `Ενημέρωση ${D.updated}`),
    h('div', {class: 'hero-cta'}, h('a', {class: 'btn btn-cta', href: '#/predictions'}, 'Όλες οι προβλέψεις'), h('a', {class: 'btn btn-ghost', href: '#/standings'}, 'Βαθμολογία')));
  if (!p) return h('section', {class: 'banner hero'}, h('div', {class: 'banner-inner'}, copy));
  const hp = Math.round(p.p * 100), ap = 100 - hp, homeFav = p.p >= 0.5;
  const feature = h('div', {class: 'feature'},
    h('div', {class: 'feature-when'}, h('b', null, isFocus(p.home, p.away) ? 'Η ομάδα σου' : 'Πρώτος αγώνας'), h('span', null, `${dayLabel(p.d)} · ${p.t || ''}`)),
    h('div', {class: 'feature-match'},
      h('a', {class: 'feature-team' + (homeFav ? ' fav' : ''), href: teamHref(p.home)}, crest(p.home, 54), h('span', null, p.home)),
      h('div', {class: 'feature-score'}, h('span', null, p.phs), h('span', {class: 'dash'}, '–'), h('span', null, p.pas)),
      h('a', {class: 'feature-team' + (homeFav ? '' : ' fav'), href: teamHref(p.away)}, crest(p.away, 54), h('span', null, p.away))),
    h('div', {class: 'prob-hero', role: 'img', 'aria-label': `Πιθανότητα νίκης: ${p.home} ${hp}%, ${p.away} ${ap}%`},
      h('div', {class: 'seg ' + (homeFav ? 'accent' : 'track'), style: `width:${hp}%`}),
      h('div', {class: 'seg ' + (homeFav ? 'track' : 'accent'), style: `width:${ap}%`})),
    h('div', {class: 'prob-labels'}, h('span', null, hp + '%'), h('span', null, 'πιθανότητα νίκης'), h('span', null, ap + '%')));
  return h('section', {class: 'banner hero'}, h('div', {class: 'banner-inner'}, copy, feature));
}

pages.home = () => {
  const m = D.model;
  const graded = D.log.filter(r => r.ok !== null), pending = D.log.filter(r => r.ok === null);
  const correct = graded.filter(r => r.ok).length;
  const fs = STANDING[focus];
  const focusNext = D.upcoming.find(u => u.home === focus || u.away === focus);
  const focusPred = focusNext && focusNext.pi >= 0 ? D.next[focusNext.pi] : null;
  const feat = D.next.find(p => isFocus(p.home, p.away)) || D.next[0];
  return [
    hero(feat),
    played.length ? h('section', {class: 'ticker', 'aria-label': 'Τελευταία αποτελέσματα'}, played.slice(0, 10).map(g => {
      const hw = g.hs > g.as;
      return h('a', {class: 'tick', href: teamHref(isFocus(g.away) ? g.away : g.home), title: `${g.home} ${g.hs}–${g.as} ${g.away}`},
        h('span', {class: 't-date'}, h('span', null, dayLabel(g.d)), g.pick ? verdict(g.pick.w === winnerOf(g)) : h('span')),
        h('span', {class: 't-team' + (hw ? '' : ' lost')}, crest(g.home, 18), h('span', null, g.home)), h('span', {class: 't-pts' + (hw ? '' : ' lost')}, g.hs),
        h('span', {class: 't-team' + (hw ? ' lost' : '')}, crest(g.away, 18), h('span', null, g.away)), h('span', {class: 't-pts' + (hw ? ' lost' : '')}, g.as));
    })) : null,
    h('section', {class: 'kpis'},
      kpi('Αγώνες σεζόν', String(seasonGames.length), `${D.upcoming.length} ακόμα στο πρόγραμμα`),
      kpi('Ρεκόρ προβλέψεων', graded.length ? `${correct}/${graded.length}` : '–', graded.length ? `${pct(correct / graded.length)} σωστοί νικητές · ${pending.length} σε αναμονή` : `${pending.length} σε αναμονή`),
      kpi('Ακρίβεια μοντέλου', pct(m.acc), `walk-forward σε ${m.n_test} αγώνες · Elo μόνο ${pct(m.elo_acc)}`),
      kpi('Σφάλμα διαφοράς', m.margin_mae == null ? '–' : `±${m.margin_mae}`, `πόντοι κατά μέσο όρο · σύνολο ±${m.total_mae}`)),
    h('section', null, sectionHead('Επόμενη αγωνιστική', D.next.length ? `${dayLabel(D.next[0].d)} – ${dayLabel(D.next[D.next.length - 1].d)}` : '', h('a', {href: '#/predictions'}, 'Όλες οι προβλέψεις →')),
      D.next.length ? h('div', {class: 'cards'}, D.next.map(predCard)) : h('p', {class: 'empty'}, 'Δεν υπάρχουν προγραμματισμένοι αγώνες.')),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Βαθμολογία', season, h('a', {href: '#/standings'}, 'Πλήρης →')), standingsTable(true)),
      h('div', {class: 'stack'},
        fs ? h('section', {class: 'panel'}, sectionHead(focus, `${fs.pos}ος · ${fs.w}-${fs.l}`, h('a', {href: teamHref(focus)}, 'Σελίδα ομάδας →')),
          h('div', {class: 'tile-row'}, h('span', null, 'Φόρμα'), formChips(fs.form)),
          h('div', {class: 'tile-row'}, h('span', null, 'Elo'), h('b', null, fs.elo)),
          h('div', {class: 'tile-row'}, h('span', null, 'Πόντοι / αγώνα'), h('span', null, `${(fs.pf / fs.gp).toFixed(1)} υπέρ · ${(fs.pa / fs.gp).toFixed(1)} κατά`)),
          focusNext ? h('div', {class: 'tile-row'}, h('span', null, 'Επόμενος'), h('span', null, `${dayLabel(focusNext.d)} · ${focusNext.home === focus ? 'vs ' + focusNext.away : '@ ' + focusNext.home}`)) : null,
          focusPred ? h('div', {class: 'tile-row'}, h('span', null, 'Πρόβλεψη'), h('b', null, `${focusPred.phs}–${focusPred.pas} · ${focus} ${pct(focusPred.home === focus ? focusPred.p : 1 - focusPred.p)}`)) : null) : null,
        h('section', {class: 'panel'}, sectionHead('Elo', 'δύναμη σε σχέση με το 1500'), h('div', {class: 'chart', 'data-chart': 'bars'})))),
    h('section', {class: 'panel'}, sectionHead('Τελευταία αποτελέσματα', 'πρόβλεψη του μοντέλου δίπλα στο πραγματικό σκορ', h('a', {href: '#/predictions'}, 'Ιστορικό →')),
      resultsTable(played.slice(0, 10))),
  ];
};

function standingsTable(compact) {
  const cols = [
    {label: '#', num: true, sort: r => r.pos, render: r => h('span', {class: 'pos' + (r.pos <= 8 ? ' top' : '')}, r.pos)},
    {label: 'Ομάδα', sort: r => r.team, render: r => tlink(r.team)},
    {label: 'Αγ', num: true, title: 'Αγώνες', sort: r => r.gp, render: r => r.gp},
    {label: 'Ν', num: true, title: 'Νίκες', sort: r => r.w, render: r => r.w},
    {label: 'Η', num: true, title: 'Ήττες', sort: r => r.l, render: r => r.l},
  ];
  if (!compact) cols.push(
    {label: 'Έδρα', num: true, title: 'Νίκες-ήττες εντός', sort: r => r.hw - r.hl, render: r => `${r.hw}-${r.hl}`},
    {label: 'Εκτός', num: true, title: 'Νίκες-ήττες εκτός', sort: r => r.aw - r.al, render: r => `${r.aw}-${r.al}`},
    {label: 'Υπ', num: true, title: 'Πόντοι υπέρ', sort: r => r.pf, render: r => r.pf},
    {label: 'Κατ', num: true, title: 'Πόντοι κατά', sort: r => r.pa, render: r => r.pa});
  cols.push(
    {label: '+/-', num: true, sort: r => r.diff, render: r => signed(r.diff)},
    {label: '%', num: true, sort: r => r.pct, render: r => Math.round(r.pct * 100) + '%'},
    {label: 'Φόρμα', render: r => formChips(r.form)});
  if (!compact) cols.push({label: 'Σερί', num: true, render: r => streakGr(r.streak)});
  cols.push({label: 'Elo', num: true, sort: r => r.elo, render: r => r.elo});
  return table(cols, D.standings, {sortIdx: 0, dir: 1, rowClass: r => r.team === focus ? 'is-focus' : null});
}

pages.standings = () => [
  pageBanner('Βαθμολογία', `${roundNo - 1} αγωνιστικές · κλικ στις επικεφαλίδες για ταξινόμηση`),
  h('section', {class: 'panel'}, standingsTable(false),
    h('p', {class: 'foot-note'}, 'Κλικ στις επικεφαλίδες για ταξινόμηση. Η σειρά βγαίνει από το ποσοστό νικών και μετά τη διαφορά πόντων, όπως στο feature του μοντέλου. Η επίσημη ΕΣΑΚΕ λύνει ισοβαθμίες με τα μεταξύ τους.')),
  h('div', {class: 'grid-2-even'},
    h('section', {class: 'panel'}, sectionHead('Elo', 'δύναμη σε σχέση με το 1500'), h('div', {class: 'chart', 'data-chart': 'bars'}),
      h('p', {class: 'foot-note'}, 'Σε κάθε νέα σεζόν το Elo επιστρέφει κατά 25% προς το 1500, λόγω αλλαγών στα ρόστερ. Κλικ σε μπάρα για τη σελίδα της ομάδας.')),
    h('section', {class: 'panel'}, sectionHead('Εξέλιξη Elo', `${focus} με μπλε · οι υπόλοιπες με γκρι`), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': focus}))),
];

pages.predictions = () => {
  const box = h('div');
  const st = {season: '', team: '', status: 'all', model: ''};
  const seasons = [...new Set(D.log.map(r => r.s))].sort().reverse();
  const versions = [...new Set(D.log.map(r => r.v))];
  const draw = () => {
    const rows = D.log.filter(r => (!st.season || r.s === st.season) && (!st.team || r.home === st.team || r.away === st.team)
      && (!st.model || r.v === st.model)
      && (st.status === 'all' || (st.status === 'ok' && r.ok === true) || (st.status === 'bad' && r.ok === false) || (st.status === 'pending' && r.ok === null)));
    const graded = rows.filter(r => r.ok !== null), ok = graded.filter(r => r.ok).length;
    const errs = graded.map(r => marginErr(r, r.ahs, r.aas));
    const mae = errs.length ? (errs.reduce((a, b) => a + b, 0) / errs.length).toFixed(1) : null;
    box.replaceChildren(
      h('p', {class: 'summary-line'}, graded.length ? `${ok}/${graded.length} σωστοί νικητές (${pct(ok / graded.length)}) · μέση απόκλιση διαφοράς ${mae} πόντοι · ${rows.length - graded.length} σε αναμονή` : `${rows.length} προβλέψεις σε αναμονή`),
      table([
        {label: 'Ημέρα', sort: r => r.d, render: r => dayLabel(r.d)},
        {label: 'Αγώνας', sort: r => r.home, render: r => h('span', null, tlink(r.home), ' – ', tlink(r.away))},
        {label: 'Πρόβλεψη', num: true, render: r => h('b', null, `${r.phs}–${r.pas}`)},
        {label: 'Νικητής (πιθ.)', title: 'Ο νικητής που διάλεξε και η πιθανότητα που του έδωσε', sort: r => Math.max(r.p, 1 - r.p), render: r => `${r.w} ${pct(r.w === r.home ? r.p : 1 - r.p)}`},
        {label: 'Αποτέλεσμα', num: true, render: r => r.ahs == null ? h('span', {class: 'muted'}, '–') : h('span', {class: 'score-cell'}, `${r.ahs}–${r.aas}`)},
        {label: 'Απόκλιση', num: true, title: 'Πόντοι μεταξύ προβλεπόμενης και πραγματικής διαφοράς', sort: r => r.ahs == null ? 999 : marginErr(r, r.ahs, r.aas), render: r => r.ahs == null ? '' : `${marginErr(r, r.ahs, r.aas)} π.`},
        {label: '', render: r => verdict(r.ok)},
        {label: 'Μοντέλο', render: r => h('span', {class: 'badge', style: 'margin:0', title: `καταγράφηκε ${r.at}`}, r.v)},
      ], rows, {sortIdx: 0, dir: -1, rowClass: r => isFocus(r.home, r.away) ? 'is-focus' : null, empty: 'Καμία πρόβλεψη με αυτά τα φίλτρα.'}));
  };
  const filters = h('div', {class: 'filters'},
    selectEl([['', 'Όλες οι σεζόν'], ...seasons.map(x => [x, x])], st.season, v => { st.season = v; draw(); }, 'Σεζόν'),
    selectEl([['', 'Όλες οι ομάδες'], ...TEAMS.slice().sort().map(t => [t, t])], st.team, v => { st.team = v; draw(); }, 'Ομάδα'),
    segCtrl([['all', 'Όλες'], ['ok', 'Σωστές'], ['bad', 'Λάθος'], ['pending', 'Σε αναμονή']], st.status, v => { st.status = v; draw(); }),
    versions.length > 1 ? selectEl([['', 'Όλα τα μοντέλα'], ...versions.map(v => [v, v])], st.model, v => { st.model = v; draw(); }, 'Μοντέλο') : null);
  draw();
  return [
    pageBanner('Προβλέψεις', 'Κάθε πρόβλεψη καταγράφεται πριν από τον αγώνα, με το ακριβές σκορ, και βαθμολογείται όταν βγει το αποτέλεσμα.'),
    h('section', null, sectionHead('Επόμενη αγωνιστική', D.next.length ? `${dayLabel(D.next[0].d)} – ${dayLabel(D.next[D.next.length - 1].d)} · μοντέλο ${D.model.version}` : ''),
      D.next.length ? h('div', {class: 'cards'}, D.next.map(predCard)) : h('p', {class: 'empty'}, 'Δεν υπάρχουν προγραμματισμένοι αγώνες.')),
    h('section', {class: 'panel'}, sectionHead('Ιστορικό προβλέψεων', 'καταγράφηκαν πριν από τους αγώνες'), filters, box,
      h('p', {class: 'foot-note'}, 'Κάθε γραμμή είναι πρόβλεψη που καταγράφηκε πριν από τον αγώνα, με το ακριβές σκορ που έδωσε το μοντέλο. Απόκλιση: πόσους πόντους απείχε η προβλεπόμενη διαφορά από την πραγματική. Το "ensemble-v1" είναι το παλιό μοντέλο, που χρησιμοποιήθηκε μέχρι 05/10/2026.')),
    h('section', {class: 'panel'}, sectionHead('Όλοι οι αγώνες της σεζόν', 'με την πρόβλεψη του μοντέλου'), resultsTable(seasonGames),
      h('p', {class: 'foot-note'}, '"Πριν τον αγώνα": καταγεγραμμένη πρόβλεψη. "Walk-forward": πρόβλεψη από μοντέλο εκπαιδευμένο μόνο σε προηγούμενους αγώνες, άρα κι αυτή εκτός δείγματος.')),
  ];
};

pages.teams = () => [
  pageBanner('Ομάδες', `${TEAMS.length} ομάδες · κλικ σε μια ομάδα για τη σελίδα της`),
  h('div', {class: 'team-grid'}, D.standings.map(r => h('a', {class: 'team-tile' + (r.team === focus ? ' is-focus' : ''), href: teamHref(r.team)},
    h('div', {class: 'tile-top'}, h('span', {class: 'tile-pos'}, `${r.pos}ος`), h('span', {class: 'muted small'}, `Elo ${r.elo}`)),
    h('div', {class: 'tile-name'}, crest(r.team, 38), h('span', null, r.team)),
    h('div', {class: 'tile-row'}, h('span', null, `${r.w}-${r.l} · ${signed(r.diff)}`), formChips(r.form))))),
];

pages.team = (name) => {
  const r = STANDING[name];
  if (!r) return [h('h1', null, 'Δεν βρέθηκε η ομάδα'), h('p', null, h('a', {href: '#/teams'}, '← Όλες οι ομάδες'))];
  const games = played.filter(g => g.home === name || g.away === name);
  const thisSeason = games.filter(g => g.s === season), lastSeason = games.filter(g => g.s !== season);
  const upcoming = D.upcoming.filter(u => u.home === name || u.away === name).slice(0, 8);
  const withPick = games.filter(g => g.pick);
  const okN = withPick.filter(g => g.pick.w === winnerOf(g)).length;
  return [
    h('section', {class: 'banner'}, h('div', {class: 'banner-inner'},
      h('div', null,
        h('div', {class: 'crumb'}, h('a', {href: '#/teams'}, 'Ομάδες'), ' / ', name),
        h('div', {class: 'team-banner-row'}, crest(name, 64),
          h('div', null, h('div', {class: 'eyebrow'}, `Stoiximan GBL · ${season}`), h('h1', null, name),
            h('p', {class: 'hero-sub'}, `${r.pos}ος στη βαθμολογία · ${r.w}-${r.l} · σερί ${streakGr(r.streak)}`)))),
      h('button', {class: 'btn btn-outline', type: 'button', onclick: () => setFocus(name), disabled: name === focus}, name === focus ? '★ Η ομάδα μου' : '☆ Ορισμός ως η ομάδα μου'))),
    h('section', {class: 'kpis'},
      kpi('Elo', String(r.elo), `${signed(r.elo - 1500)} από τον μέσο όρο`),
      kpi('Πόντοι / αγώνα', r.gp ? (r.pf / r.gp).toFixed(1) : '–', r.gp ? `δέχεται ${(r.pa / r.gp).toFixed(1)}` : ''),
      kpi('Έδρα · Εκτός', `${r.hw}-${r.hl} · ${r.aw}-${r.al}`, 'νίκες-ήττες'),
      kpi('Το μοντέλο στους αγώνες της', withPick.length ? `${okN}/${withPick.length}` : '–', 'σωστοί νικητές, όλες οι σεζόν')),
    h('div', {class: 'grid-2'},
      h('section', {class: 'panel'}, sectionHead('Επόμενοι αγώνες', null, h('a', {href: '#/schedule'}, 'Πρόγραμμα →')), upcoming.length ? upcoming.map(u => {
        const p = u.pi >= 0 ? D.next[u.pi] : null;
        return h('div', {class: 'sched-game'}, h('span', {class: 'muted small'}, dayLabel(u.d)),
          h('span', null, u.home === name ? 'vs ' : '@ ', tlink(u.home === name ? u.away : u.home), u.t ? h('span', {class: 'muted small'}, '  ' + u.t) : null),
          p ? h('span', {class: 'pchip'}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${name} ${pct(p.home === name ? p.p : 1 - p.p)}`) : h('span'));
      }) : h('p', {class: 'empty'}, 'Κανένας προγραμματισμένος αγώνας.')),
      h('section', {class: 'panel'}, sectionHead('Εξέλιξη Elo'), h('div', {class: 'chart', 'data-chart': 'lines', 'data-team': name}))),
    h('section', {class: 'panel'}, sectionHead('Αποτελέσματα ' + season, 'με την πρόβλεψη του μοντέλου'), resultsTable(thisSeason, {empty: 'Κανένας αγώνας ακόμα.'})),
    lastSeason.length ? h('details', {class: 'panel'}, h('summary', null, `Προηγούμενη σεζόν · ${lastSeason.length} αγώνες`), resultsTable(lastSeason)) : null,
  ];
};

pages.schedule = () => {
  const box = h('div');
  const months = [...new Set(D.upcoming.map(u => u.d.slice(0, 7)))];
  const st = {team: '', month: months[0] || ''};
  const draw = () => {
    const rows = D.upcoming.filter(u => st.team ? (u.home === st.team || u.away === st.team) : (!st.month || u.d.startsWith(st.month)));
    const byDay = {};
    rows.forEach(u => (byDay[u.d] = byDay[u.d] || []).push(u));
    box.replaceChildren(...(rows.length ? Object.entries(byDay).map(([d, us]) => h('div', {class: 'sched-day'}, h('div', {class: 'sched-date'}, fullDate(d)),
      us.map(u => {
        const p = u.pi >= 0 ? D.next[u.pi] : null;
        return h('div', {class: 'sched-game' + (isFocus(u.home, u.away) ? ' is-focus' : '')}, h('span', {class: 'muted'}, u.t || ''), h('span', {class: 'vs'}, tlink(u.home), h('span', {class: 'muted'}, '–'), tlink(u.away)),
          p ? h('span', {class: 'pchip', title: 'Πρόβλεψη μοντέλου'}, h('span', {class: 'dot'}), `${p.phs}–${p.pas} · ${p.w} ${pct(Math.max(p.p, 1 - p.p))}`) : h('span', {class: 'pchip muted'}, ''));
      }))) : [h('p', {class: 'empty'}, 'Κανένας αγώνας.')]));
  };
  const monthCtrl = segCtrl(months.map(mo => [mo, `${MONTHS[+mo.slice(5) - 1]} '${mo.slice(2, 4)}`]), st.month, v => { st.month = v; draw(); });
  const filters = h('div', {class: 'filters'},
    selectEl([['', 'Όλες οι ομάδες'], ...TEAMS.slice().sort().map(t => [t, t])], st.team, v => { st.team = v; monthCtrl.style.display = v ? 'none' : ''; draw(); }, 'Ομάδα'),
    monthCtrl);
  draw();
  return [pageBanner('Πρόγραμμα', `${D.upcoming.length} αγώνες μέχρι το τέλος της κανονικής περιόδου`),
    h('section', {class: 'panel'}, filters, box,
      h('p', {class: 'foot-note'}, 'Το μοντέλο προβλέπει μόνο την επόμενη αγωνιστική. Για αγώνες πιο μακριά, η φόρμα και τα ρόστερ θα έχουν αλλάξει μέχρι τότε. Διάλεξε ομάδα για να δεις όλο το πρόγραμμά της.'))];
};

pages.model = () => {
  const m = D.model;
  const wf = played.filter(g => g.pick && g.pick.src === 'wf');
  const bins = calibrationBins(wf);
  return [
    pageBanner('Το μοντέλο', `Έκδοση ${m.version} · πόσο καλά προβλέπει και πώς διαβάζονται τα νούμερα`),
    h('p', {class: 'lede'}, 'Ένα μοντέλο προβλέπει τη διαφορά πόντων του γηπεδούχου από τρία στοιχεία: τη διαφορά Elo (μαζί με την έδρα), τη διαφορά φόρμας στους 5 τελευταίους αγώνες και τη διαφορά ποσοστού νικών. Από αυτή τη διαφορά βγαίνουν και η πιθανότητα νίκης και το σκορ, οπότε δεν μπορούν να διαφωνούν. Ένα δεύτερο μοντέλο προβλέπει το σύνολο πόντων από τη φόρμα επίθεσης και άμυνας.'),
    h('section', {class: 'kpis'},
      kpi('Σωστός νικητής', pct(m.acc), `${m.n_test} αγώνες εκτός δείγματος · πάντα ο γηπεδούχος: ${pct(m.home_rate)}`),
      kpi('Log-loss', fx(m.ll), `χαμηλότερο = καλύτερο · Elo μόνο ${fx(m.elo_ll)}`),
      kpi('Brier', fx(m.brier), `0.25 = κορόνα-γράμματα · Elo μόνο ${fx(m.elo_brier)}`),
      kpi('Σφάλμα διαφοράς', `±${m.margin_mae}`, `πόντοι · σ = ${m.sigma} · R² ${fx(m.margin_r2, 2)}`)),
    h('div', {class: 'grid-2-even'},
      h('section', {class: 'panel'}, sectionHead('Βαθμονόμηση', 'αληθεύουν τα ποσοστά;'), h('div', {class: 'chart', 'data-chart': 'cal'}),
        h('details', null, h('summary', null, 'Πίνακας'), table([
          {label: 'Πιθανότητα φαβορί', render: b => `${pct(b.a)}–${pct(Math.min(1, b.b))}`},
          {label: 'Αγώνες', num: true, render: b => b.n},
          {label: 'Μέση πρόβλεψη', num: true, render: b => pct(b.sp / b.n)},
          {label: 'Νίκες φαβορί', num: true, render: b => pct(b.won / b.n)},
        ], bins)),
        h('p', {class: 'foot-note'}, 'Κάθε τελεία είναι μια ομάδα αγώνων με παρόμοια πιθανότητα για το φαβορί, και ο αριθμός δίπλα δείχνει πόσοι αγώνες είναι. Όσο πιο κοντά στη διαγώνιο, τόσο πιο αξιόπιστα είναι τα ποσοστά.')),
      h('section', {class: 'panel'}, sectionHead('Πώς διαβάζεται'),
        h('dl', {class: 'glossary'},
          h('dt', null, 'Walk-forward'), h('dd', null, `Μετά τους πρώτους ${m.warmup} αγώνες, το μοντέλο ξαναεκπαιδεύεται πριν από κάθε αγωνιστική μόνο με όσα έχουν ήδη παιχτεί, και προβλέπει την αγωνιστική. Είναι ακριβώς ο τρόπος που χρησιμοποιείται στην πράξη.`),
          h('dt', null, 'Πιθανότητα'), h('dd', null, `Φ(διαφορά / ${m.sigma}). Μια διαφορά +6 για τον γηπεδούχο αντιστοιχεί σε περίπου 69%.`),
          h('dt', null, '±πόντοι'), h('dd', null, 'Πόσο απέχει κατά μέσο όρο η προβλεπόμενη διαφορά από την πραγματική. Το μπάσκετ έχει πολύ θόρυβο, και ακόμα και τα στοιχηματικά γραφεία πέφτουν έξω κατά ~10 πόντους.'),
          h('dt', null, 'Log-loss · Brier'), h('dd', null, 'Βαθμολογούν τις πιθανότητες, όχι μόνο τον νικητή, και τιμωρούν περισσότερο ένα σίγουρο λάθος από ένα διστακτικό. Σε ~120 αγώνες, μια διαφορά 2-4 μονάδων στο ποσοστό επιτυχίας είναι θόρυβος, γι\'αυτό αυτοί οι δείκτες μετράνε περισσότερο.'),
          h('dt', null, 'Τύπος'), h('dd', null, `διαφορά = ${m.intercept} + ${m.coef[0]}×ΔElo + ${m.coef[1]}×Δφόρμα + ${m.coef[2]}×Δ%νικών`),
          h('dt', null, 'Εκδόσεις'), h('dd', null, `Κάθε πρόβλεψη καταγράφει ποιο μοντέλο την έκανε. Το "ensemble-v1" (ML + Elo) χρησιμοποιήθηκε μέχρι 05/10/2026, και από εκεί και πέρα το "${m.version}".`)))),
  ];
};

pages.help = () => [
  pageBanner('Οδηγίες', 'Όλα γίνονται με κλικ — χωρίς εντολές.'),
  h('section', {class: 'panel howto'}, sectionHead('Κάθε φορά'),
    h('ol', {class: 'steps'},
      h('li', null, h('b', null, 'Διπλό κλικ στο εικονίδιο «GBL Predictor»'), ' στην επιφάνεια εργασίας. Ανοίγει ένα μαύρο παράθυρο και, μετά από λίγα δευτερόλεπτα, αυτή η σελίδα. Αν έχουν περάσει πάνω από 6 ώρες από την τελευταία φορά, φέρνει πρώτα μόνο του τα νέα αποτελέσματα (περίπου 20 δευτερόλεπτα).'),
      h('li', null, h('b', null, 'Μην κλείσεις το μαύρο παράθυρο'), ' όσο χρησιμοποιείς τη σελίδα. Αυτό κάνει το κουμπί «Ανανέωση» να δουλεύει.'),
      h('li', null, 'Πάτα ', h('span', {class: 'kbd'}, '⟳ Ανανέωση'), ' πάνω δεξιά όποτε θέλεις τα πιο φρέσκα δεδομένα. Φέρνει αποτελέσματα και πρόγραμμα, ξαναεκπαιδεύει το μοντέλο, βγάζει προβλέψεις για την επόμενη αγωνιστική και τις καταγράφει.'),
      h('li', null, h('b', null, 'Τέλος:'), ' κλείσε τη σελίδα και το μαύρο παράθυρο.'))),
  h('section', {class: 'panel howto'}, sectionHead('Πότε να πατάς Ανανέωση'),
    h('p', null, h('b', null, 'Μία φορά μετά από κάθε αγωνιστική και πριν ξεκινήσει η επόμενη'), ', για παράδειγμα Δευτέρα με Παρασκευή. Έτσι οι προβλέψεις καταγράφονται πριν παιχτούν οι αγώνες, και το ρεκόρ στις «Προβλέψεις» είναι αληθινό.'),
    h('p', null, 'Δεν χρειάζεται να πατάς πολλές φορές. Το πρόγραμμα δεδομένων (API) έχει όριο 500 κλήσεων τον μήνα, και κάθε ανανέωση χρησιμοποιεί περίπου 6–8.')),
  h('section', {class: 'panel howto'}, sectionHead('Τι θα βρεις'),
    h('dl', {class: 'glossary'},
      h('dt', null, h('a', {class: 'tlink', href: '#/'}, 'Αρχική')), h('dd', null, 'Οι προβλέψεις της επόμενης αγωνιστικής, η βαθμολογία, η ομάδα σου και τα τελευταία αποτελέσματα, με την πρόβλεψη δίπλα σε κάθε σκορ.'),
      h('dt', null, h('a', {class: 'tlink', href: '#/predictions'}, 'Προβλέψεις')), h('dd', null, 'Όλες οι προβλέψεις που καταγράφηκαν πριν από τους αγώνες: το σκορ που έδωσε το μοντέλο, το πραγματικό αποτέλεσμα, πόσους πόντους απείχε, ✓ ή ✗. Έχει φίλτρα ανά ομάδα και σεζόν.'),
      h('dt', null, h('a', {class: 'tlink', href: '#/standings'}, 'Βαθμολογία')), h('dd', null, 'Πλήρης πίνακας. Κλικ σε μια επικεφαλίδα για ταξινόμηση. Έχει και το Elo κάθε ομάδας.'),
      h('dt', null, h('a', {class: 'tlink', href: '#/teams'}, 'Ομάδες')), h('dd', null, 'Κλικ σε μια ομάδα για τη σελίδα της: επόμενοι αγώνες, αποτελέσματα, εξέλιξη Elo. Κάθε όνομα ομάδας σε όλη τη σελίδα είναι link.'),
      h('dt', null, h('a', {class: 'tlink', href: '#/schedule'}, 'Πρόγραμμα')), h('dd', null, 'Όλοι οι αγώνες ανά μήνα ή ανά ομάδα.'),
      h('dt', null, h('a', {class: 'tlink', href: '#/model'}, 'Μοντέλο')), h('dd', null, 'Πόσο καλά προβλέπει και πώς διαβάζονται τα νούμερα.'),
      h('dt', null, 'Η ομάδα μου'), h('dd', null, 'Το μενού πάνω δεξιά τονίζει την ομάδα σου σε όλες τις σελίδες. Το κουμπί ◐ αλλάζει ανάμεσα σε φωτεινό και σκοτεινό θέμα.'))),
  h('section', {class: 'panel howto'}, sectionHead('Αν κάτι δεν πάει καλά'),
    h('dl', {class: 'glossary'},
      h('dt', null, '«API rejected the key»'), h('dd', null, 'Το κλειδί ή η συνδρομή στο RapidAPI έληξε. Μπες στο rapidapi.com, κάνε ξανά Subscribe στο FlashScore (δωρεάν πλάνο) και ζήτα από το Claude να βάλει το νέο κλειδί.'),
      h('dt', null, '«rate limit»'), h('dd', null, 'Τελείωσαν οι κλήσεις του μήνα. Η σελίδα δείχνει κανονικά τα τελευταία δεδομένα, και οι νέες κλήσεις ανανεώνονται τον επόμενο μήνα.'),
      h('dt', null, '«Unmapped team names»'), h('dd', null, 'Το API έφερε όνομα ομάδας που δεν αναγνωρίζεται. Συμβαίνει συνήθως με νέες ομάδες. Πες στο Claude να το προσθέσει.'),
      h('dt', null, 'Το κουμπί δεν κάνει τίποτα'), h('dd', null, 'Η σελίδα άνοιξε απευθείας από αρχείο και όχι από το εικονίδιο. Κλείσε την και άνοιξέ την από το «GBL Predictor».'),
      h('dt', null, 'Δεν ανοίγει τίποτα'), h('dd', null, 'Διάβασε τι γράφει το μαύρο παράθυρο και στείλε το στο Claude.'))),
];

// ---------------------------------------------------------------- refresh button
const toast = document.getElementById('toast');
let toastTimer;
function showToast(msg, kind, ms) {
  toast.textContent = msg; toast.className = 'toast' + (kind ? ' ' + kind : ''); toast.hidden = false;
  clearTimeout(toastTimer); if (ms) toastTimer = setTimeout(() => { toast.hidden = true; }, ms);
}
const refreshBtn = document.getElementById('refresh');
const resetBtn = () => { refreshBtn.disabled = false; refreshBtn.textContent = '⟳ Ανανέωση'; };
refreshBtn.addEventListener('click', async () => {
  if (!location.protocol.startsWith('http')) {
    showToast('Για να δουλέψει η Ανανέωση, άνοιξε τη σελίδα από το εικονίδιο «GBL Predictor» στην επιφάνεια εργασίας.', 'bad', 9000);
    return;
  }
  refreshBtn.disabled = true; refreshBtn.textContent = '⟳ Ανανέωση…';
  showToast('Φέρνω νέα αποτελέσματα, εκπαιδεύω το μοντέλο και βγάζω προβλέψεις… (~20 δευτερόλεπτα)');
  try {
    const res = await fetch('/api/refresh', {method: 'POST', headers: {'X-GBL-Refresh': '1'}});
    const body = await res.json();
    if (body.ok) { showToast('Έτοιμο!\n' + body.message, 'good'); setTimeout(() => location.reload(), 1600); }
    else { showToast('Κάτι δεν πήγε καλά:\n' + body.message + '\n\nΔες τις «Οδηγίες» στο μενού.', 'bad'); resetBtn(); }
  } catch (err) {
    showToast('Δεν βρέθηκε το πρόγραμμα. Μήπως έκλεισε το μαύρο παράθυρο; Άνοιξε ξανά το «GBL Predictor».', 'bad');
    resetBtn();
  }
});

// ---------------------------------------------------------------- router
const NAV = [['', 'Αρχική'], ['predictions', 'Προβλέψεις'], ['standings', 'Βαθμολογία'], ['teams', 'Ομάδες'], ['schedule', 'Πρόγραμμα'], ['model', 'Μοντέλο'], ['help', 'Οδηγίες']];
const nav = document.getElementById('nav');
nav.replaceChildren(...NAV.map(([k, label]) => h('a', {href: '#/' + k, 'data-k': k}, label)));
document.getElementById('brand-season').textContent = `STOIXIMAN GBL · ${season}`;
if (D.league_logo) document.getElementById('brand-badge').append(h('img', {src: D.league_logo, alt: ''}));
document.getElementById('foot-brand').append(D.league_logo ? h('img', {src: D.league_logo, alt: ''}) : '', 'GBL Predictor');
document.getElementById('foot').textContent = `Δεδομένα & σήματα: FlashScore (RapidAPI) · μοντέλο ${D.model.version} · ενημέρωση ${D.updated} · ανεπίσημη εφαρμογή, χωρίς σχέση με την ΕΣΑΚΕ`;

function drawCharts() {
  app.querySelectorAll('[data-chart]').forEach(c => {
    if (c.dataset.chart === 'bars') eloBars(c);
    else if (c.dataset.chart === 'lines') eloLines(c, c.dataset.team || focus);
    else if (c.dataset.chart === 'cal') calibration(c, played.filter(g => g.pick && g.pick.src === 'wf'));
  });
}
function route(scrollTop) {
  hideTip();
  const raw = location.hash.replace(/^#\/?/, '');
  const [k, ...rest] = raw.split('/');
  const teamName = k === 'team' ? decodeURIComponent(rest.join('/')) : null;
  const view = teamName !== null ? pages.team(teamName) : (pages[k] || pages.home)();
  app.replaceChildren(...[].concat(view).filter(Boolean));
  app.classList.remove('enter'); void app.offsetWidth; app.classList.add('enter');
  const active = teamName !== null ? 'teams' : (pages[k] ? k : '');
  nav.querySelectorAll('a').forEach(a => a.classList.toggle('active', a.dataset.k === active || (active === 'home' && a.dataset.k === '')));
  document.title = `${teamName || (NAV.find(n => n[0] === active) || NAV[0])[1]} · GBL Predictor`;
  drawCharts();
  if (scrollTop) window.scrollTo({top: 0});
}
function setFocus(t) {
  focus = t; localStorage.setItem('gbl-focus', t);
  document.getElementById('focus').value = t;
  route(false);
}

const sel = document.getElementById('focus');
sel.replaceChildren(...TEAMS.slice().sort().map(t => h('option', {value: t, selected: t === focus}, t)));
sel.addEventListener('change', e => setFocus(e.target.value));

const saved = localStorage.getItem('gbl-theme'); if (saved) root.dataset.theme = saved;
document.getElementById('theme').addEventListener('click', () => {
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark'; localStorage.setItem('gbl-theme', root.dataset.theme); drawCharts();
});

addEventListener('hashchange', () => route(true));
let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(drawCharts, 120); });
route(false);
})();
"""
