"""Feature engineering for the GBL predictor.

This module turns a raw list of games (date, home, away, home_score, away_score)
into the features our model uses to predict future games. Everything is computed
strictly from PAST data for each game — no peeking at the future.

The main entry point is ``build_features``. Everything else is a helper.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config as cfg

# ---------------------------------------------------------------------------
# Elo rating
# ---------------------------------------------------------------------------


def elo_expected_score(rating_a: float, rating_b: float) -> float:
    """Return the probability that team A beats team B according to Elo.

    Classic chess-Elo formula. If the ratings are equal, the result is 0.5.
    A 200-point gap implies about a 76% win probability for the higher-rated
    team. Callers should add the home-court bonus to ``rating_a`` BEFORE
    calling this function if they want to account for it.
    """
    # The formula: 1 / (1 + 10^((B - A) / 400))
    # This is a logistic curve — smooth S-shape from 0 to 1.
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / cfg.ELO_DIVISOR))


def elo_update(
    home_rating: float,
    away_rating: float,
    home_won: int,
    k: float = cfg.ELO_K,
    home_advantage: float = cfg.ELO_HOME_ADVANTAGE,
) -> tuple[float, float]:
    """Return the pair (new_home_rating, new_away_rating) after one game.

    We add the home-advantage bonus to the home team's rating ONLY while
    computing the expected score — we do not permanently boost their rating.
    Otherwise home teams would drift up forever.
    """
    # Expected score FROM THE HOME TEAM'S PERSPECTIVE, with the home bonus applied.
    expected_home = elo_expected_score(home_rating + home_advantage, away_rating)
    # Actual outcome: 1 if home won, 0 if they lost. (No ties in basketball.)
    actual_home = float(home_won)
    # The "surprise" of the result drives the rating change. If Elo expected
    # a home win (expected_home = 0.8) and the home team won (actual = 1.0),
    # the rating only moves a little — it wasn't surprising.
    delta = k * (actual_home - expected_home)
    # Zero-sum: whatever one team gains, the other loses. Keeps the league average at 1500.
    return home_rating + delta, away_rating - delta


def game_k(home_games: int, away_games: int) -> float:
    """K for one game: ELO_K_EARLY while either team is in its first
    ELO_EARLY_GAMES games of the season (counts before this game), else ELO_K."""
    early = min(home_games, away_games) < cfg.ELO_EARLY_GAMES
    return cfg.ELO_K_EARLY if early else cfg.ELO_K


def season_of(date: pd.Timestamp) -> int:
    """Start year of the GBL season ``date`` falls in (2027-03-01 -> 2026)."""
    return date.year if date.month >= cfg.SEASON_START_MONTH else date.year - 1


# ---------------------------------------------------------------------------
# Per-team running state
# ---------------------------------------------------------------------------
# We stream through the games in chronological order and maintain one of these
# objects per team. At the moment a game is about to happen, this struct holds
# everything we'd know about the team from prior games — which is exactly what
# we want as features.


@dataclass
class TeamState:
    """Running state for one team, built up game by game."""

    elo: float = cfg.ELO_INITIAL
    games_played: int = 0
    last_game_date: pd.Timestamp | None = None
    # deque with maxlen auto-drops the oldest entry when we append — a natural
    # sliding window without any manual bookkeeping.
    recent_scored: deque[int] = field(default_factory=lambda: deque(maxlen=cfg.ROLLING_WINDOW))
    recent_conceded: deque[int] = field(default_factory=lambda: deque(maxlen=cfg.ROLLING_WINDOW))
    recent_wins: deque[int] = field(default_factory=lambda: deque(maxlen=cfg.ROLLING_WINDOW))
    # Full-season counters — separate from the rolling deques above. The
    # deques only see the last ROLLING_WINDOW games; these accumulate forever.
    season_wins: int = 0
    season_margin_total: int = 0  # cumulative point differential, used as standings tiebreak
    season: int | None = None  # season (start year) the counters above belong to

    def start_season(self, season: int) -> None:
        """Roll the team into ``season`` if it isn't there already.

        Everything season-scoped (W-L, games played, L5 form, rest days) starts
        over; Elo carries over, regressed toward the mean. Idempotent — calling
        it again for the same season is a no-op.
        """
        if self.season == season:
            return
        if self.season is not None:
            self.elo = cfg.ELO_INITIAL + cfg.ELO_SEASON_CARRYOVER * (self.elo - cfg.ELO_INITIAL)
            self.games_played = 0
            self.season_wins = 0
            self.season_margin_total = 0
            self.last_game_date = None
            self.recent_scored.clear()
            self.recent_conceded.clear()
            self.recent_wins.clear()
        self.season = season

    # --- accessors used at feature-build time ----------------------------------
    # Each returns NaN until we have enough games. NaN is important:
    # HistGradientBoosting treats it as a missing value and handles it natively,
    # which is more honest than filling with the league mean.

    def _rolling_mean(self, dq: deque[int]) -> float:
        if len(dq) < cfg.MIN_GAMES_FOR_ROLLING:
            return np.nan
        return float(np.mean(dq))

    @property
    def avg_scored_L5(self) -> float:
        return self._rolling_mean(self.recent_scored)

    @property
    def avg_conceded_L5(self) -> float:
        return self._rolling_mean(self.recent_conceded)

    @property
    def margin_L5(self) -> float:
        if len(self.recent_scored) < cfg.MIN_GAMES_FOR_ROLLING:
            return np.nan
        # Point differential, averaged over the window.
        return float(
            np.mean([s - c for s, c in zip(self.recent_scored, self.recent_conceded, strict=True)])
        )

    @property
    def form_L5(self) -> float:
        return self._rolling_mean(self.recent_wins)

    @property
    def season_losses(self) -> int:
        return self.games_played - self.season_wins

    @property
    def season_win_pct(self) -> float:
        """Wins / games_played. NaN before the team has played any game."""
        if self.games_played == 0:
            return np.nan
        return self.season_wins / self.games_played

    def rest_days(self, current_date: pd.Timestamp) -> float:
        """How many days since this team's previous game.

        Returns NaN for the team's first game of the season — no prior game
        means no rest value to compute.
        """
        if self.last_game_date is None:
            return np.nan
        return float((current_date - self.last_game_date).days)

    def record_game(self, scored: int, conceded: int, date: pd.Timestamp) -> None:
        """Add a completed game to this team's history.

        Called AFTER we've extracted features for the game — so the features
        reflect only PAST games, not the one just played.
        """
        won = 1 if scored > conceded else 0
        self.recent_scored.append(scored)
        self.recent_conceded.append(conceded)
        self.recent_wins.append(won)
        self.games_played += 1
        self.season_wins += won
        self.season_margin_total += scored - conceded
        self.last_game_date = date


# ---------------------------------------------------------------------------
# Head-to-head tracker
# ---------------------------------------------------------------------------


class HeadToHead:
    """Tracks, for each (team_a, team_b) pair, how often team_a has won.

    We store this pairwise — (A, B) is different from (B, A) — so querying
    with home/away in their natural order gives us the home-team win rate.
    """

    def __init__(self) -> None:
        # defaultdict saves us from checking "does this key exist" everywhere.
        self._wins: dict[tuple[str, str], int] = defaultdict(int)
        self._games: dict[tuple[str, str], int] = defaultdict(int)

    def home_winrate(self, home: str, away: str) -> float:
        """Historical win rate of ``home`` vs ``away`` across all prior meetings.

        Returns NaN before the two teams have met — with no history there's
        genuinely no signal, and NaN is more honest than assuming 0.5.
        """
        games = self._games[(home, away)] + self._games[(away, home)]
        if games == 0:
            return np.nan
        # Wins by `home` in either venue, over total meetings.
        wins = self._wins[(home, away)] + (self._games[(away, home)] - self._wins[(away, home)])
        return wins / games

    def record(self, home: str, away: str, home_won: int) -> None:
        self._games[(home, away)] += 1
        if home_won:
            self._wins[(home, away)] += 1


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


def enter_season(states: dict[str, TeamState], team: str, season: int) -> TeamState:
    """The team's state, rolled into ``season`` (see TeamState.start_season).

    A team that has never played while the league already has an earlier season
    is a promoted team: it starts at ELO_PROMOTED_START, not the league average.
    """
    state = states[team]
    if state.season is None and any(
        o.season is not None and o.season < season for o in states.values()
    ):
        state.elo = cfg.ELO_PROMOTED_START
    state.start_season(season)
    return state


def standings_rank(states: dict[str, TeamState], team: str, season: int | None = None) -> float:
    """Return ``team``'s 1-based position in the league table.

    With ``season`` given, only teams whose counters belong to that season are
    ranked — last season's (or relegated) teams don't pollute the new table.

    Sorting key: win % desc, then cumulative margin total desc as tiebreak.
    This isn't the OFFICIAL GBL ranking (which uses head-to-head) but it
    matches the real table closely enough — and the model only needs an
    ordinal "are they top of the table or bottom" signal, not the exact
    position the league office would publish.

    Returns NaN if ``team`` hasn't played a game yet, or isn't in ``states``.
    Teams with zero games are excluded from the ranking — they have no
    win % to sort on.
    """
    if team not in states or states[team].games_played == 0:
        return np.nan
    if season is not None and states[team].season != season:
        return np.nan
    active = [
        (name, s)
        for name, s in states.items()
        if s.games_played > 0 and (season is None or s.season == season)
    ]
    # Sort: highest win% first, then highest margin total as the tiebreaker.
    active.sort(key=lambda item: (-item[1].season_win_pct, -item[1].season_margin_total))
    for i, (name, _) in enumerate(active):
        if name == team:
            return float(i + 1)
    return np.nan


# ---------------------------------------------------------------------------
# Main feature builder
# ---------------------------------------------------------------------------


def build_features(games: pd.DataFrame) -> pd.DataFrame:
    """Return ``games`` with all engineered features attached.

    Input must contain: game_date, home_team, away_team, home_score, away_score.
    The output preserves input order but adds feature columns plus margin,
    total_points, and home_win.

    We process games in strict chronological order so that at each row, every
    feature only uses information available BEFORE that game was played.
    """
    # Copy so we don't mutate the caller's DataFrame — a Python courtesy.
    games = games.copy()

    # Ensure the date column is actually datetime. If the caller already parsed
    # it, this is a no-op; if they passed strings, this saves us a bug later.
    # dayfirst=True so CSV strings like "15/04/2026" parse as 15 April 2026
    # (European format) rather than the US mm/dd/yyyy interpretation.
    games[cfg.COL_DATE] = pd.to_datetime(games[cfg.COL_DATE], dayfirst=True)

    # Sort chronologically. This is THE critical step — without it, rolling
    # features would leak future data into past rows. We keep the original
    # index on the output so callers can realign if needed.
    games = games.sort_values(cfg.COL_DATE, kind="stable").reset_index(drop=True)

    # Derived targets (computed from scores, not learned).
    games[cfg.COL_MARGIN] = games[cfg.COL_HOME_SCORE] - games[cfg.COL_AWAY_SCORE]
    games[cfg.COL_TOTAL] = games[cfg.COL_HOME_SCORE] + games[cfg.COL_AWAY_SCORE]
    games[cfg.COL_HOME_WIN] = (games[cfg.COL_MARGIN] > 0).astype(int)

    # Per-team state: one TeamState per team, default-created on first access.
    states: dict[str, TeamState] = defaultdict(TeamState)
    h2h = HeadToHead()

    # We'll collect feature rows here, then assign them back as columns at the end.
    # Building a list of dicts is faster than repeatedly setting DataFrame cells.
    feature_rows: list[dict] = []

    for _, row in games.iterrows():
        home: str = row[cfg.COL_HOME]
        away: str = row[cfg.COL_AWAY]
        date: pd.Timestamp = row[cfg.COL_DATE]

        # First game of a new season for either team -> reset its season state.
        season = season_of(date)
        h = enter_season(states, home, season)
        a = enter_season(states, away, season)

        # --- snapshot features BEFORE recording the game -------------------
        # This ordering is what prevents data leakage: the features describe
        # the state of each team immediately before tipoff.
        home_elo = h.elo
        away_elo = a.elo
        elo_diff_adj = (home_elo + cfg.ELO_HOME_ADVANTAGE) - away_elo
        win_prob = elo_expected_score(home_elo + cfg.ELO_HOME_ADVANTAGE, away_elo)

        # Standings + W-L snapshot (state-as-of-tipoff, no leakage).
        home_rank = standings_rank(states, home, season)
        away_rank = standings_rank(states, away, season)
        # rank_diff: negative = home team higher in the table (a stronger team
        # at home). NaN early-season when ranks aren't defined for both sides.
        rank_diff = (
            home_rank - away_rank if not (np.isnan(home_rank) or np.isnan(away_rank)) else np.nan
        )

        feature_rows.append(
            {
                "home_elo_pre": home_elo,
                "away_elo_pre": away_elo,
                "elo_diff_adj": elo_diff_adj,
                "home_win_prob_elo": win_prob,
                "home_avg_scored_L5": h.avg_scored_L5,
                "home_avg_conceded_L5": h.avg_conceded_L5,
                "away_avg_scored_L5": a.avg_scored_L5,
                "away_avg_conceded_L5": a.avg_conceded_L5,
                "home_margin_L5": h.margin_L5,
                "away_margin_L5": a.margin_L5,
                "home_form_L5": h.form_L5,
                "away_form_L5": a.form_L5,
                "home_rest_days": h.rest_days(date),
                "away_rest_days": a.rest_days(date),
                "home_games_played": h.games_played,
                "away_games_played": a.games_played,
                "h2h_home_winrate": h2h.home_winrate(home, away),
                "home_season_wins": h.season_wins,
                "home_season_losses": h.season_losses,
                "home_season_win_pct": h.season_win_pct,
                "away_season_wins": a.season_wins,
                "away_season_losses": a.season_losses,
                "away_season_win_pct": a.season_win_pct,
                "home_rank": home_rank,
                "away_rank": away_rank,
                "rank_diff": rank_diff,
            }
        )

        # --- update state AFTER extracting features ------------------------
        home_score = int(row[cfg.COL_HOME_SCORE])
        away_score = int(row[cfg.COL_AWAY_SCORE])
        home_won = int(home_score > away_score)

        k = game_k(h.games_played, a.games_played)
        h.record_game(home_score, away_score, date)
        a.record_game(away_score, home_score, date)
        new_home_elo, new_away_elo = elo_update(h.elo, a.elo, home_won, k=k)
        h.elo = new_home_elo
        a.elo = new_away_elo
        h2h.record(home, away, home_won)

    # Attach the features as columns in one shot. This is much faster than
    # setting cells one at a time inside the loop.
    features_df = pd.DataFrame(feature_rows, index=games.index)
    # all_fixtures.csv carries legacy (empty) columns with some of the same
    # names, e.g. home_avg_scored_L5. Drop them so each feature exists once.
    games = games.drop(columns=[c for c in features_df.columns if c in games.columns])
    return pd.concat([games, features_df], axis=1)


# ---------------------------------------------------------------------------
# Live-inference helper
# ---------------------------------------------------------------------------


def team_state_snapshot(
    history: pd.DataFrame,
) -> tuple[dict[str, TeamState], HeadToHead]:
    """Replay all historical games and return the final per-team / H2H state.

    Used at prediction time: we want the "current" Elo, form, etc. for each
    team so we can build features for games that HAVEN'T been played yet.
    """
    history = history.copy()
    # dayfirst=True for European-style CSV dates (see build_features for rationale).
    history[cfg.COL_DATE] = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    history = history.sort_values(cfg.COL_DATE, kind="stable")

    states: dict[str, TeamState] = defaultdict(TeamState)
    h2h = HeadToHead()

    for _, row in history.iterrows():
        home: str = row[cfg.COL_HOME]
        away: str = row[cfg.COL_AWAY]
        date: pd.Timestamp = row[cfg.COL_DATE]
        home_score = int(row[cfg.COL_HOME_SCORE])
        away_score = int(row[cfg.COL_AWAY_SCORE])
        home_won = int(home_score > away_score)

        season = season_of(date)
        h = enter_season(states, home, season)
        a = enter_season(states, away, season)
        k = game_k(h.games_played, a.games_played)
        h.record_game(home_score, away_score, date)
        a.record_game(away_score, home_score, date)
        new_home_elo, new_away_elo = elo_update(h.elo, a.elo, home_won, k=k)
        h.elo = new_home_elo
        a.elo = new_away_elo
        h2h.record(home, away, home_won)

    return states, h2h


def features_for_fixture(
    home: str,
    away: str,
    fixture_date: pd.Timestamp,
    states: dict[str, TeamState],
    h2h: HeadToHead,
) -> dict[str, float]:
    """Build the feature row for a single unplayed fixture.

    Mirrors the per-row logic inside ``build_features`` but using the
    snapshot state rather than streaming through history.

    If the fixture opens a new season for a team, its snapshot state is rolled
    over in place (idempotent), exactly as ``build_features`` would do.
    """
    season = season_of(fixture_date)
    h = enter_season(states, home, season)
    a = enter_season(states, away, season)
    home_elo = h.elo
    away_elo = a.elo
    home_rank = standings_rank(states, home, season)
    away_rank = standings_rank(states, away, season)
    rank_diff = (
        home_rank - away_rank if not (np.isnan(home_rank) or np.isnan(away_rank)) else np.nan
    )
    return {
        "home_elo_pre": home_elo,
        "away_elo_pre": away_elo,
        "elo_diff_adj": (home_elo + cfg.ELO_HOME_ADVANTAGE) - away_elo,
        "home_win_prob_elo": elo_expected_score(home_elo + cfg.ELO_HOME_ADVANTAGE, away_elo),
        "home_avg_scored_L5": h.avg_scored_L5,
        "home_avg_conceded_L5": h.avg_conceded_L5,
        "away_avg_scored_L5": a.avg_scored_L5,
        "away_avg_conceded_L5": a.avg_conceded_L5,
        "home_margin_L5": h.margin_L5,
        "away_margin_L5": a.margin_L5,
        "home_form_L5": h.form_L5,
        "away_form_L5": a.form_L5,
        "home_rest_days": h.rest_days(fixture_date),
        "away_rest_days": a.rest_days(fixture_date),
        "home_games_played": h.games_played,
        "away_games_played": a.games_played,
        "h2h_home_winrate": h2h.home_winrate(home, away),
        "home_season_wins": h.season_wins,
        "home_season_losses": h.season_losses,
        "home_season_win_pct": h.season_win_pct,
        "away_season_wins": a.season_wins,
        "away_season_losses": a.season_losses,
        "away_season_win_pct": a.season_win_pct,
        "home_rank": home_rank,
        "away_rank": away_rank,
        "rank_diff": rank_diff,
    }
