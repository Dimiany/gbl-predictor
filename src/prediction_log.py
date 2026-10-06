"""Persistent log of predictions made via the 'Generate Predictions' button.

Each click upserts rows into ``data/prediction_history.csv`` keyed on
(fixture_date, home, away) — so the latest prediction for a given fixture
wins, and the file size grows with the number of fixtures predicted, not
the number of clicks.

When the game is later played and the result lands in
``data/raw/all_fixtures.csv``, the accuracy view joins them back together
to show predicted vs. actual side-by-side. That join happens at display
time, so the log file stays simple (predictions only, no actuals duplicated).

This is the "live model accuracy" feed — distinct from the walk-forward
backtest, which is internal evaluation. The numbers here reflect what the
deployed model actually said about real upcoming fixtures.

A row whose ``prediction_made_at`` is after its fixture date is retroactive
(``predict_retroactively``: a missed round re-predicted from pre-round data).
The site labels those and keeps them out of the pre-game record.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config as cfg
from src.features import build_features
from src.model import _fit_bundle
from src.predict import Fixture, Prediction, predict_fixtures

PREDICTION_LOG_CSV: Path = cfg.DATA_DIR / "prediction_history.csv"

LOG_COLUMNS = [
    "fixture_date",
    "home",
    "away",
    "predicted_home_score",
    "predicted_away_score",
    "predicted_winner",
    "home_win_probability",
    "prediction_made_at",
    # Which model made the prediction (cfg.MODEL_VERSION). Blank on rows
    # logged before versioning existed — those came from "ensemble-v1".
    "model_version",
]

# Version label for log rows written before the column existed.
LEGACY_MODEL_VERSION = "ensemble-v1"

# A logged fixture still matches its result if the game was moved by up to
# this many days (FlashScore schedules shift; the teams are what identify it).
RESCHEDULE_TOLERANCE_DAYS = 3

_KEY_COLS = ["fixture_date", "home", "away"]


def load_log(path: Path = PREDICTION_LOG_CSV) -> pd.DataFrame:
    """Return the prediction history DataFrame, or an empty frame if missing."""
    if not path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.read_csv(path)


def append_predictions(
    preds: list[Prediction],
    path: Path = PREDICTION_LOG_CSV,
    overwrite: bool = True,
) -> None:
    """Upsert predictions into the log keyed on (fixture_date, home, away).

    Latest write wins — re-clicking the button after retraining replaces the
    older prediction for the same fixture rather than appending a duplicate.
    ``overwrite=False`` only adds fixtures not logged yet (used for
    retroactive rows, which must never replace a real pre-game prediction).
    """
    if not overwrite:
        logged = set(load_log(path)[_KEY_COLS].astype(str).itertuples(index=False, name=None))
        preds = [p for p in preds if (p.date, p.home, p.away) not in logged]
    if not preds:
        return

    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = pd.DataFrame(
        [
            {
                "fixture_date": p.date,
                "home": p.home,
                "away": p.away,
                "predicted_home_score": p.predicted_home_score,
                "predicted_away_score": p.predicted_away_score,
                "predicted_winner": p.winner,
                "home_win_probability": round(p.home_win_probability, 4),
                "prediction_made_at": now,
                "model_version": p.model_version,
            }
            for p in preds
        ]
    )

    existing = load_log(path)
    merged = pd.concat([existing, new_rows], ignore_index=True)
    # keep="last" makes the freshest write win — exactly what we want.
    merged = merged.drop_duplicates(subset=_KEY_COLS, keep="last").reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)


def predict_retroactively(
    start: pd.Timestamp,
    end: pd.Timestamp,
    history: pd.DataFrame | None = None,
) -> list[Prediction]:
    """Predict already-played games as the model would have before they began.

    The model is fit only on games strictly before ``start``, and every game in
    [start, end] is predicted from that same pre-round state, so no result from
    inside the window (or after it) leaks into any prediction.
    """
    if history is None:
        history = pd.read_csv(cfg.RAW_GAMES_CSV)
    dates = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    before = history[dates < start].reset_index(drop=True)
    window = history[(dates >= start) & (dates <= end)]
    if window.empty or before.empty:
        return []
    bundle = _fit_bundle(build_features(before))
    fixtures = [
        Fixture(date=d.strftime("%d/%m/%Y"), matchday="", home=h, away=a)
        for d, h, a in zip(
            dates[window.index], window[cfg.COL_HOME], window[cfg.COL_AWAY], strict=True
        )
    ]
    # Teams with no games before the window were promoted into it: real teams,
    # not typos (window names come from history, which only sync writes).
    promoted = {f.home for f in fixtures} | {f.away for f in fixtures}
    promoted -= set(before[cfg.COL_HOME]) | set(before[cfg.COL_AWAY])
    return predict_fixtures(
        fixtures, list(dates[window.index]), history=before, bundle=bundle, promoted=promoted
    )


def _match_rescheduled(log: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Fill actuals for logged fixtures whose game was played a few days off.

    The exact-date join misses games FlashScore rescheduled after we logged
    the prediction. Same home + away within RESCHEDULE_TOLERANCE_DAYS is the
    same game (a pairing meets at most twice a season, months apart).
    """
    missing = log["actual_home_score"].isna()
    for i in log.index[missing]:
        same = actuals[
            (actuals["home"] == log.at[i, "home"]) & (actuals["away"] == log.at[i, "away"])
        ]
        if same.empty:
            continue
        gap = (same["_fixture_date_dt"] - log.at[i, "_fixture_date_dt"]).abs()
        best = gap.idxmin()
        if gap[best] <= pd.Timedelta(days=RESCHEDULE_TOLERANCE_DAYS):
            log.at[i, "actual_home_score"] = same.at[best, "actual_home_score"]
            log.at[i, "actual_away_score"] = same.at[best, "actual_away_score"]
    return log


