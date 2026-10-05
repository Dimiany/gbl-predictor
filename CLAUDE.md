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
| Sync + retrain + predict (the normal path) | Run cells 2 then 3 of `predictor.ipynb` (cell 2 auto-syncs from FlashScore before training) |
| Predict upcoming fixtures (next round only) | Run cell 3 of `predictor.ipynb` |
| **What the user actually does** (no terminal): double-click the desktop shortcut "GBL Predictor" → `GBL Predictor.bat` → `scripts/serve.py`; the page's ⟳ Ανανέωση button runs the full update | — |
| Sync + retrain + predict + build HTML dashboard | `python scripts/build_dashboard.py` (`--no-sync` to skip API+retrain, `--no-log` to skip logging, `--open` to open it) |
| View prediction history & model accuracy | Run `models_accuracy.ipynb` |
| Sync results + upcoming fixtures from API (dry-run, escape hatch) | `python scripts/sync.py` |
| Sync results + upcoming fixtures from API (commit, escape hatch) | `python scripts/sync.py --commit` |

## Project layout

```
data/raw/
  all_fixtures.csv         # completed games (the history) — API-sourced, kept chronological
  upcoming_fixtures.csv    # games to predict — overwritten wholesale by sync
  rosters.csv              # players + tier (star/starter/rotation/bench)
  absences.csv             # current injuries/suspensions (time-windowed)
  adjustments.csv          # non-player margin overrides (coach, etc.)
  team_name_mapping.csv    # API team names -> our canonical names
data/team_logos.csv        # canonical team -> crest URL (FlashScore CDN), refreshed by sync
data/
  prediction_history.csv   # one row per fixture predicted, upserted on each
                           # 'Generate Predictions' click. Drives the accuracy view.
src/
  config.py                # ALL paths, hyperparams, tier->points mapping, env vars
  features.py              # Elo + rolling stats + H2H + rest days
                           # + season W-L record + standings rank (win% with margin tiebreak)
  model.py                 # linear margin + total models, P = Phi(margin/sigma), rolling walk-forward
  predict.py               # fixture predictions + adjustment overlays
                           # (returns [] for empty fixture lists — callers safe)
  visualize.py             # HTML renderers: fixtures table, prediction cards, accuracy table
  ui.py                    # ipywidgets glue for predictor.ipynb (button, slot, dark zone)
  dashboard.py             # static HTML dashboard (standings, Elo, next round, results, schedule)
  api_client.py            # thin wrapper around FlashScore (RapidAPI)
  team_name_mapping.py     # API name -> canonical name translator
  sync.py                  # reusable sync engine — run_sync() + sync_for_notebook()
  prediction_log.py        # upsert + accuracy-view join (predictions ⨝ all_fixtures)
  backtest.py              # predicted-vs-actual table from walk-forward test (legacy,
                           # no longer wired into the notebook but still importable)
scripts/
  train.py                 # retrain + evaluate + save model
  record_results.py        # interactive manual result entry
  sync.py                  # thin CLI wrapper around src/sync.run_sync (escape hatch)
  build_dashboard.py       # sync + retrain + log next round + write dashboard/index.html
  serve.py                 # local server (127.0.0.1:8765) behind the Refresh button
GBL Predictor.bat          # double-click launcher (desktop shortcut points here)
dashboard/                 # generated index.html + assets/ crest cache (gitignored)
tests/                     # pytest suite — must stay green
models/                    # saved joblib model (gitignored)
.env                       # API key + league ID (GITIGNORED, never commit)
.env.example               # template showing which env vars are needed
predictor.ipynb            # thin driver on top of src/ (install → sync+train → predict)
models_accuracy.ipynb      # aggregated table of every prediction vs its actual result
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
5. **Don't over-engineer for ~180 rows.** A rolling walk-forward comparison
   (05/10/2026) found gradient boosting the worst-calibrated option; a 3-feature
   linear margin model matched the ML+Elo blend and replaced it. Simple wins.
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
10. **`all_fixtures.csv` is fully API-sourced and kept chronological.** Do not
    append rows by hand. The train cell of `predictor.ipynb` auto-syncs via
    `src.sync.sync_for_notebook()` before retraining; `python scripts/sync.py
    --commit` is the manual escape hatch. Sync is idempotent. Writes are sorted
    oldest→newest so the bottom of the file is always the latest game.
11. **When editing files in `src/`, remind the user to restart the Jupyter
    kernel** before re-running notebook cells. Python caches imports, and
    stale kernel state produces confusing line-number mismatches.
12. **Auto-sync must never block the notebook.** `sync_for_notebook()` swallows
    every exception and returns a one-line status string. If you change it,
    keep that contract — a transient API blip can't be allowed to crash the
    train cell.
13. **`data/prediction_history.csv` is predictions-only.** Actuals are joined
    in at display time from `all_fixtures.csv` (in `prediction_log.build_accuracy_view`).
    Don't denormalize the actuals into the log unless the user explicitly asks —
    one source of truth per fact.

## FlashScore API quirks (handled in src/sync.py — keep it that way)

- `/tournaments/results` gives the **regulation-time** score, so overtime games
  look tied. Sync resolves every tie via `/matches/details` (`home_total` /
  `away_total`), one request per tie, and never writes a tie to history.
- The API sometimes lists the same game twice; sync dedupes results, fixtures,
  and the written history on (date, home, away).
- Season IDs are NOT sequential: 2025/26 = `187`, 2026/27 = `190`
  (`FLASHSCORE_TOURNAMENT_TEMPLATE_ID=xn32I3T4`). There is no seasons-list
  endpoint; probe `/tournaments/results` with candidate IDs.
- Free plan: 500 requests/month. A normal sync costs ~5-10.

## Seasons

`all_fixtures.csv` holds multiple seasons. `features.season_of()` derives the
season from the date (Aug+ = new season). At each team's first game of a new
season, `TeamState.start_season()` resets W-L, games played, L5 form and rest
days, and regresses Elo toward 1500 (`ELO_SEASON_CARRYOVER = 0.75`). Standings
rank only teams in the same season.

## Current state

<!-- Snapshot of what's true right now. Update when it changes. -->

- 181 games in history as of 05/10/2026: 174 from 2025/26 (regular season +
  playoffs; champion Olympiacos) and 7 from 2026/27 round 1. 14 teams in
  2026/27: Panionios relegated; new teams "Doxa Lefkadas" (API: Lefkadas) and
  "Vikos Falcons Ioanninon" (API: Vikos), names chosen by the user.
- 175 upcoming 2026/27 fixtures (through April 2027). The UI and dashboard
  only predict the next round (`predict.next_round`, 4-day window).
- `data/prediction_history.csv`: 2025/26 predictions (model `ensemble-v1`,
  blank `model_version`) graded 12/14; round 2 of 2026/27 (10-11/10) logged
  with `margin-v2`, pending. Grading tolerates games rescheduled by ≤3 days.
- Model `margin-v2` (cfg.MODEL_VERSION; bump it whenever the method changes):
  - margin = LinearRegression(elo_diff_adj, form_diff, win_pct_diff)
  - P(home win) = Phi(margin / sigma), sigma = residual std (~12.4)
  - total = Ridge(alpha=50) on the four L5 scored/conceded columns
  - scoreline from (margin, total), rounded so it never ties and always
    agrees with the probability. Old setup (HGB classifier + regressors
    blended with Elo) could disagree — e.g. Aris–AEK 10/10/2026.
- Rolling walk-forward (60-game warm-up, refit every game day; 121 games):
  - Win accuracy 73% (Elo alone 76%; always-home 63%; ±4 noise).
  - Log loss 0.506 (Elo 0.552), Brier 0.171 (Elo 0.183).
  - Margin MAE 10.1 pts, R² 0.30. Total MAE 15.4 pts.
- `rosters.csv` has only the 13 team stubs (no real player data); stubs
  are silently skipped by the loader.
- `absences.csv` and `adjustments.csv` are empty.

## Known limits

<!-- For future sessions asking "why doesn't this work better?" -->

- Margin R² ~0.30, but accuracy differences between models are within
  noise on ~120 evaluated games; compare log loss / Brier, not accuracy.
- Promoted teams start at Elo 1500, which overrates them early on.
- No box-score features (pace, eFG%, ORtg/DRtg). FlashScore doesn't
  expose those either; would need a different feed.
- No live injury feed; absences are user-entered via rosters.csv +
  absences.csv (tier-based margin adjustments).
- Team-name string match is exact across files — no fuzzy matching at
  lookup time, only at fixture-validation time.

## The user does not use the terminal

They said so explicitly. Anything they need to do must be a button on the
site or a double-click. When a change needs a manual step (new API key, new
team mapping), do it for them and tell them in plain Greek what changed.
Keep the in-site Οδηγίες page (`pages.help` in src/dashboard.py) current.

## When in doubt

<!-- Default behaviour when the user's intent isn't 100% clear. -->

- Ask before editing `data/raw/` files.
- Ask before adding new features / new modules / new files.
- Do NOT ask before running tests or retraining.
- Assume the user is the domain expert on GBL — defer to them on player
  ratings, tier choices, and which players matter.
