<!-- ============================================================
     This file is automatically loaded into context at the start of every
     Claude Code session in this project. It is NOT human documentation —
     it's onboarding notes FOR Claude. Keep it under ~200 lines; entries
     past that get truncated.

     Conventions used in this file:
       * Plain prose = instructions Claude must follow.
       * <!-- HTML comments --> = explanations for the human reader.
         They render as invisible in preview but are visible in raw source
         and to Claude. Use them to explain WHY a rule exists.
     ============================================================ -->

# GBL Basketball Predictor

Greek Basketball League (GBL, A1 division) score and win-probability predictor.
Combines an ML model (gradient-boosted trees) with an Elo rating system and a
human override layer for injuries / manual adjustments. Data-light: ~150 games
over a 13-team league.

## Tech stack

- Python 3.14 on Windows. Primary shell is bash (Unix conventions).
- pandas, scikit-learn, joblib, requests, python-dotenv.
- FlashScore API via RapidAPI for result / fixture ingestion
  (see `src/api_client.py`). No scraping.
- pytest for tests; plain CSVs for all persistent data.

## Key commands

<!-- Use these when the user says "train", "run the tests", "record a result", etc.
     Don't invent alternative invocations — these are the canonical ones. -->

| Task | Command |
|---|---|
| Train + evaluate + save model | `python scripts/train.py` |
| Run all tests | `python -m pytest tests/` |
| Lint (matches CI) | `ruff check .` |
| Format (matches CI) | `ruff format .` |
| Record completed match results (interactive) | `python scripts/record_results.py` |
| Predict upcoming fixtures | Run cell 3 of `predictor.ipynb` |
| Sync results + upcoming fixtures from API (dry-run) | `python scripts/sync.py` |
| Sync results + upcoming fixtures from API (commit) | `python scripts/sync.py --commit` |

## Project layout

```
data/raw/
  all_fixtures.csv         # completed games (the history)
  upcoming_fixtures.csv    # games to predict
  rosters.csv              # players + tier (star/starter/rotation/bench)
  absences.csv             # current injuries/suspensions (time-windowed)
  adjustments.csv          # non-player margin overrides (coach, etc.)
  team_name_mapping.csv    # API team names -> our canonical names
src/
  config.py                # ALL paths, hyperparams, tier->points mapping, env vars
  features.py              # Elo + rolling stats + H2H + rest days
  model.py                 # HistGradientBoosting, walk-forward eval, ensemble
  predict.py               # fixture predictions + adjustment overlays
  visualize.py             # HTML card renderer
  api_client.py            # thin wrapper around FlashScore (RapidAPI)
  team_name_mapping.py     # API name -> canonical name translator
  backtest.py              # predicted-vs-actual table from walk-forward test
scripts/
  train.py                 # retrain + evaluate + save model
  record_results.py        # interactive manual result entry
  sync.py                  # API-based results + fixtures sync (dry-run by default)
tests/                     # pytest suite — must stay green
models/                    # saved joblib model (gitignored)
.env                       # API key + league ID (GITIGNORED, never commit)
.env.example               # template showing which env vars are needed
predictor.ipynb            # thin driver on top of src/ (install, train, backtest, predict)
```

## Data conventions — IMPORTANT

<!-- These rules bite hard when forgotten. Each one is enforced by at
     least one test in tests/. If you find yourself wanting to break one,
     stop and ask the user first. -->

- **All dates use dd/mm/yyyy.** When parsing with pandas, always pass
  `dayfirst=True`. ISO strings will fail with a cryptic `%Y-%d-%m` error.
- **Team names are exact and case-sensitive.** Compare to whatever is in
  `all_fixtures.csv`. `predict.py` has a validator with fuzzy
  suggestions for typos.
- **Player importance uses tier strings, not raw points.** Valid tiers:
  `star` / `starter` / `rotation` / `bench`. The points mapping lives at
  `src/config.py::PLAYER_TIER_POINTS` — one place to tune.
