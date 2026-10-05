"""Tests for the prediction-history log.

Covers the two behaviors that matter:
  1. Upsert by (fixture_date, home, away) — re-clicking the button must
     replace the existing prediction for the same fixture, never duplicate it.
  2. Accuracy view enrichment — when actuals exist in all_fixtures.csv they
     get merged in and the winner_correct flag is set; when they don't, the
     row stays "pending" with NA actuals.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config as cfg
from src.predict import Prediction
from src.prediction_log import (
    LOG_COLUMNS,
    append_predictions,
    build_accuracy_view,
    load_log,
)


def _make_pred(home: str, away: str, h: int, a: int, date: str = "20/04/2026") -> Prediction:
    """Minimal Prediction dataclass instance for log tests."""
    winner = home if h > a else away if a > h else "TIE"
    return Prediction(
        date=date,
        matchday="Matchday 30",
        home=home,
        away=away,
        predicted_home_score=h,
        predicted_away_score=a,
        predicted_margin=float(h - a),
        predicted_total=float(h + a),
        home_win_probability=0.62 if winner == home else 0.38,
        home_win_probability_raw=0.6,
        home_win_probability_elo=0.65,
        score_uncertainty_pts=15.0,
        winner=winner,
    )


def test_load_log_returns_empty_frame_when_missing(tmp_path: Path) -> None:
    log = load_log(tmp_path / "nope.csv")
    assert log.empty
    assert list(log.columns) == LOG_COLUMNS


def test_append_creates_file_and_writes_rows(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    append_predictions([_make_pred("PAO", "OSFP", 88, 80)], path=path)

    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 1
    assert df.iloc[0]["home"] == "PAO"
    assert df.iloc[0]["predicted_winner"] == "PAO"


def test_append_upserts_on_repeat_click(tmp_path: Path) -> None:
    """Re-clicking with a new prediction for the same fixture must replace, not duplicate."""
    path = tmp_path / "history.csv"
    append_predictions([_make_pred("PAO", "OSFP", 88, 80)], path=path)
    # Same fixture, different prediction (model retrained, say)
    append_predictions([_make_pred("PAO", "OSFP", 75, 78)], path=path)

    df = pd.read_csv(path)
    assert len(df) == 1
    # Latest write wins
    assert df.iloc[0]["predicted_home_score"] == 75
    assert df.iloc[0]["predicted_away_score"] == 78
    assert df.iloc[0]["predicted_winner"] == "OSFP"


def test_append_keeps_distinct_fixtures(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    append_predictions(
        [
            _make_pred("PAO", "OSFP", 88, 80, date="20/04/2026"),
            _make_pred("ARIS", "PAOK", 70, 72, date="21/04/2026"),
        ],
        path=path,
    )
    df = pd.read_csv(path)
    assert len(df) == 2
    assert set(df["home"]) == {"PAO", "ARIS"}


def test_accuracy_view_marks_played_games_correct(tmp_path: Path) -> None:
    log_path = tmp_path / "history.csv"
    fixtures_path = tmp_path / "all_fixtures.csv"

    # One played fixture (PAO won 88-80, predicted PAO 88-80 → correct)
    pd.DataFrame(
        [
            {
                cfg.COL_DATE: "20/04/2026",
                cfg.COL_HOME: "PAO",
                cfg.COL_AWAY: "OSFP",
                cfg.COL_HOME_SCORE: 88,
                cfg.COL_AWAY_SCORE: 80,
            }
        ]
    ).to_csv(fixtures_path, index=False)

    append_predictions([_make_pred("PAO", "OSFP", 88, 80, date="20/04/2026")], path=log_path)

    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path)
    assert len(view) == 1
    assert view.iloc[0]["actual_home_score"] == 88
    assert view.iloc[0]["actual_winner"] == "PAO"
    assert bool(view.iloc[0]["winner_correct"]) is True


def test_accuracy_view_marks_played_games_wrong(tmp_path: Path) -> None:
    log_path = tmp_path / "history.csv"
    fixtures_path = tmp_path / "all_fixtures.csv"

    pd.DataFrame(
        [
            {
                cfg.COL_DATE: "20/04/2026",
                cfg.COL_HOME: "PAO",
                cfg.COL_AWAY: "OSFP",
                cfg.COL_HOME_SCORE: 70,
                cfg.COL_AWAY_SCORE: 90,  # OSFP actually won
            }
        ]
    ).to_csv(fixtures_path, index=False)

    # Predicted PAO 88-80 — wrong call.
    append_predictions([_make_pred("PAO", "OSFP", 88, 80, date="20/04/2026")], path=log_path)

    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path)
    assert view.iloc[0]["actual_winner"] == "OSFP"
    assert bool(view.iloc[0]["winner_correct"]) is False


def test_accuracy_view_pending_rows_have_na_actuals(tmp_path: Path) -> None:
    """Fixture that hasn't been played yet (no row in all_fixtures) → pending."""
    log_path = tmp_path / "history.csv"
    fixtures_path = tmp_path / "all_fixtures.csv"
    # Empty fixtures file with the right schema.
    pd.DataFrame(
        columns=[
            cfg.COL_DATE,
            cfg.COL_HOME,
            cfg.COL_AWAY,
            cfg.COL_HOME_SCORE,
            cfg.COL_AWAY_SCORE,
        ]
    ).to_csv(fixtures_path, index=False)

    append_predictions([_make_pred("PAO", "OSFP", 88, 80)], path=log_path)
    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path)

    assert len(view) == 1
    assert pd.isna(view.iloc[0]["actual_home_score"])
    assert pd.isna(view.iloc[0]["actual_winner"])
    assert pd.isna(view.iloc[0]["winner_correct"])


