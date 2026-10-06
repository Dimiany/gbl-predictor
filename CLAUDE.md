<!-- Onboarding notes FOR Claude, loaded at the start of every session in this
     project. Keep it under ~300 lines; content past that gets truncated.
     Plain prose = instructions to follow. HTML comments = the "why", for humans. -->

# TipOff · Greek Basketball Predictor

Score and win-probability predictor for the Greek Basket League (Stoiximan GBL,
A1). A 3-feature linear margin model on top of Elo, with an optional human
override layer (absences / adjustments). About 180 games, 14 teams. The output
is a website: a desktop app on the user's PC plus a public copy on Firebase.

Brand (since 06/10/2026): **TipOff** · *Greek Basketball Predictor*, domain
tipoff.gr, slogan «Οι αριθμοί, πριν το τζάμπολ.» All names live in `config.SITE_*`
(JS: `BRAND`). Internal names (repo, Firebase project `gbl-predictor`) stay.

## The user

- Greek-speaking PAOK fan and the GBL domain expert. Reply in Greek; defer to
  them on players, tiers and team names.
- **They never use the terminal.** Everything they do must be a button on the
  site, a double-click, or clicks in a web console. When a change needs a manual
  step (new API key, team mapping, secret), do it for them and explain in plain
  Greek what changed. Keep the site's Οδηγίες page (`18-help.js`) current.

## Where it runs

```
Desktop app (local)          GitHub Actions (cloud brain)         Firebase (public site)
TipOff.bat                   .github/workflows/site.yml           Hosting: the built page
 -> scripts/serve.py          nightly: sync if due -> retrain      Firestore: contact form
 -> 127.0.0.1:8765            -> predict -> log -> commit data      (REST, create-only rules)
 ⟳ Ανανέωση button             -> deploy to Firebase Hosting
                              preview.yml: PR -> preview link
```

- `GBL_SITE_MODE` picks the build: `local` (Refresh button, CSV contact form),
  `live` (no Refresh; form -> Firestore `contact_messages`), `preview` (yellow
  "ΔΟΚΙΜΑΣΤΙΚΗ ΕΚΔΟΣΗ" strip, noindex, form -> `test_contact_messages`).
- Once the cloud is live, **GitHub Actions owns sync and prediction logging.**
  The desktop `.env` then has `GBL_CLOUD_SYNC=1`, so Refresh runs
  `git pull --ff-only` + retrain + rebuild and never calls the API or logs.
  <!-- One writer per fact: two loggers would record different predictions for
       the same game and race for the 500-request monthly quota. -->
- Bot commits ("data: automatic update") land on `main`. Run `git pull` before
  any work; never hand-edit data files the bot writes.
- Work on a branch and open a PR: CI runs, preview.yml publishes it to the fixed
  test site https://gbl-predictor-test.web.app (2nd Hosting site in firebase.json)
  and comments the link; the user approves. Merging to `main` deploys live
  (site.yml on push, `--only hosting:gbl-predictor`). Live: https://gbl-predictor.web.app
- Both workflows skip until the repo variable `FIREBASE_PROJECT_ID` exists.
  Secrets: `RAPIDAPI_KEY`, `FIREBASE_SERVICE_ACCOUNT` (JSON). Variables:
  `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FLASHSCORE_TOURNAMENT_TEMPLATE_ID`,
  `FLASHSCORE_SEASON_ID`. Set them with `gh secret set` / `gh variable set`.
- Free tiers only: Firebase Spark (no card), Actions minutes. Cloud Functions
  need the Blaze plan; ask the user before anything that requires it.

## Tech stack

- Windows 11. Local Python 3.14, CI Python 3.13, code targets >= 3.10.
  PowerShell is the primary shell; Git Bash is available.
- pandas, scikit-learn, joblib, requests, python-dotenv. Node is only used for
  `node --check` in tests and `npx firebase-tools@15` in the workflows.
- FlashScore via RapidAPI (`src/api_client.py`). No scraping.
- pytest + ruff. Plain CSVs for all persistent data.

## Key commands

