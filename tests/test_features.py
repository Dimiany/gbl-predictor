"""Tests for feature engineering.

These tests protect the most important invariant of the whole project:
FEATURES FOR A GAME MUST ONLY USE INFORMATION FROM GAMES PLAYED EARLIER.

If this invariant ever breaks — for example, because someone "helpfully"
reorders the rows — the model will look great in testing and fail in
production. These tests are our safety net.

Run with:  pytest tests/
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src import config as cfg
from src.features import (
    HeadToHead,
    TeamState,
    build_features,
    elo_expected_score,
    elo_update,
    standings_rank,
)

# ---------------------------------------------------------------------------
# Elo unit tests
# ---------------------------------------------------------------------------


def test_elo_expected_equal_ratings_is_half():
    # Two teams with identical ratings should have a 50/50 Elo expectation.
    assert elo_expected_score(1500, 1500) == pytest.approx(0.5)


def test_elo_expected_higher_rated_favored():
    # The team rated 200 points higher should be well above 50% to win.
    high_vs_low = elo_expected_score(1700, 1500)
    assert high_vs_low > 0.7
    # And symmetrically the other side is below 30%.
    low_vs_high = elo_expected_score(1500, 1700)
    assert low_vs_high < 0.3
    # Probabilities must sum to 1 (standard Elo property).
    assert high_vs_low + low_vs_high == pytest.approx(1.0)


def test_elo_update_is_zero_sum():
    # Whatever the home team gains in Elo, the away team must lose — otherwise
    # the league's average Elo would drift over time.
    new_home, new_away = elo_update(1500, 1500, home_won=1)
    assert (new_home - 1500) == pytest.approx(-(new_away - 1500))


def test_elo_update_home_loss_still_plausible_given_advantage():
    # The home team is rated equal BUT has home-court advantage (~65 Elo).
    # If they lose, their Elo should DROP — the home bonus meant they were
    # expected to win, so losing is a bigger surprise.
    new_home, _ = elo_update(1500, 1500, home_won=0)
    assert new_home < 1500


# ---------------------------------------------------------------------------
# TeamState unit tests
# ---------------------------------------------------------------------------


def test_team_state_returns_nan_before_min_games():
    # Before the team has played MIN_GAMES_FOR_ROLLING, all rolling stats
    # must be NaN — otherwise early-season predictions lean on noise.
    s = TeamState()
    assert math.isnan(s.avg_scored_L5)
    assert math.isnan(s.form_L5)

    # After one game — still not enough to trust a rolling average.
    s.record_game(scored=80, conceded=75, date=pd.Timestamp("2025-10-04"))
    if cfg.MIN_GAMES_FOR_ROLLING > 1:
        assert math.isnan(s.avg_scored_L5)


def test_team_state_rolling_window_drops_oldest():
    # The sliding window should forget games older than ROLLING_WINDOW.
    s = TeamState()
    dates = pd.date_range("2025-10-04", periods=cfg.ROLLING_WINDOW + 1, freq="7D")
    # Score steadily rising by 10 each game.
    for i, d in enumerate(dates):
        s.record_game(scored=70 + 10 * i, conceded=70, date=d)
    # We now have ROLLING_WINDOW games of data, and the OLDEST (70 points)
    # should have been evicted — so the minimum in the window is 80.
    assert min(s.recent_scored) >= 80


def test_rest_days_is_nan_for_first_game():
    s = TeamState()
    # No previous game → no rest-days concept yet.
    assert math.isnan(s.rest_days(pd.Timestamp("2025-10-04")))


def test_rest_days_counts_correctly():
    s = TeamState()
    s.record_game(80, 75, pd.Timestamp("2025-10-04"))
    assert s.rest_days(pd.Timestamp("2025-10-07")) == 3.0


# ---------------------------------------------------------------------------
# HeadToHead unit tests
# ---------------------------------------------------------------------------


def test_h2h_returns_nan_before_first_meeting():
    h2h = HeadToHead()
    assert math.isnan(h2h.home_winrate("A", "B"))


def test_h2h_tracks_symmetrically_across_venues():
    # A home-winrate over B should combine both venues' history.
    # If A beat B at home, then B beat A at home, it's 1 win each => 0.5.
    h2h = HeadToHead()
    h2h.record("A", "B", home_won=1)  # A won at home
    h2h.record("B", "A", home_won=1)  # B won at home
    assert h2h.home_winrate("A", "B") == pytest.approx(0.5)
    assert h2h.home_winrate("B", "A") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# The big one: build_features data-leakage invariant
# ---------------------------------------------------------------------------


def _toy_games() -> pd.DataFrame:
    """A small synthetic dataset we can hand-verify."""
    # Dates in dd/mm/yyyy — the format the production CSVs use.
    return pd.DataFrame(
        [
            # date, home, away, home_score, away_score
            ("04/10/2025", "A", "B", 90, 80),
            ("05/10/2025", "C", "D", 70, 75),
            ("11/10/2025", "B", "A", 85, 95),
            ("12/10/2025", "D", "C", 88, 80),
            ("18/10/2025", "A", "C", 92, 90),
            ("19/10/2025", "B", "D", 78, 82),
        ],
        columns=[cfg.COL_DATE, cfg.COL_HOME, cfg.COL_AWAY, cfg.COL_HOME_SCORE, cfg.COL_AWAY_SCORE],
    )


def test_build_features_first_game_has_neutral_elo():
    # Very first game of the season: both teams start at ELO_INITIAL,
    # so home_elo_pre and away_elo_pre must BOTH be ELO_INITIAL.
    feats = build_features(_toy_games())
    first = feats.iloc[0]
    assert first["home_elo_pre"] == cfg.ELO_INITIAL
    assert first["away_elo_pre"] == cfg.ELO_INITIAL


def test_build_features_elo_updates_after_each_game():
    # After game 1 (A beat B), A's Elo must be strictly higher than 1500
    # on its NEXT game — not on the game currently being featurized.
    feats = build_features(_toy_games())
    # Game 3 is B vs A (their second meeting). A's pre-game Elo here must
    # reflect the win from game 1.
    g3 = feats.iloc[2]
    assert g3[cfg.COL_AWAY] == "A"  # A is away in game 3
    assert g3["away_elo_pre"] > cfg.ELO_INITIAL


def test_build_features_no_leakage_rolling_stats():
    """The golden test — the feature in row N must not depend on row N itself.

    We verify this by checking that columns like home_avg_scored_L5 can
    only reference scores from rows strictly BEFORE the current row.
    """
    feats = build_features(_toy_games())
    # Team A plays games 1, 3, 5. Before game 5, A has played 2 prior games
    # (scored 90 then 95 according to our toy data).
    # The rolling stat is only defined once MIN_GAMES_FOR_ROLLING is reached.
    game5 = feats.iloc[4]
    assert game5[cfg.COL_HOME] == "A"
    assert game5["home_games_played"] == 2
    if cfg.MIN_GAMES_FOR_ROLLING <= 2:
        # We expect the mean of (90, 95) = 92.5 — NOT including game 5's score of 92.
        assert game5["home_avg_scored_L5"] == pytest.approx(92.5)
    else:
        assert math.isnan(game5["home_avg_scored_L5"])


def test_build_features_handles_unsorted_input():
    # Even if the caller passes games in shuffled order, the output must be
    # chronologically consistent — this is what protects production users
    # who don't know to sort.
    shuffled = _toy_games().sample(frac=1, random_state=0).reset_index(drop=True)
    feats = build_features(shuffled)
    # Dates must come out monotonic.
    dates = feats[cfg.COL_DATE].tolist()
    assert dates == sorted(dates)


def test_build_features_adds_target_columns():
    feats = build_features(_toy_games())
    # Derived targets must exist and match the raw scores.
    assert (feats[cfg.COL_MARGIN] == feats[cfg.COL_HOME_SCORE] - feats[cfg.COL_AWAY_SCORE]).all()
    assert (feats[cfg.COL_TOTAL] == feats[cfg.COL_HOME_SCORE] + feats[cfg.COL_AWAY_SCORE]).all()
    assert ((feats[cfg.COL_HOME_WIN] == 0) | (feats[cfg.COL_HOME_WIN] == 1)).all()


# ---------------------------------------------------------------------------
# Season W-L record
# ---------------------------------------------------------------------------


def test_team_state_tracks_season_wins_losses():
    s = TeamState()
    # Fresh state: no games played, no record yet.
    assert s.season_wins == 0
    assert s.season_losses == 0
    assert math.isnan(s.season_win_pct)

    s.record_game(scored=90, conceded=80, date=pd.Timestamp("2025-10-04"))  # win
    s.record_game(scored=70, conceded=85, date=pd.Timestamp("2025-10-11"))  # loss
    s.record_game(scored=88, conceded=75, date=pd.Timestamp("2025-10-18"))  # win

    assert s.season_wins == 2
    assert s.season_losses == 1
    assert s.season_win_pct == pytest.approx(2 / 3)


def test_team_state_season_margin_total():
    # season_margin_total accumulates point differential across the whole season,
    # used as the standings tiebreaker.
    s = TeamState()
    s.record_game(90, 80, pd.Timestamp("2025-10-04"))  # +10
    s.record_game(70, 85, pd.Timestamp("2025-10-11"))  # -15
    s.record_game(88, 75, pd.Timestamp("2025-10-18"))  # +13
    assert s.season_margin_total == 8


def test_build_features_season_record_no_leakage():
    """Feature row N must show the W-L record AFTER game N-1, not after game N."""
    feats = build_features(_toy_games())
    # Team A's games: row 0 (home, won), row 2 (away, won), row 4 (home).
    # Before game 5, A has played and won the previous two.
    g5 = feats.iloc[4]
    assert g5[cfg.COL_HOME] == "A"
    assert g5["home_season_wins"] == 2
    assert g5["home_season_losses"] == 0
    assert g5["home_season_win_pct"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Standings rank
# ---------------------------------------------------------------------------


def test_standings_rank_nan_for_unplayed_team():
    states: dict[str, TeamState] = {}
    assert math.isnan(standings_rank(states, "A"))


def test_standings_rank_orders_by_win_pct():
    states: dict[str, TeamState] = {
        "A": TeamState(),
        "B": TeamState(),
        "C": TeamState(),
    }
    # A: 2-0 (1.000), B: 1-1 (0.500), C: 0-2 (0.000) — clean ordering.
    states["A"].record_game(90, 80, pd.Timestamp("2025-10-04"))
    states["A"].record_game(95, 70, pd.Timestamp("2025-10-11"))
    states["B"].record_game(70, 85, pd.Timestamp("2025-10-04"))
    states["B"].record_game(88, 75, pd.Timestamp("2025-10-11"))
    states["C"].record_game(60, 80, pd.Timestamp("2025-10-04"))
    states["C"].record_game(55, 90, pd.Timestamp("2025-10-11"))
    assert standings_rank(states, "A") == 1
    assert standings_rank(states, "B") == 2
    assert standings_rank(states, "C") == 3


def test_standings_rank_uses_margin_as_tiebreaker():
    # Two teams both 1-1: the one with the better point differential ranks higher.
    states: dict[str, TeamState] = {"A": TeamState(), "B": TeamState()}
    # A: won by 20, lost by 5 -> +15
    states["A"].record_game(95, 75, pd.Timestamp("2025-10-04"))
    states["A"].record_game(70, 75, pd.Timestamp("2025-10-11"))
    # B: won by 5, lost by 20 -> -15
    states["B"].record_game(80, 75, pd.Timestamp("2025-10-04"))
    states["B"].record_game(70, 90, pd.Timestamp("2025-10-11"))
    assert standings_rank(states, "A") == 1
    assert standings_rank(states, "B") == 2


def test_build_features_first_game_has_nan_rank():
    """Round-1 fixture: no team has played yet, so neither has a rank."""
    feats = build_features(_toy_games())
    first = feats.iloc[0]
    assert math.isnan(first["home_rank"])
    assert math.isnan(first["away_rank"])
    assert math.isnan(first["rank_diff"])


# ---------------------------------------------------------------------------
# Season rollover — a new season must not inherit last season's W-L / rank
# ---------------------------------------------------------------------------


def test_season_of_splits_on_season_start_month():
    from src.features import season_of

    assert season_of(pd.Timestamp("2026-06-13")) == 2025
    assert season_of(pd.Timestamp("2026-10-04")) == 2026
    assert season_of(pd.Timestamp("2027-03-01")) == 2026


def test_start_season_resets_counters_and_regresses_elo():
    s = TeamState(elo=1600.0)
    s.start_season(2025)
    s.record_game(90, 80, pd.Timestamp("2026-05-01"))
    elo_before = s.elo

    s.start_season(2026)

    assert (s.games_played, s.season_wins, s.season_margin_total) == (0, 0, 0)
    assert len(s.recent_scored) == 0
    assert s.last_game_date is None
    expected = cfg.ELO_INITIAL + cfg.ELO_SEASON_CARRYOVER * (elo_before - cfg.ELO_INITIAL)
    assert s.elo == pytest.approx(expected)
    # Idempotent: rolling into the same season again changes nothing.
    s.start_season(2026)
    assert s.elo == pytest.approx(expected)


def test_build_features_new_season_starts_from_clean_record():
    games = pd.DataFrame(
        {
            "game_date": ["01/05/2026", "08/05/2026", "04/10/2026"],
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "B", "B"],
            "home_score": [90, 92, 80],
            "away_score": [80, 70, 85],
        }
    )
    feats = build_features(games)
    opener = feats.iloc[2]
    assert opener["home_games_played"] == 0
    assert opener["home_season_wins"] == 0
    assert math.isnan(opener["home_rank"])  # nobody has played the new season yet
    # Elo still carries signal: A beat B twice, so A stays ahead after regression.
    assert opener["home_elo_pre"] > opener["away_elo_pre"]


def test_standings_rank_ignores_teams_from_another_season():
    states = {"A": TeamState(), "B": TeamState()}
    states["A"].start_season(2025)
    states["A"].record_game(90, 80, pd.Timestamp("2026-05-01"))
    states["B"].start_season(2026)
    states["B"].record_game(70, 80, pd.Timestamp("2026-10-04"))

    assert standings_rank(states, "B", 2026) == 1
    assert math.isnan(standings_rank(states, "A", 2026))


def test_build_features_replaces_legacy_feature_columns():
    # all_fixtures.csv has stale, empty columns named like features.
    games = _toy_games()
    games["home_avg_scored_L5"] = np.nan
    games["home_games_played"] = -1  # stale value that must be overwritten
    feats = build_features(games)
    assert list(feats.columns).count("home_avg_scored_L5") == 1
    assert list(feats.columns).count("home_games_played") == 1
    assert feats["home_games_played"].iloc[0] == 0


# ---------------------------------------------------------------------------
# margin-v3 Elo rules: promoted teams start low, faster learning early in a season
# ---------------------------------------------------------------------------


def test_promoted_team_starts_below_the_league_average():
    games = pd.DataFrame(
        {
            "game_date": ["01/05/2026", "04/10/2026", "04/10/2026"],
            "home_team": ["A", "A", "C"],
            "away_team": ["B", "N", "B"],
            "home_score": [90, 90, 80],
            "away_score": [80, 70, 85],
        }
    )
    feats = build_features(games)
    # The very first season has no "promoted" teams: everyone starts at the average.
    assert feats.iloc[0]["away_elo_pre"] == cfg.ELO_INITIAL
    # N and C appear only in the next season: they came up from A2.
    assert feats.iloc[1]["away_elo_pre"] == cfg.ELO_PROMOTED_START
    assert feats.iloc[2]["home_elo_pre"] == cfg.ELO_PROMOTED_START


def test_promoted_team_before_its_first_game_uses_the_promoted_start():
    from src.features import features_for_fixture, team_state_snapshot

    history = pd.DataFrame(
        {
            "game_date": ["01/05/2026"],
            "home_team": ["A"],
            "away_team": ["B"],
            "home_score": [90],
            "away_score": [80],
        }
    )
    states, h2h = team_state_snapshot(history)
    row = features_for_fixture("New", "A", pd.Timestamp("2026-10-10"), states, h2h)
    assert row["home_elo_pre"] == cfg.ELO_PROMOTED_START


def test_ratings_move_faster_in_the_first_games_of_a_season():
    from src.features import game_k

    assert game_k(0, 20) == cfg.ELO_K_EARLY  # either team still early -> fast
    assert game_k(cfg.ELO_EARLY_GAMES, cfg.ELO_EARLY_GAMES) == cfg.ELO_K
    assert cfg.ELO_K_EARLY > cfg.ELO_K
