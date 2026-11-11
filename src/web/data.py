"""Data assembly for the site: every number the pages show, as one JSON-able dict.

``build_dashboard(bundle)`` returns ``(data, next_round_predictions)``. The dict is
embedded in the page by ``src.web.render`` and read by the JavaScript in
``src/web/assets/js``. Keep it JSON-safe (no NaN) — ``JSON.parse`` rejects NaN.

Every played game carries the model's pre-game call ("pick"): the logged
prediction when one exists, otherwise the walk-forward one (also out-of-sample —
that model never saw the game).
"""

from __future__ import annotations

import base64
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

from src import config as cfg
from src.features import build_features, elo_update, game_k, season_of, team_state_snapshot
from src.model import PredictorBundle
from src.predict import Prediction, load_fixtures_from_csv, next_round, predict_fixtures
from src.prediction_log import RESCHEDULE_TOLERANCE_DAYS, build_accuracy_view
from src.simulate import simulate_season
from src.web.render import slug

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
        k = game_k(int(g["home_games_played"]), int(g["away_games_played"]))
        home_post, away_post = elo_update(home_pre, away_pre, int(g[cfg.COL_HOME_WIN]), k=k)
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
        made_at = pd.Timestamp(r["prediction_made_at"])
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
                # Made after the game day: re-predicted from pre-round data
                # (prediction_log.predict_retroactively), not a pre-game record.
                "retro": bool(made_at.normalize() > d),
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
                src = "retro" if r["retro"] else "log"
                pick = {k: r[k] for k in ("phs", "pas", "p", "w", "v")} | {"src": src}
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


def site_settings(mode: str | None = None) -> dict:
    """Which build this is (cfg.SITE_MODE) and how its contact form sends.

    Public builds post the form straight to Firestore (REST, no SDK); the
    collection is per mode, so preview links never mix with real messages.
    """
    mode = mode or cfg.SITE_MODE
    if mode not in cfg.SITE_MODES:
        raise ValueError(f"GBL_SITE_MODE must be one of {cfg.SITE_MODES}, got {mode!r}")
    firestore = None
    if mode != "local" and cfg.FIREBASE_PROJECT_ID and cfg.FIREBASE_API_KEY:
        firestore = {
            "project": cfg.FIREBASE_PROJECT_ID,
            "key": cfg.FIREBASE_API_KEY,
            "collection": cfg.CONTACT_COLLECTIONS[mode],
        }
    return {"mode": mode, "cloud_sync": cfg.CLOUD_SYNC, "firestore": firestore}


def crest_file(team: str) -> Path:
    """Where scripts/fetch_crests.py stores a team's official crest."""
    return cfg.CRESTS_DIR / f"{slug(team)}.webp"


def _team_logos() -> dict[str, str]:
    """Canonical team name -> crest address.

    Preference: the official crest in assets/crests (192 px, served as a file the
    browser caches; build.write_site_files copies the folder), then FlashScore's
    100x100 crest, then its 30x30 list image (both inlined).
    """
    if not cfg.TEAM_LOGOS_CSV.exists():
        return {}
    logos = pd.read_csv(cfg.TEAM_LOGOS_CSV, dtype=str, keep_default_na=False)
    if "crest_url" not in logos.columns:
        logos["crest_url"] = ""
    out = {}
    for team, small, large in zip(
        logos["team"], logos["logo_url"], logos["crest_url"], strict=True
    ):
        official = crest_file(team)
        if official.exists():
            out[team] = f"/{cfg.CRESTS_DIR.name}/{official.name}"
            continue
        uri = _image_data_uri(large) or _image_data_uri(small)
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


def _projection(
    standings: list[dict],
    fixtures: list,
    dates: list[pd.Timestamp],
    season: int,
    bundle: PredictorBundle,
) -> dict | None:
    """Title / playoff / relegation chances from simulating this season's remaining
    fixtures (src/simulate.py). The margins come from the same model as the next-round
    predictions, computed once from today's team states. None when something is off
    (an unmapped team name in a far fixture must not block the build)."""
    left = [(f, d) for f, d in zip(fixtures, dates, strict=True) if season_of(d) == season]
    try:
        preds = (
            predict_fixtures([f for f, _ in left], [d for _, d in left], bundle=bundle)
            if left
            else []
        )
    except ValueError:
        return None
    sigma = float(bundle.metrics.get("margin_rmse", bundle.margin_sigma))
    return simulate_season(
        {r["team"]: (r["w"], r["l"], r["diff"]) for r in standings},
        [(p.home, p.away, p.predicted_margin) for p in preds],
        sigma,
    )


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
    projection = _projection(standings, fixtures, dates, season, bundle)
    m = bundle.metrics

    data = {
        "season": _season_label(season),
        "updated": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M"),
        "last_game": history[cfg.COL_DATE].max().strftime("%Y-%m-%d"),
        "focus": DEFAULT_FOCUS_TEAM
        if any(r["team"] == DEFAULT_FOCUS_TEAM for r in standings)
        else (standings[0]["team"] if standings else ""),
        "standings": standings,
        "projection": projection,
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
        "contact_email": cfg.CONTACT_EMAIL,
        "site": site_settings(),
        "logos": _team_logos(),
        "league_logo": _image_data_uri(cfg.LEAGUE_LOGO_URL),
        "brand": {
            "name": cfg.SITE_NAME,
            "tagline": cfg.SITE_TAGLINE,
            "slogan": cfg.SITE_SLOGAN,
            "url": cfg.SITE_URL,
        },
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
            "margin_rmse": _num(m.get("margin_rmse"), 1),
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
