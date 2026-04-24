"""Tests for the rosters + absences layer.

These check:
  * Loaders behave gracefully when files are missing or empty.
  * Tier values are validated — typos fail loudly.
  * An absence correctly resolves to the tier's point value.
  * An unknown player (not in rosters) falls back to the default tier.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import config as cfg
from src.predict import (
    _tier_points,
    absences_to_adjustments,
    load_absences,
    load_rosters,
)

# ---------------------------------------------------------------------------
# Loader behaviour
# ---------------------------------------------------------------------------


def test_load_rosters_missing_file_returns_empty(tmp_path):
    # First-run users won't have the file yet — graceful degradation, not an error.
    df = load_rosters(tmp_path / "does_not_exist.csv")
    assert df.empty
    for col in ("team", "player", "tier", "note"):
        assert col in df.columns


def test_load_absences_missing_file_returns_empty(tmp_path):
    df = load_absences(tmp_path / "does_not_exist.csv")
    assert df.empty


def test_load_rosters_skips_team_stub_rows(tmp_path):
    """The shipped template has one row per team with blank player/tier.

    Those stub rows let the user see the exact spelling of every team at a
    glance; they must be silently ignored by the loader so an empty template
    doesn't trip the tier validator.
    """
    path = tmp_path / "rosters.csv"
    path.write_text(
        "team,player,tier,note\n"
        "Olympiacos,,,stub row for this team\n"
        "PAOK,Real Player,starter,filled in\n"
    )
    df = load_rosters(path)
    assert len(df) == 1
    assert df.iloc[0]["player"] == "Real Player"


def test_load_rosters_rejects_unknown_tier(tmp_path):
    # Typo like "starer" would otherwise silently default to "rotation".
    # Failing loudly is much kinder to the user.
    path = tmp_path / "rosters.csv"
    path.write_text("team,player,tier,note\nOlympiacos,Some Player,starer,oops typo\n")
    with pytest.raises(ValueError) as exc_info:
        load_rosters(path)
    assert "starer" in str(exc_info.value)


def test_load_absences_parses_dd_mm_yyyy(tmp_path):
    # Project convention: all dates use dd/mm/yyyy.
    path = tmp_path / "absences.csv"
    path.write_text(
        "team,player,effective_date,expires_date,reason\n"
        "Olympiacos,Fall,15/04/2026,22/04/2026,knee\n"
    )
    df = load_absences(path)
    assert df.iloc[0]["effective_date"] == pd.Timestamp("2026-04-15")
    assert df.iloc[0]["expires_date"] == pd.Timestamp("2026-04-22")


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------


def _rosters_sample() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Olympiacos", "Mustapha Fall", "rotation", "backup center"),
            ("PAOK", "Star Guard", "star", "primary ball-handler"),
        ],
        columns=["team", "player", "tier", "note"],
    )


def test_tier_points_returns_correct_value_for_known_player():
    points, tier = _tier_points("Mustapha Fall", "Olympiacos", _rosters_sample())
    # "rotation" points come from config — if someone tunes the tier value,
    # this test keeps moving with them rather than hard-coding a number.
    assert points == cfg.PLAYER_TIER_POINTS["rotation"]
    assert tier == "rotation"


def test_tier_points_falls_back_to_default_for_unknown_player():
    # User marked someone absent without adding them to rosters first —
    # we apply the conservative default tier rather than erroring.
    points, tier = _tier_points("Unknown Guy", "Olympiacos", _rosters_sample())
    assert tier == cfg.DEFAULT_PLAYER_TIER
    assert points == cfg.PLAYER_TIER_POINTS[cfg.DEFAULT_PLAYER_TIER]


def test_tier_points_falls_back_when_rosters_empty():
    # Completely empty rosters file: every player is "unknown" and gets the default.
    empty = pd.DataFrame(columns=["team", "player", "tier", "note"])
    points, tier = _tier_points("Anyone", "Anywhere", empty)
    assert tier == cfg.DEFAULT_PLAYER_TIER


# ---------------------------------------------------------------------------
# absences_to_adjustments
# ---------------------------------------------------------------------------


def test_absences_to_adjustments_produces_one_row_per_absence():
    abs_df = pd.DataFrame(
        [
            (
                "Olympiacos",
                "Mustapha Fall",
                pd.Timestamp("2026-04-15"),
                pd.Timestamp("2026-04-22"),
                "knee",
            ),
        ],
        columns=["team", "player", "effective_date", "expires_date", "reason"],
    )
    result = absences_to_adjustments(abs_df, _rosters_sample())
    assert len(result) == 1
    # Note includes the player's tier and the reason, so the end user can
    # see WHY the number is what it is.
    assert "Mustapha Fall" in result.iloc[0]["note"]
    assert "rotation" in result.iloc[0]["note"]
    # Margin adjustment matches the rotation tier's points.
    assert result.iloc[0]["margin_adjustment"] == cfg.PLAYER_TIER_POINTS["rotation"]


def test_absences_to_adjustments_handles_empty_input():
    empty = pd.DataFrame(columns=["team", "player", "effective_date", "expires_date", "reason"])
    result = absences_to_adjustments(empty, _rosters_sample())
    assert result.empty
    # Schema still present so downstream concat doesn't break.
    for col in ("team", "effective_date", "expires_date", "margin_adjustment", "note"):
        assert col in result.columns


def test_absences_to_adjustments_uses_default_tier_for_unknown_player():
    abs_df = pd.DataFrame(
        [
            (
                "Olympiacos",
                "Someone Not In Rosters",
                pd.Timestamp("2026-04-15"),
                pd.Timestamp("2026-04-22"),
                "minor",
            ),
        ],
        columns=["team", "player", "effective_date", "expires_date", "reason"],
    )
    result = absences_to_adjustments(abs_df, _rosters_sample())
    # The fallback points should match the default tier.
    assert result.iloc[0]["margin_adjustment"] == cfg.PLAYER_TIER_POINTS[cfg.DEFAULT_PLAYER_TIER]
    # The note should still show the default tier in parens, so the user
    # can see "hey, this player wasn't in rosters, I guessed rotation".
    assert cfg.DEFAULT_PLAYER_TIER in result.iloc[0]["note"]
