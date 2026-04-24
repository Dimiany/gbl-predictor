"""Tests for the manual-adjustments feature.

These check three things:
  1. The CSV loader handles the empty / missing-file cases without erroring.
  2. _team_adjustment_on finds the right row(s) given a date.
  3. The margin-to-win-probability math is directionally correct
     (weakening a home team must lower its win probability, not raise it).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.predict import (
    _adjusted_win_prob,
    _team_adjustment_on,
    load_adjustments,
)

# ---------------------------------------------------------------------------
# load_adjustments
# ---------------------------------------------------------------------------


def test_load_adjustments_returns_empty_for_missing_file(tmp_path):
    # A user who never creates the adjustments CSV should just get
    # unadjusted predictions — not an error.
    missing = tmp_path / "does_not_exist.csv"
    df = load_adjustments(missing)
    assert df.empty
    # Schema is still present so downstream code can filter without branching.
    for col in ("team", "effective_date", "expires_date", "margin_adjustment", "note"):
        assert col in df.columns


def test_load_adjustments_returns_empty_for_header_only_file(tmp_path):
    path = tmp_path / "adj.csv"
    path.write_text("team,effective_date,expires_date,margin_adjustment,note\n")
    df = load_adjustments(path)
    assert df.empty


def test_load_adjustments_parses_rows(tmp_path):
    path = tmp_path / "adj.csv"
    # Dates in dd/mm/yyyy — the project's standard format.
    path.write_text(
        "team,effective_date,expires_date,margin_adjustment,note\n"
        "PAOK,18/04/2026,25/04/2026,-4,star guard ACL\n"
        "Aris,15/04/2026,,+2,new coach bump\n"
    )
    df = load_adjustments(path)
    assert len(df) == 2
    # Blank expires_date should be filled with a far-future sentinel so
    # "is active?" comparisons are straightforward.
    assert df.iloc[1]["expires_date"].year >= 2999


def test_load_adjustments_raises_on_missing_column(tmp_path):
    # Missing 'note' column — user probably deleted it by accident.
    path = tmp_path / "adj.csv"
    path.write_text(
        "team,effective_date,expires_date,margin_adjustment\nPAOK,18/04/2026,25/04/2026,-4\n"
    )
    with pytest.raises(ValueError) as exc_info:
        load_adjustments(path)
    assert "note" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _team_adjustment_on
# ---------------------------------------------------------------------------


def _adj_df() -> pd.DataFrame:
    # Build an in-memory adjustments DataFrame in the shape load_adjustments returns.
    df = pd.DataFrame(
        [
            ("PAOK", "2026-04-18", "2026-04-25", -4.0, "ACL"),
            ("PAOK", "2026-04-18", "2026-04-25", -1.0, "minor strain"),  # two active
            ("Aris", "2026-04-01", "2026-04-10", +2.0, "coach bump"),  # already expired by Apr 18
        ],
        columns=["team", "effective_date", "expires_date", "margin_adjustment", "note"],
    )
    df["effective_date"] = pd.to_datetime(df["effective_date"])
    df["expires_date"] = pd.to_datetime(df["expires_date"])
    return df


def test_team_adjustment_sums_overlapping_rows():
    # PAOK has two active adjustments on 2026-04-20: -4 and -1 => total -5.
    total, notes = _team_adjustment_on(pd.Timestamp("2026-04-20"), "PAOK", _adj_df())
    assert total == -5.0
    assert len(notes) == 2


def test_team_adjustment_ignores_expired_rows():
    # Aris's +2 expired on Apr 10 — asking about Apr 18 returns nothing.
    total, notes = _team_adjustment_on(pd.Timestamp("2026-04-18"), "Aris", _adj_df())
    assert total == 0.0
    assert notes == []


def test_team_adjustment_ignores_not_yet_effective_rows():
    # Asking BEFORE the effective date: PAOK's injury starts Apr 18, so
    # Apr 17 should see zero adjustment.
    total, _ = _team_adjustment_on(pd.Timestamp("2026-04-17"), "PAOK", _adj_df())
    assert total == 0.0


def test_team_adjustment_returns_zero_for_unknown_team():
    # A team that has never had an adjustment should just return 0 cleanly.
    total, notes = _team_adjustment_on(pd.Timestamp("2026-04-18"), "Mykonos", _adj_df())
    assert total == 0.0
    assert notes == []


def test_team_adjustment_empty_adjustments_df():
    # Empty DataFrame input (the common case) is a fast path — returns 0
    # without any filtering.
    empty = pd.DataFrame(
        columns=["team", "effective_date", "expires_date", "margin_adjustment", "note"]
    )
    total, notes = _team_adjustment_on(pd.Timestamp("2026-04-18"), "PAOK", empty)
    assert total == 0.0
    assert notes == []


# ---------------------------------------------------------------------------
# _adjusted_win_prob — directional sanity
# ---------------------------------------------------------------------------


def test_adjusted_win_prob_is_pass_through_when_shift_is_zero():
    # A zero shift must not touch the probability — otherwise every fixture
    # would drift even when nothing's wrong.
    assert _adjusted_win_prob(0.6, predicted_margin=3.0, margin_shift=0.0, sigma=15.0) == 0.6


def test_adjusted_win_prob_drops_when_home_is_weakened():
    # Negative margin shift (home team weakened) must lower home win prob.
    before = 0.6
    after = _adjusted_win_prob(before, predicted_margin=3.0, margin_shift=-5.0, sigma=15.0)
    assert after < before


def test_adjusted_win_prob_rises_when_home_is_strengthened():
    # Positive margin shift must raise home win prob.
    before = 0.6
    after = _adjusted_win_prob(before, predicted_margin=3.0, margin_shift=+5.0, sigma=15.0)
    assert after > before


def test_adjusted_win_prob_clipped_to_unit_interval():
    # A huge negative shift on a near-certain home win should not push the
    # returned probability below 0 due to floating-point arithmetic.
    capped = _adjusted_win_prob(0.01, predicted_margin=-20.0, margin_shift=-50.0, sigma=15.0)
    assert 0.0 <= capped <= 1.0