| Task | Command |
|---|---|
| Tests (must pass) | `python -m pytest tests/` |
| Lint + format (match CI) | `ruff check .` and `ruff format .` |
| Full update + build the page | `python scripts/build_dashboard.py` (`--no-sync`, `--no-log`, `--open`, `--auto` = cloud "only if due") |
| Desktop app (what the user double-clicks) | desktop shortcut "TipOff" (icon `src/web/assets/tipoff.ico`) -> `TipOff.bat` -> `python scripts/serve.py` |
| Retrain + evaluate only | `python scripts/train.py` |
| Refresh official crests | `python scripts/fetch_crests.py [TEAM ...]` (sources: `data/crest_sources.csv`) |
| Re-predict a missed round | `python scripts/backfill_predictions.py dd/mm/yyyy dd/mm/yyyy` (adds retroactive rows only) |
| Sync only (escape hatch) | `python scripts/sync.py` (dry run), `--commit` to write |
| Cloud update now | GitHub -> Actions -> "Site" -> Run workflow, or `gh workflow run site.yml` |
| Notebooks (legacy UI) | `predictor.ipynb` (cell 2 sync+train, cell 3 predict), `models_accuracy.ipynb` |

`scripts/record_results.py` (manual result entry) predates API sync. Don't use
it while cloud sync is on: it writes `all_fixtures.csv` by hand.

## Project layout

```
data/raw/all_fixtures.csv      completed games, API-sourced, chronological (bot-written)
data/raw/upcoming_fixtures.csv games to predict, replaced on every sync (bot-written)
data/raw/team_name_mapping.csv API name -> canonical name
data/raw/rosters.csv, absences.csv, adjustments.csv   optional override layer (user-curated)
data/team_logos.csv            team -> FlashScore image URLs, small + crest_url (bot-written)
data/crest_sources.csv         team -> official crest on esake.gr + crop rule (user-approved)
data/prediction_history.csv    one row per predicted fixture (bot-written)
src/config.py                  ALL paths, hyperparameters, env vars, site modes
src/features.py                Elo, rolling L5 stats, H2H, rest, W-L, standings, seasons
src/model.py                   margin + total models, P = Phi(margin/sigma), walk-forward
src/predict.py                 fixture predictions, overrides, next_round()
src/prediction_log.py          upsert log + accuracy view (log ⨝ all_fixtures)
src/sync.py                    run_sync() / sync_for_notebook(): API -> CSVs
src/api_client.py              FlashScore wrapper; team_name_mapping.py translator
src/ui.py, visualize.py        notebook widgets/HTML; backtest.py = legacy, unused by the site
src/web/data.py                every number on the site -> one JSON dict; site_settings()
src/web/render.py              HTML shell, hash-based CSP, inlines CSS + JS as one IIFE
src/web/build.py               update_site(), pull_latest(), sync_due() for the cloud run
src/web/server.py              local server: POST /api/refresh, POST /api/contact
src/web/contact.py             local contact storage (data/contact_messages.csv, gitignored)
src/web/assets/                app.css + js/NN-*.js (01-core ... 1x-pages ... 90-app)
src/web/assets/crests/         official crests, 192 px WebP (scripts/fetch_crests.py)
scripts/                       build_dashboard.py, serve.py, sync.py, train.py, fetch_crests.py,
                               backfill_predictions.py, record_results.py
firebase.json, firestore.rules Hosting config (serves dashboard/) + database rules
.github/workflows/             ci.yml (lint+tests), site.yml (live), preview.yml (PR links)
dashboard/, models/            generated, gitignored
.env                           secrets + IDs, gitignored; .env.example lists every variable
```

## Data conventions

- CSV dates are dd/mm/yyyy: always `pd.to_datetime(..., dayfirst=True)`. API dates
  are ISO: parse those with `pd.Timestamp(...)`, never `dayfirst` (it swaps day
  and month).
- Team names are exact and case-sensitive across all files. Fuzzy suggestions
  exist only in fixture validation (`predict.py`).
- Player importance is a tier (`star`/`starter`/`rotation`/`bench`), mapped to
  points in `config.PLAYER_TIER_POINTS`.
- Missing optional CSVs are fine: loaders return empty frames.

## Rules for Claude

1. Never invent GBL player names. Ask the user.
2. Ask before modifying user-curated `data/raw/` files (mapping, rosters,
   absences, adjustments). API-sourced files change only via sync.
3. Time-based evaluation only (walk-forward). Never a random split.
4. Keep it simple for ~180 rows: gradient boosting lost to the linear margin
   model on log-loss (05/10/2026). Prefer editing files over adding modules.
5. `ruff check`, `ruff format --check` and `pytest` must all pass (CI).
6. API keys and the Firebase service-account JSON live only in `.env` / GitHub
   Secrets. Never print, hardcode or commit them. Delete a downloaded key file
   once it's stored as a secret. Mock HTTP in tests (see `test_api_client.py`).
   The Firebase web `apiKey` and project ID are public by design; Firestore
   rules are the protection.
