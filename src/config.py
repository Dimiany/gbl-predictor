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
# Crest URL per canonical team name, refreshed by every sync from the API
# payload (no extra requests). The dashboard downloads and inlines them.
TEAM_LOGOS_CSV: Path = DATA_DIR / "team_logos.csv"
# Basket League logo on FlashScore's CDN (from /tournaments/details).
# Official crests (scripts/fetch_crests.py): team -> source image on esake.gr,
# stored cropped + square in src/web/assets/crests. Preferred over FlashScore.
CREST_SOURCES_CSV: Path = DATA_DIR / "crest_sources.csv"
CRESTS_DIR: Path = PROJECT_ROOT / "src" / "web" / "assets" / "crests"
# 2x the largest on-page crest (68 CSS px) plus headroom, for sharp retina screens.
CREST_SIZE: int = 192
# Full-size crests cost one /matches/details request per game (two teams
# each); sync spends at most this many per run, only on teams still missing one.
CREST_REQUESTS_PER_SYNC: int = 8
LEAGUE_LOGO_URL: str = "https://static.flashscore.com/res/image/data/4A1mgVjD-C8llyQ7L.png"

# Where trained artifacts live. joblib is the standard way to persist sklearn models.
MODEL_FILE: Path = MODELS_DIR / "gbl_model.joblib"

# The static HTML dashboard written by scripts/build_dashboard.py (gitignored —
# it's regenerated from the data on every build).
DASHBOARD_FILE: Path = PROJECT_ROOT / "dashboard" / "index.html"
# When the site's data was last synced from the API (written by
# src.web.update_site). The desktop launcher only re-syncs if this is stale.
LAST_SYNC_FILE: Path = DATA_DIR / ".last_sync"
# Contact-form messages (written by src/web/server.py; gitignored).
CONTACT_MESSAGES_CSV: Path = DATA_DIR / "contact_messages.csv"
# Optional address for the Contact page's mailto fallback when the page is
# opened as a plain file. Empty = no address is published on the page.
CONTACT_EMAIL: str = os.getenv("GBL_CONTACT_EMAIL", "")
# Local-only port for scripts/serve.py (the Refresh button's backend).
SERVE_PORT: int = 8765
# The launcher re-syncs on start-up if the last sync is older than this.
AUTO_SYNC_AFTER_HOURS: float = 6.0

# The site's name everywhere (header, title, footer, about, share text).
SITE_NAME: str = "TipOff"
SITE_TAGLINE: str = "Greek Basketball Predictor"
SITE_SLOGAN: str = "Οι αριθμοί, πριν το τζάμπολ."
SITE_URL: str = "https://tipoff.gr"
# Share card (Open Graph image) shipped next to index.html; 1200x630.
SHARE_CARD_FILE: str = "og-card.jpg"

# Where this build of the site will be shown:
#   local   — the desktop app (scripts/serve.py): Refresh + CSV contact form
#   live    — the public site on Firebase Hosting (built by GitHub Actions)
#   preview — a pull request's temporary Firebase preview link (noindex, test data)
SITE_MODE: str = os.getenv("GBL_SITE_MODE", "local")
SITE_MODES: tuple[str, ...] = ("local", "live", "preview")
# Firebase web config. Public by design (it ships in every page); access is
# governed by firestore.rules, not by keeping these secret.
FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_API_KEY: str = os.getenv("FIREBASE_API_KEY", "")
# Firestore collection the public contact form writes to, per site mode.
CONTACT_COLLECTIONS: dict[str, str] = {
    "live": "contact_messages",
    "preview": "test_contact_messages",
}
# "1" once GitHub Actions owns sync + prediction logging: the desktop app's
# Refresh then pulls the cloud's data with git instead of calling the API, so
# the two never log different predictions or race for the monthly quota.
CLOUD_SYNC: bool = os.getenv("GBL_CLOUD_SYNC", "") == "1"
# The scheduled cloud run calls the API only when there's a reason to
# (src/web/build.sync_due): results due from the last few days, an unlogged
# game coming up, or the weekly check that catches reschedules.
SITE_TIMEZONE: str = "Europe/Athens"
SYNC_RESULTS_LOOKBACK_DAYS: int = 3
SYNC_LOG_LOOKAHEAD_DAYS: int = 2
SYNC_WEEKLY_WEEKDAY: int = 0  # Monday

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
# At each new season every rating is pulled back toward ELO_INITIAL, keeping
# this fraction of its distance from the mean. Off-season roster turnover in
# the GBL is heavy, so last June's rating is only partly informative in October.
# 1.0 = full carry-over, 0.0 = everyone restarts at 1500.
ELO_SEASON_CARRYOVER: float = 0.75

# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------
# A GBL season runs ~October to June. Games from this month onward belong to
# the season starting that year (e.g. 2026-10-04 -> 2026; 2027-03-01 -> 2026).
SEASON_START_MONTH: int = 8

# A GBL round is spread over ~3 days (Sat-Mon). Fixtures within this many days
# of the earliest upcoming one count as "the next round".
NEXT_ROUND_WINDOW_DAYS: int = 4

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
    # Season-long W-L record + standings position. Win % captures cumulative
    # quality (more stable than the L5 rolling form), and rank tells the model
    # whether this is a top-of-table vs. bottom-of-table matchup directly.
    "home_season_wins",
    "home_season_losses",
    "home_season_win_pct",
    "away_season_wins",
    "away_season_losses",
    "away_season_win_pct",
    "home_rank",
    "away_rank",
    "rank_diff",  # home_rank - away_rank; negative = home team higher in table
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
# Model (see src/model.py for why it's linear)
# ---------------------------------------------------------------------------
# Bumped whenever the prediction method changes. Logged next to every
# prediction in data/prediction_history.csv, so old and new models' records
# stay distinguishable. Rows without a version came from "ensemble-v1"
# (HistGradientBoosting classifier blended with Elo, until 05/10/2026).
MODEL_VERSION: str = "margin-v2"

# Inputs of the margin model (derived in model.model_inputs):
#   elo_diff_adj — Elo gap incl. home court; form_diff — L5 margin difference;
#   win_pct_diff — season win-% difference.
MARGIN_FEATURES: list[str] = ["elo_diff_adj", "form_diff", "win_pct_diff"]

# Inputs of the total-points model: each side's L5 scoring and conceding.
TOTAL_FEATURES: list[str] = [
    "home_avg_scored_L5",
    "home_avg_conceded_L5",
    "away_avg_scored_L5",
    "away_avg_conceded_L5",
]
# Ridge shrinkage for the total model — L5 averages are noisy, so the
# prediction should lean toward the league mean.
TOTAL_RIDGE_ALPHA: float = 50.0

# Rolling walk-forward evaluation: score every game day using only earlier
# days, once at least this many games are available to train on.
WALK_FORWARD_WARMUP: int = 60

# Minimum games a team must have played before we trust its rolling features.
# Below this, L5 features are NaN and the model treats form as neutral.
MIN_GAMES_FOR_ROLLING: int = 3