- **Walk-forward evaluation is the ONLY honest metric here.** Never use
  a random train/test split on this time-series data — it leaks future
  games into training.
- **Missing CSVs are OK.** `rosters.csv`, `absences.csv`,
  `adjustments.csv` are all optional. Loaders return empty DataFrames,
  not errors.

## Rules for Claude

<!-- Hard-won from prior conversations with this user. Breaking any of
     these is a regression — the user will notice. -->

1. **Never hallucinate GBL player names.** Training-data GBL coverage is
   thin and inconsistent. If asked to seed rosters, ASK the user for names
   rather than inventing them.
2. **Never modify `data/raw/` files without asking.** They are the user's
   curated source of truth. Exception: scripts the user explicitly runs
   (e.g. `record_results.py`) may write to them.
3. **Never use random train/test splits.** Time-based / walk-forward only.
4. **Always pass `dayfirst=True`** when reading CSV dates with pandas.
5. **Don't over-engineer for ~150 rows.** On this dataset, Elo alone still
   nearly matches the full ML model. Simple additions beat sophisticated ones.
6. **Retraining is a few-second operation.** Offer to retrain after any
   change to `all_fixtures.csv`.
7. **Prefer editing existing files over adding new ones.** Abstractions
   should earn their keep — this is a small project.
8. **Tests must stay green, AND ruff must pass.** CI (`.github/workflows/ci.yml`)
   runs `ruff check`, `ruff format --check`, and `pytest`. All three must pass.
   If a change breaks any, fix it before moving on.
9. **API keys live in `.env` only.** Never hardcode a key, never commit `.env`,
   never print a key. If asked to test the API, mock the HTTP session
   (see tests/test_api_client.py for the pattern).
10. **`all_fixtures.csv` is fully API-sourced.** Do not append rows by hand.
    Use `python scripts/sync.py --commit` to fetch new games. Running sync
    is idempotent; safe to run any time.
11. **When editing files in `src/`, remind the user to restart the Jupyter
    kernel** before re-running notebook cells. Python caches imports, and
    stale kernel state produces confusing line-number mismatches.

## Current state

<!-- Snapshot of what's true right now. Update when it changes. -->

- 154 games in history (2025/26 season, Greek A1), 13 teams. All rows
  sourced from the FlashScore API — no manual additions.
- 6 upcoming fixtures in `upcoming_fixtures.csv` (also API-sourced).
- Model: HistGradientBoosting classifier + regressors, ensembled with Elo.
- Tuned blend weight: `ML * 0.45 + Elo * 0.55`.
- Walk-forward test metrics (31 games held out):
  - Win accuracy: ~71% (ensemble), ~74% (Elo alone), ~71% (ML alone).
  - Margin: MAE ~12 pts, RMSE ~15 pts, R² ≈ 0.09.
  - Total points: MAE ~15 pts, RMSE ~18 pts, R² ≈ 0.13.
- `rosters.csv` has only the 13 team stubs (no real player data); stubs
  are silently skipped by the loader.
- `absences.csv` and `adjustments.csv` are empty.

## Known limits

<!-- For future sessions asking "why doesn't this work better?" -->

- Margin R² ~0.09 — barely positive. ~150 rows is too few to beat Elo
  decisively; no sophisticated tuning will change that.
- No box-score features (pace, eFG%, ORtg/DRtg). FlashScore doesn't
  expose those either; would need a different feed.
- No live injury feed; absences are user-entered via rosters.csv +
  absences.csv (tier-based margin adjustments).
- Team-name string match is exact across files — no fuzzy matching at
  lookup time, only at fixture-validation time.

## When in doubt

<!-- Default behaviour when the user's intent isn't 100% clear. -->

- Ask before editing `data/raw/` files.
- Ask before adding new features / new modules / new files.
- Do NOT ask before running tests or retraining.
- Assume the user is the domain expert on GBL — defer to them on player
  ratings, tier choices, and which players matter.