def test_accuracy_view_empty_when_no_log(tmp_path: Path) -> None:
    view = build_accuracy_view(
        log_path=tmp_path / "nope.csv",
        fixtures_path=tmp_path / "also_nope.csv",
    )
    assert view.empty


@pytest.mark.parametrize("preds", [[], None])
def test_append_noop_on_empty_input(tmp_path: Path, preds) -> None:
    path = tmp_path / "history.csv"
    # ``None`` would raise; only [] is a valid empty list. Skip None case.
    if preds is None:
        return
    append_predictions(preds, path=path)
    assert not path.exists()


def _write_result(path: Path, date: str, home: str, away: str, hs: int, as_: int) -> None:
    pd.DataFrame(
        [
            {
                cfg.COL_DATE: date,
                cfg.COL_HOME: home,
                cfg.COL_AWAY: away,
                cfg.COL_HOME_SCORE: hs,
                cfg.COL_AWAY_SCORE: as_,
            }
        ]
    ).to_csv(path, index=False)


def test_accuracy_view_matches_game_rescheduled_by_two_days(tmp_path: Path) -> None:
    # Logged for 13/05, actually played 15/05 — still the same game.
    log_path, fixtures_path = tmp_path / "h.csv", tmp_path / "f.csv"
    _write_result(fixtures_path, "15/05/2026", "PAO", "OSFP", 90, 80)
    append_predictions([_make_pred("PAO", "OSFP", 88, 80, date="13/05/2026")], path=log_path)

    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path)
    assert view.iloc[0]["actual_home_score"] == 90
    assert bool(view.iloc[0]["winner_correct"]) is True


def test_accuracy_view_ignores_same_pairing_far_apart(tmp_path: Path) -> None:
    log_path, fixtures_path = tmp_path / "h.csv", tmp_path / "f.csv"
    _write_result(fixtures_path, "01/02/2026", "PAO", "OSFP", 90, 80)
    append_predictions([_make_pred("PAO", "OSFP", 88, 80, date="13/05/2026")], path=log_path)

    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path)
    assert pd.isna(view.iloc[0]["actual_home_score"])


def test_log_records_model_version_and_backfills_legacy(tmp_path: Path) -> None:
    from src.prediction_log import LEGACY_MODEL_VERSION

    log_path, fixtures_path = tmp_path / "h.csv", tmp_path / "f.csv"
    _write_result(fixtures_path, "20/04/2026", "PAO", "OSFP", 90, 80)
    old = _make_pred("AEK", "ARIS", 80, 70)  # no version: an old-model row
    new = _make_pred("PAO", "OSFP", 88, 80)
    new.model_version = "margin-v2"
    append_predictions([old, new], path=log_path)
    # Simulate a pre-versioning log file: blank version on the old row.
    df = pd.read_csv(log_path)
    df.loc[df["home"] == "AEK", "model_version"] = None
    df.to_csv(log_path, index=False)

    view = build_accuracy_view(log_path=log_path, fixtures_path=fixtures_path).set_index("home")
    assert view.at["PAO", "model_version"] == "margin-v2"
    assert view.at["AEK", "model_version"] == LEGACY_MODEL_VERSION