7. `sync_for_notebook()` and `pull_latest()` never raise and return a status
   line. Keep that: an API or git hiccup must never block a build.
8. `prediction_history.csv` holds predictions only. Actuals are joined at display
   time. One source of truth per fact. A row made after its game day is
   retroactive (`predict_retroactively`: fit only on games before the window).
   The site labels it «αναδρομική» and keeps it out of the pre-game record
   (`preGameLog`). Never overwrite a real pre-game row with one (`overwrite=False`).
9. Bump `cfg.MODEL_VERSION` whenever the prediction method changes; it's logged
   with every prediction.
10. After editing `src/`, remind the user to restart a running Jupyter kernel
    (only matters for the notebooks).
11. Contact form topics live in two places: `TOPICS` in `17-contact.js` and
    `firestore.rules`. `test_web.py` checks that they match.

## FlashScore API (quirks handled in src/sync.py, keep them there)

- `/tournaments/results` gives regulation-time scores, so overtime games look
  tied. Sync resolves each tie with `/matches/details` (`home_total`/`away_total`)
  and never writes a tie.
- The API sometimes lists a game twice: sync dedupes on (date, home, away).
- List endpoints only have 30x30 crests (`small_image_path`). `/matches/details` has
  100x100 (`image_path`): sync fetches those once per team into
  `team_logos.csv:crest_url` (at most `CREST_REQUESTS_PER_SYNC`), and the site prefers them.
- Season IDs aren't sequential: 2025/26 = `187`, 2026/27 = `190`, template
  `xn32I3T4`. No seasons endpoint; probe `/tournaments/results` with candidates.
- Free plan: 500 requests a month, about 5-10 per sync. The nightly cloud run
  syncs only when `sync_due()` says so: results due in the last 3 days, an
  unlogged game within 2 days, or the Monday weekly check.

## Seasons

`features.season_of()`: August onward = new season. At a team's first game of
a season, `TeamState.start_season()` resets W-L, L5 form and rest, and regresses
Elo toward 1500 (`ELO_SEASON_CARRYOVER = 0.75`). Standings rank within a season.

## Model `margin-v2`

- margin = LinearRegression(elo_diff_adj, form_diff, win_pct_diff)
- P(home win) = Phi(margin / sigma), sigma = residual std (about 12.4)
- total = Ridge(alpha=50) on the four L5 scored/conceded columns
- scoreline from (margin, total), rounded so it never ties and always agrees
  with the probability
- Rolling walk-forward (60-game warm-up, refit every game day, 121 games):
  accuracy 73% (Elo alone 76%, always-home 63%, ±4 noise), log-loss 0.506 (Elo
  0.552), Brier 0.171, margin MAE 10.1, R² 0.30, total MAE 15.4.
- Compare models on log-loss / Brier, not accuracy: differences of 3-4 points
  on ~120 games are noise.

## Website conventions

- No framework, no CDN, no npm in the page: plain ES2020 in `assets/js`, one
  concern per file, concatenated in file-name order into one strict-mode IIFE.
  A new page = a new `1x-<name>.js` registering `pages.<name>`.
- DOM via `h()` / `s()` (text nodes only, never innerHTML with data). The CSP
  allows only the bundled script by hash: no inline handlers, eval or external
  scripts. Images must be data URIs. Network: same origin + Firestore only.
- Site-mode flags in `01-core.js`: `SITE`, `PUBLIC`, `SERVED`. Anything that needs
  the local server must check `SERVED`; public-only text checks `PUBLIC`.
- Every metric shown gets an entry in `02-metrics.js` (ⓘ tooltip + guide card).
- Every section gets a `sectionHead(title, plain-Greek explanation)`; the user asked
  for explanatory headings. Score boxes are labelled «Αποτέλεσμα» / «Πρόβλεψη».
- `autoScroll(strip)` (01-core) = endless self-scrolling strip with mouse drag,
  pause on hover/focus/off-screen, none under reduced motion (home ticker).
- Chart colours (`--accent`/`--neg` per theme in app.css) were validated with
  the dataviz palette checker. Re-validate if you change them or the surfaces.
- "Hit" = favourite probability >= 0.8 and correct (gold). "Sharp" = correct
  and margin within 3 points (🎯). Constants live in `01-core.js`.
- `tests/test_web.py` runs `node --check` on the bundle, checks the CSP hash,
  site modes and rules/form consistency.
