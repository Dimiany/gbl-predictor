"""Tests for fixture loading and team-name validation.

These tests protect the main *user-facing* failure modes: a bad fixture CSV
or a typo'd team name. Both of those are easy to introduce and (without
validation) produce silently wrong predictions, so catching them here is
worth the lines of code.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import config as cfg
from src.predict import (
    Fixture,
    load_fixtures_from_csv,
    validate_team_names,
)

# ---------------------------------------------------------------------------
# Tiny synthetic history we can reuse across tests
# ---------------------------------------------------------------------------


def _history() -> pd.DataFrame:
    """Small games DataFrame with three known teams."""
    # Dates in dd/mm/yyyy — matches the project's CSV format.
    return pd.DataFrame(
        [
            ("04/10/2025", "Panathinaikos", "Olympiacos", 90, 85),
            ("05/10/2025", "Olympiacos", "PAOK", 80, 78),
            ("11/10/2025", "PAOK", "Panathinaikos", 70, 88),
        ],
        columns=[cfg.COL_DATE, cfg.COL_HOME, cfg.COL_AWAY, cfg.COL_HOME_SCORE, cfg.COL_AWAY_SCORE],
    )


# ---------------------------------------------------------------------------
# validate_team_names
# ---------------------------------------------------------------------------


def test_validate_passes_for_known_teams():
    # Both teams exist in history → no exception.
    fixtures = [Fixture("01 Jan", "MD1", "Panathinaikos", "PAOK")]
    validate_team_names(fixtures, _history())  # must not raise


def test_validate_raises_for_unknown_team():
    fixtures = [Fixture("01 Jan", "MD1", "Panathinaikos", "SomeTeamThatDoesntExist")]
    with pytest.raises(ValueError) as exc_info:
        validate_team_names(fixtures, _history())
    # The error message should name the offending team so the user knows
    # which row in their fixtures CSV to fix.
    assert "SomeTeamThatDoesntExist" in str(exc_info.value)


def test_validate_suggests_close_match_for_typo():
    # "Olympiakos" is a common misspelling of the correct "Olympiacos".
    # We expect the error message to include a "did you mean" hint.
    fixtures = [Fixture("01 Jan", "MD1", "Olympiakos", "PAOK")]
    with pytest.raises(ValueError) as exc_info:
        validate_team_names(fixtures, _history())
    msg = str(exc_info.value)
    assert "did you mean" in msg
    assert "Olympiacos" in msg


def test_validate_reports_all_bad_names_at_once():
    # If multiple fixtures are bad, the user sees ALL the problems in one
    # error message — not "fix this, retry, fix that, retry" one by one.
    fixtures = [
        Fixture("01 Jan", "MD1", "Bogus1", "PAOK"),
        Fixture("02 Jan", "MD1", "Panathinaikos", "Bogus2"),
    ]
    with pytest.raises(ValueError) as exc_info:
        validate_team_names(fixtures, _history())
    msg = str(exc_info.value)
    assert "Bogus1" in msg
    assert "Bogus2" in msg


# ---------------------------------------------------------------------------
# load_fixtures_from_csv
# ---------------------------------------------------------------------------


def test_load_fixtures_parses_rows(tmp_path):
    # tmp_path is a pytest fixture — a fresh directory that's cleaned up
    # automatically. Perfect for testing file I/O without leaving junk behind.
    csv_path = tmp_path / "fixtures.csv"
    csv_path.write_text(
        "fixture_date,matchday,home_team,away_team\n"
        "15/04/2026,Matchday 21,Panathinaikos,PAOK\n"
        "18/04/2026,Matchday 25,Olympiacos,PAOK\n"
    )
    fixtures, dates = load_fixtures_from_csv(csv_path)
    assert len(fixtures) == 2
    assert fixtures[0].home == "Panathinaikos"
    assert fixtures[0].away == "PAOK"
    # Dates must parse into proper Timestamps so the rest-days feature works.
    # pd.Timestamp ISO constructor gives us an unambiguous date to compare against.
    assert dates[0] == pd.Timestamp("2026-04-15")


def test_load_fixtures_skips_blank_rows(tmp_path):
    # Users often leave placeholder rows in the CSV; we don't want those
    # to crash the pipeline or turn into "predict TBD vs TBD" rows.
    csv_path = tmp_path / "fixtures.csv"
    csv_path.write_text(
        "fixture_date,matchday,home_team,away_team\n"
        "15/04/2026,Matchday 21,Panathinaikos,PAOK\n"
        "20/04/2026,Matchday 26,,\n"
    )
    fixtures, _ = load_fixtures_from_csv(csv_path)
    assert len(fixtures) == 1


def test_load_fixtures_raises_on_missing_column(tmp_path):
    # If a user accidentally deletes the `matchday` column, fail loudly and
    # tell them which column is missing — don't silently fall back.
    csv_path = tmp_path / "fixtures.csv"
    csv_path.write_text("fixture_date,home_team,away_team\n15/04/2026,Panathinaikos,PAOK\n")
    with pytest.raises(ValueError) as exc_info:
        load_fixtures_from_csv(csv_path)
    assert "matchday" in str(exc_info.value)
