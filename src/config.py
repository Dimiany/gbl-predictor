"""Central configuration: paths, column names, feature lists, hyperparameters.

Keeping all "magic numbers" and string constants here means that when you want
to tune the model, you change ONE file — not hunt through the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load environment variables from a .env file if one exists. This is a common
# pattern — secrets (API keys) live in .env (gitignored), code reads them via
# os.getenv. If python-dotenv isn't installed, we fall back to whatever's
# already in the environment, so the project still runs without it.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# __file__ is this config.py. .parent.parent walks up to the project root.
# Using Path objects (not raw strings) keeps paths OS-independent (Windows / Mac / Linux).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
MODELS_DIR: Path = PROJECT_ROOT / "models"

# The single raw input: one row per played game.
RAW_GAMES_CSV: Path = RAW_DATA_DIR / "all_fixtures.csv"
# Upcoming fixtures to predict — edit this CSV instead of hardcoding in notebooks.
UPCOMING_FIXTURES_CSV: Path = RAW_DATA_DIR / "upcoming_fixtures.csv"
# Manual per-team margin adjustments — coach fires, team-wide suspensions,
# anything that isn't a specific player being out. Optional: if the file is
# missing or empty, predictions run unadjusted.
ADJUSTMENTS_CSV: Path = RAW_DATA_DIR / "adjustments.csv"

# Team rosters with player importance tiers. Slow-changing reference data.
ROSTERS_CSV: Path = RAW_DATA_DIR / "rosters.csv"
# Current player absences (injuries, suspensions, personal). Fast-changing.
ABSENCES_CSV: Path = RAW_DATA_DIR / "absences.csv"

# ---------------------------------------------------------------------------
# Player importance tiers
# ---------------------------------------------------------------------------
# Instead of asking users to guess signed point values for every player, they
# classify each player into ONE of these tiers and we map the tier to a point
# swing. This is the ONE place to tune how much absences affect the margin.
#
# Tier meaning:
#   star     — franchise cornerstone, losing them is catastrophic (-6)
#   starter  — regular starter whose absence meaningfully hurts (-3)
#   rotation — steady rotation piece, felt but not critical (-1)
#   bench    — end-of-bench player, functionally replaceable (0)
#
# The numbers are OPINIONS, not science. Tune them here if you disagree —
# a single change propagates through every absence in the whole project.
# ---------------------------------------------------------------------------
PLAYER_TIER_POINTS: dict[str, float] = {
    "star": -6.0,
    "starter": -3.0,
    "rotation": -1.0,
    "bench": 0.0,
}

# Unknown players (absent but not listed in rosters.csv) default to this tier.
# "rotation" is deliberately conservative — better to under-adjust than to
# over-adjust for someone you haven't characterised yet.
DEFAULT_PLAYER_TIER: str = "rotation"

# ---------------------------------------------------------------------------
# External API integration (optional)
# ---------------------------------------------------------------------------
# The API client reads its key from the environment. If the key isn't set,
# any script that tries to call the API will fail loudly with a clear
# message — the MAIN pipeline (train/predict) runs fine without it.
#
# Why env vars instead of a constant here?
#   1. Secrets should never live in source code. If the repo is ever shared,
#      anyone with the key can use your quota and impersonate you.
#   2. Env vars are the industry-standard boundary between "code" and
#      "deployment configuration" — same key on your laptop and in CI.
# ---------------------------------------------------------------------------
RAPIDAPI_KEY: str | None = os.getenv("RAPIDAPI_KEY")

# The specific API we're targeting (FlashScore via RapidAPI). If you swap
# to a different provider, this is the ONE place to change the host
# (plus api_client.py's parsing).
FLASHSCORE_HOST: str = "flashscore4.p.rapidapi.com"
FLASHSCORE_BASE_URL: str = "https://flashscore4.p.rapidapi.com"

# FlashScore identifies leagues with TWO opaque IDs (both from their docs):
#   * tournament_template_id — alphanumeric, identifies the league itself
#     (e.g. "xn32I3T4" for the Greek A1)
#   * season_id — numeric string, identifies one season of that league
#     (e.g. "187" for 2025/26)
#
# Unlike api-basketball's single integer league_id, FlashScore requires both.
# Find them by browsing the RapidAPI endpoints page for FlashScore and
# drilling General -> Get countries -> Get country tournaments.
FLASHSCORE_TOURNAMENT_TEMPLATE_ID: str = os.getenv("FLASHSCORE_TOURNAMENT_TEMPLATE_ID", "")
FLASHSCORE_SEASON_ID: str = os.getenv("FLASHSCORE_SEASON_ID", "")

# Maps the team names the API returns to the canonical names we use
# everywhere else. "Kolossos Rhodes" (API) -> "Kolossos Rodou" (our canon).
TEAM_NAME_MAPPING_CSV: Path = RAW_DATA_DIR / "team_name_mapping.csv"

# Where trained artifacts live. joblib is the standard way to persist sklearn models.
MODEL_FILE: Path = MODELS_DIR / "gbl_model.joblib"

# ---------------------------------------------------------------------------
# Column names (single source of truth — avoids typos across files)
# ---------------------------------------------------------------------------
COL_DATE = "game_date"
COL_HOME = "home_team"
COL_AWAY = "away_team"
COL_HOME_SCORE = "home_score"
COL_AWAY_SCORE = "away_score"
COL_HOME_WIN = "home_win"
COL_MARGIN = "margin"  # home_score - away_score
COL_TOTAL = "total_points"  # home_score + away_score

# ---------------------------------------------------------------------------
# Elo rating parameters (chess-style rating adapted for basketball)
# ---------------------------------------------------------------------------
# Every team starts at 1500. Elo is a RELATIVE rating — only differences matter.
ELO_INITIAL: float = 1500.0
# K controls how fast ratings move after each game. 20 is a common sports default.
# Higher K = ratings react faster (good for short seasons, noisy for long ones).
ELO_K: float = 20.0
# Home-court advantage expressed in Elo points. ~65 is a well-known basketball value.
# Equivalent to saying "playing at home is worth ~9% extra win probability".
ELO_HOME_ADVANTAGE: float = 65.0
# The divisor in the Elo expected-score formula (standard chess value).
ELO_DIVISOR: float = 400.0

# ---------------------------------------------------------------------------
# Rolling-window feature parameters
# ---------------------------------------------------------------------------
# L5 = "last 5 games". Smaller windows react faster to form; larger windows are
# more stable. 5 is a sensible middle ground for a ~26-game basketball season.
ROLLING_WINDOW: int = 5

# ---------------------------------------------------------------------------
# Feature list used by the ML models.
# IMPORTANT: these must all be available BEFORE a game is played — otherwise
# we'd be "cheating" by using information from the future (data leakage).
# ---------------------------------------------------------------------------
FEATURE_COLS: list[str] = [
    # Elo-based (strongest single signal)
    "home_elo_pre",
    "away_elo_pre",
    "elo_diff_adj",  # home_elo - away_elo + home-court bonus
    "home_win_prob_elo",  # Elo-implied win probability for the home team
    # Rolling form
    "home_avg_scored_L5",
    "home_avg_conceded_L5",
    "away_avg_scored_L5",
    "away_avg_conceded_L5",
    "home_margin_L5",
    "away_margin_L5",
    "home_form_L5",
    "away_form_L5",
    # Context
    "home_rest_days",
    "away_rest_days",
    "home_games_played",
    "away_games_played",
    "h2h_home_winrate",  # historical head-to-head rate for this pairing
]

# ---------------------------------------------------------------------------
# Targets — what we want to predict
# ---------------------------------------------------------------------------
# We predict MARGIN (home - away) and TOTAL (home + away) instead of the two
# scores directly. Why? Margin and total are (roughly) uncorrelated, whereas
# home_score and away_score move together (a "high-scoring game" lifts both).
# Predicting uncorrelated targets gives the model a cleaner learning signal.
TARGET_CLASSIFICATION: str = COL_HOME_WIN
TARGET_MARGIN: str = COL_MARGIN
TARGET_TOTAL: str = COL_TOTAL

# ---------------------------------------------------------------------------
# Model hyperparameters
# ---------------------------------------------------------------------------
# HistGradientBoosting is the right default on small tabular data: it handles
# missing values natively (no imputation needed), is fast, and rarely overfits
# badly out of the box. Random Forests tend to overfit on ~140 rows.
GBM_PARAMS: dict = {
    "max_iter": 300,
    "learning_rate": 0.05,
    "max_depth": 5,
    "min_samples_leaf": 10,
    "l2_regularization": 1.0,
    "random_state": 42,
}

# Walk-forward evaluation: we train on the first TRAIN_FRACTION of games
# (ordered by DATE) and evaluate on the remaining ones. This mimics real usage:
# at any given point in the season, we only know games that already happened.
TRAIN_FRACTION: float = 0.8

# Minimum games a team must have played before we trust its rolling features.
# Below this, L5 features are NaN and the model falls back on Elo.
MIN_GAMES_FOR_ROLLING: int = 3

# ---------------------------------------------------------------------------
# Ensemble blend
# ---------------------------------------------------------------------------
# The final reported win probability is a weighted average of the ML
# classifier's prediction and the Elo-implied probability:
#
#     final = ENSEMBLE_ML_WEIGHT * p_ml + (1 - ENSEMBLE_ML_WEIGHT) * p_elo
#
# Why blend? On small datasets (hundreds of games, not thousands) a simple
# rating system like Elo is hard to beat, because complex models overfit.
# Blending hedges between the two and is almost always at least as good as
# either alone. The exact weight is picked automatically during training by
# minimising log-loss on the training set — this value is just the fallback
# used if the auto-tuning fails for some reason.
ENSEMBLE_ML_WEIGHT_DEFAULT: float = 0.4