- Check visual changes with a headless Edge screenshot before calling them done.
- Share card: `assets/og-card.jpg` (1200x630, static) is copied next to index.html
  with robots.txt + sitemap.xml by `build.write_site_files`; Open Graph tags in
  `render.share_meta` point at `SITE_URL`. Canonical = https://tipoff.gr/ (live only).
  Search Console uses a DNS TXT record at papaki (Domain property).
- Crests: official league images (esake.gr) in `assets/crests`, fitted inside
  the round frame (`.crest` has `border-radius:50%` and a white disc in dark
  mode). `crop=sponsor` strips a sponsor logo below the crest; `crop=none`
  keeps stars. Kolossos' "H" is part of its official crest. FlashScore
  images are only the fallback. New team: add a row and rerun fetch_crests.

## Current state (06/10/2026)

- 181 games in history: 174 from 2025/26 (champion Olympiacos) and 7 from
  2026/27 round 1. 175 upcoming fixtures (to April 2027). The site predicts
  only the next round (`predict.next_round`, 4-day window).
- 14 teams in 2026/27. Panionios was relegated. New teams are "Doxa Lefkadas"
  (API: Lefkadas) and "Vikos Falcons Ioanninon" (API: Vikos), names chosen by
  the user.
- `prediction_history.csv`: 2025/26 rows (blank `model_version` = `ensemble-v1`)
  graded 12/14. Round 1 of 2026/27 (03-04/10) was added retroactively on
  06/10/2026 (6/7, not in the record). Round 2 (10-11/10) is logged pre-game.
  Grading tolerates games rescheduled by up to 3 days.
- `rosters.csv` has only stubs for the 2025/26 teams (no players, no stubs yet
  for the two new teams). `absences.csv` and `adjustments.csv` are empty.
- Public site live since 06/10/2026: https://gbl-predictor.web.app (Firebase
  project `gbl-predictor`, Spark plan). Test site: https://gbl-predictor-test.web.app.
  Contact messages: Firebase console → Firestore → `contact_messages`. The
  original desktop machine has `GBL_CLOUD_SYNC=1`. Custom domain **tipoff.gr**
  (papaki.gr DNS: A 199.36.158.100, TXT hosting-site=gbl-predictor; www → apex
  redirect in Firebase) live since 06/10/2026.

## Ideas backlog (agreed with the user, not started)

Offer these when the user asks "what next". Ask before starting any of them.
- AI (Claude API, key as a GitHub secret): match previews in Greek, per-team
  news summary, injury hints from news (user approves before they count),
  weekly report. A live "ask the model" chat needs a server (Blaze plan: ask).
- Model: lower starting Elo for promoted teams; Monte Carlo season simulation
  (title / playoff / relegation odds); real rosters + absences (names from the
  user only).
- Site: user-vs-model prediction game (Firestore + Auth), side-by-side team
  comparison, Open Graph share card, custom domain (avoid "GBL"/"Stoiximan"
  in the name: trademarks), App Check on the contact form.

## Setting up a new machine

When the user says "στήσε το περιβάλλον" on another computer:
1. Check git, Python >= 3.10, node, gh (tell them in Greek what to install if
   one is missing). Then `pip install -r requirements.txt ruff`.
2. Create `.env` with `GBL_CLOUD_SYNC=1`, `FLASHSCORE_TOURNAMENT_TEMPLATE_ID=xn32I3T4`
   and `FLASHSCORE_SEASON_ID=190`. No secret is needed for normal work: sync and
   deploys run in GitHub Actions. Add `RAPIDAPI_KEY` only if they want direct API
   calls; they get it from rapidapi.com, never copied over chat or email.
3. `gh auth login` (browser flow), then `python -m pytest tests/` and `ruff check .`.
4. Optional: desktop shortcut "TipOff" to `TipOff.bat`.
5. Claude's memory (preferences, history) is per machine. Everything the next
   session needs must live in this file.
Never work on two machines at once without `git pull` first.

## Known limits

- Promoted teams start at Elo 1500, which overrates them early.
- No box-score features (pace, eFG%, ratings): FlashScore doesn't expose them.
- No live injury feed: absences are user-entered.
- The contact form has a honeypot but no App Check / rate limit yet.

## When in doubt

- Ask before editing user-curated data, adding features or new modules, or
  anything that costs money or publishes something.
- Don't ask before running tests, ruff, retraining or a local `--no-sync --no-log` build.