def build_accuracy_view(
    log_path: Path = PREDICTION_LOG_CSV,
    fixtures_path: Path = cfg.RAW_GAMES_CSV,
) -> pd.DataFrame:
    """Return the prediction log enriched with actuals + correctness flags.

    Rows where the fixture has been played get ``actual_home_score`` /
    ``actual_away_score`` / ``actual_winner`` / ``winner_correct`` filled in.
    Rows for unplayed fixtures keep those columns as NA — the renderer uses
    that to show a "pending" card.
    """
    log = load_log(log_path)
    if log.empty:
        return log
    if "model_version" not in log.columns:
        log["model_version"] = pd.NA
    log["model_version"] = log["model_version"].fillna(LEGACY_MODEL_VERSION)

    # Parse log dates with dayfirst=True (European format) to match the rest
    # of the project — matters for the join key below.
    log["_fixture_date_dt"] = pd.to_datetime(log["fixture_date"], dayfirst=True)

    if fixtures_path.exists():
        fixtures = pd.read_csv(fixtures_path)
        fixtures[cfg.COL_DATE] = pd.to_datetime(fixtures[cfg.COL_DATE], dayfirst=True)
        actuals = fixtures[
            [cfg.COL_DATE, cfg.COL_HOME, cfg.COL_AWAY, cfg.COL_HOME_SCORE, cfg.COL_AWAY_SCORE]
        ].rename(
            columns={
                cfg.COL_DATE: "_fixture_date_dt",
                cfg.COL_HOME: "home",
                cfg.COL_AWAY: "away",
                cfg.COL_HOME_SCORE: "actual_home_score",
                cfg.COL_AWAY_SCORE: "actual_away_score",
            }
        )
        log = log.merge(actuals, on=["_fixture_date_dt", "home", "away"], how="left")
        log = _match_rescheduled(log, actuals)
    else:
        log["actual_home_score"] = pd.NA
        log["actual_away_score"] = pd.NA

    # actual_winner only meaningful when both scores are present.
    played = log["actual_home_score"].notna() & log["actual_away_score"].notna()
    log["actual_winner"] = pd.NA
    log.loc[played & (log["actual_home_score"] > log["actual_away_score"]), "actual_winner"] = log[
        "home"
    ]
    log.loc[played & (log["actual_home_score"] < log["actual_away_score"]), "actual_winner"] = log[
        "away"
    ]
    log.loc[played & (log["actual_home_score"] == log["actual_away_score"]), "actual_winner"] = (
        "TIE"
    )

    log["winner_correct"] = pd.NA
    log.loc[played, "winner_correct"] = (
        log.loc[played, "predicted_winner"] == log.loc[played, "actual_winner"]
    )

    # Most recent fixture first — the user opens this page to see "how did the
    # model just do?" more often than to scan ancient predictions.
    log = log.sort_values("_fixture_date_dt", ascending=False).reset_index(drop=True)
    return log.drop(columns=["_fixture_date_dt"])
