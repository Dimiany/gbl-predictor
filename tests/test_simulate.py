"""Monte Carlo season simulation (src/simulate.py)."""

from __future__ import annotations

import math

from src.simulate import simulate_season


def test_a_sure_win_decides_the_title():
    # Two teams, one game left, home side 100 points better: it wins every time.
    out = simulate_season(
        {"A": (0, 0, 0), "B": (0, 0, 0)}, [("A", "B", 100.0)], sigma=12.0, runs=500
    )
    by = {r["team"]: r for r in out["teams"]}
    assert by["A"]["title"] == 1.0 and by["B"]["title"] == 0.0
    assert by["A"]["pos"] == [1.0, 0.0] and by["B"]["pos"] == [0.0, 1.0]
    assert by["A"]["exp_w"] == 1.0 and by["B"]["exp_l"] == 1.0
    assert out["teams"][0]["team"] == "A"  # ordered by title chance


def test_even_game_splits_the_title_and_distributions_sum_to_one():
    out = simulate_season(
        {"A": (0, 0, 0), "B": (0, 0, 0)}, [("A", "B", 0.0)], sigma=12.0, runs=20_000
    )
    by = {r["team"]: r for r in out["teams"]}
    assert abs(by["A"]["title"] - 0.5) < 0.02
    for r in out["teams"]:
        assert math.isclose(sum(r["pos"]), 1.0, abs_tol=1e-6)
        assert 0 <= r["title"] <= r["playoffs"] <= 1


def test_current_record_counts_and_spots_are_capped():
    # C leads 5-0 with no games left: certain title; relegation spot = the last team.
    records = {"A": (2, 3, -10), "B": (3, 2, 4), "C": (5, 0, 60)}
    out = simulate_season(records, [], sigma=12.0, runs=10, playoff_spots=8, relegation_spots=1)
    by = {r["team"]: r for r in out["teams"]}
    assert by["C"]["title"] == 1.0
    assert by["A"]["relegation"] == 1.0 and by["B"]["relegation"] == 0.0
    assert all(r["playoffs"] == 1.0 for r in out["teams"])  # 8 spots > 3 teams: everyone is in
    assert out["games_left"] == 0 and out["playoff_spots"] == 8


def test_same_seed_same_numbers_and_no_teams_is_fine():
    games = [("A", "B", 3.0), ("B", "A", -2.0), ("A", "C", 8.0)]
    a = simulate_season({}, games, sigma=12.0, runs=2000)
    b = simulate_season({}, games, sigma=12.0, runs=2000)
    assert a == b
    assert simulate_season({}, [], sigma=12.0)["teams"] == []
