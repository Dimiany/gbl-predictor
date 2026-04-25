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
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config as cfg
from src.predict import Prediction

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
]

_KEY_COLS = ["fixture_date", "home", "away"]


def load_log(path: Path = PREDICTION_LOG_CSV) -> pd.DataFrame:
    """Return the prediction history DataFrame, or an empty frame if missing."""
    if not path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.read_csv(path)


def append_predictions(
    preds: list[Prediction],
    path: Path = PREDICTION_LOG_CSV,
) -> None:
    """Upsert predictions into the log keyed on (fixture_date, home, away).

    Latest write wins — re-clicking the button after retraining replaces the
    older prediction for the same fixture rather than appending a duplicate.
    """
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
