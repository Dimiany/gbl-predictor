"""Monte Carlo season simulation: title, playoff and relegation chances.

Every remaining game is played out many times. Its margin is drawn from the
same normal distribution the model uses for win probabilities
(``N(predicted margin, sigma)``), so a simulated win happens exactly as often
as the model says it should. Wins and point differences are added to the real
table, each simulated season is ranked, and the share of seasons in which a
team finishes first / in the playoff spots / in the relegation spots is its
chance of doing so.

Simplifications, on purpose (the site states them next to the numbers):

* Team strength stays as it is today for the rest of the season: the model's
  margins are computed once from the current Elo, form and record. The odds
  therefore move after every round, as the real table does.
* Ties are broken by point difference (plus a tiny random nudge), not by
  head-to-head results as in the official standings.
* The playoff / relegation format is a configured assumption
  (``cfg.PLAYOFF_SPOTS``, ``cfg.RELEGATION_SPOTS``).

Pure numpy, vectorised: 10,000 seasons x 180 games take well under a second.
"""

from __future__ import annotations

import numpy as np

from src import config as cfg

Record = tuple[int, int, int]  # wins, losses, point difference so far
Game = tuple[str, str, float]  # home, away, predicted margin (home minus away)


def simulate_season(
    records: dict[str, Record],
    games: list[Game],
    sigma: float,
    runs: int = cfg.SIM_RUNS,
    playoff_spots: int = cfg.PLAYOFF_SPOTS,
    relegation_spots: int = cfg.RELEGATION_SPOTS,
    seed: int = cfg.SIM_SEED,
) -> dict:
    """Play the remaining ``games`` ``runs`` times on top of ``records``.

    Returns a JSON-ready dict: the assumptions used and, per team, the chance
    of the title, of a playoff spot and of relegation, the expected final
    record and the probability of every final position (``pos[0]`` = first).
    Teams are ordered by title chance, then playoff chance.
    """
    teams = sorted(set(records) | {g[0] for g in games} | {g[1] for g in games})
    n = len(teams)
    out = {
        "runs": runs,
        "games_left": len(games),
        "playoff_spots": playoff_spots,
        "relegation_spots": relegation_spots,
        "teams": [],
    }
    if not n:
        return out
    index = {t: i for i, t in enumerate(teams)}
    base_w = np.array([records.get(t, (0, 0, 0))[0] for t in teams], dtype=float)
    base_gp = np.array([sum(records.get(t, (0, 0, 0))[:2]) for t in teams], dtype=float)
    base_diff = np.array([records.get(t, (0, 0, 0))[2] for t in teams], dtype=float)

    # One-hot "who is home / away" per game, so wins and margins can be summed
    # into per-team totals with two matrix products.
    g = len(games)
    home = np.zeros((g, n))
    away = np.zeros((g, n))
    for k, (h, a, _) in enumerate(games):
        home[k, index[h]] = 1
        away[k, index[a]] = 1
    mu = np.array([m for _, _, m in games], dtype=float)

    rng = np.random.default_rng(seed)
    margins = rng.normal(mu, sigma, size=(runs, g)) if g else np.zeros((runs, 0))
    home_won = (margins > 0).astype(float)
    wins = base_w + home_won @ home + (1 - home_won) @ away
    diff = base_diff + margins @ home - margins @ away
    gp = base_gp + home.sum(axis=0) + away.sum(axis=0)
    pct = wins / np.maximum(gp, 1)

    # Rank: win percentage, then point difference. Percentages differ by at
    # least 1/(2*gp*gp) when they differ at all, far more than the 1e-6 scale
    # a 1-point difference gets here; the random term only separates exact ties.
    key = pct * 1e6 + diff + rng.random((runs, n)) * 1e-3
    order = np.argsort(-key, axis=1)
    pos = np.empty_like(order)
    pos[np.arange(runs)[:, None], order] = np.arange(1, n + 1)
    dist = np.stack([np.bincount(pos[:, i], minlength=n + 1)[1:] for i in range(n)]) / runs

    playoff_spots = min(playoff_spots, n)
    relegation_spots = min(relegation_spots, n)
    for i, team in enumerate(teams):
        exp_w = float(wins[:, i].mean())
        out["teams"].append(
            {
                "team": team,
                "title": round(float(dist[i, 0]), 3),
                "playoffs": round(float(dist[i, :playoff_spots].sum()), 3),
                "relegation": round(float(dist[i, n - relegation_spots :].sum()), 3)
                if relegation_spots
                else 0.0,
                "exp_w": round(exp_w, 1),
                "exp_l": round(float(gp[i]) - exp_w, 1),
                "pos": [round(float(p), 3) for p in dist[i]],
            }
        )
    out["teams"].sort(key=lambda r: (-r["title"], -r["playoffs"], r["relegation"], r["team"]))
    return out
