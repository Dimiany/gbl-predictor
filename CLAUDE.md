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
| Full update + build the site | `python scripts/build_dashboard.py` (`--no-sync`, `--no-log`, `--open` = serve on 127.0.0.1, `--auto` = cloud "only if due") |
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
src/web/render.py              addresses (PAGE_SLUGS, TAB_SLUGS, site_pages), one HTML page per
                               address, shared app.css / app.js (one IIFE) / data.js, CSP
src/web/build.py               update_site(), pull_latest(), sync_due() for the cloud run
src/web/server.py              local server: clean addresses + 404 like Firebase, POST /api/refresh, /api/contact
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

## Model `margin-v3` (since 07/10/2026; v2 = same model with the old Elo rules)

- margin = LinearRegression(elo_diff_adj, form_diff, win_pct_diff)
- P(home win) = Phi(margin / sigma), sigma = residual std (about 12.4)
- total = Ridge(alpha=50) on the four L5 scored/conceded columns
- scoreline from (margin, total), rounded so it never ties and always agrees
  with the probability
- Elo rules (v3, chosen on walk-forward log-loss, user-approved): promoted teams
  start at `ELO_PROMOTED_START` 1400 (a team with no games while the league has an
  earlier season, `features.enter_season`); season carry-over 0.85; K 40 instead of 20
  while either team is in its first 8 games of a season (`game_k`, also used by the
  site's Elo chart). Prompted by Panathinaikos-Vikos (round 1): v2 said +6 / 68%, v3 +11 / 81%.
- Rolling walk-forward (60-game warm-up, refit every game day, 121 games):
  accuracy 73% (Elo alone 75%, always-home 63%, ±4 noise), log-loss 0.497 (v2
  0.506, Elo 0.522), Brier 0.167, margin MAE 9.96, R² 0.33, total MAE 15.4.
- Compare models on log-loss / Brier, not accuracy: differences of 3-4 points
  on ~120 games are noise.

## Website conventions

- No framework, no CDN, no npm in the page: plain ES2020 in `assets/js`, one
  concern per file, concatenated in file-name order into one strict-mode IIFE.
  A new page = a new `1x-<name>.js` registering `pages.<name>`.
- Real addresses in English terms (user's call, 07/10/2026): `/predictions`,
  `/standings`, `/teams`, `/teams/<slug>`, `/schedule`, `/model`, `/about`,
  `/contact`, `/help`; tabs below them (`/predictions/history`,
  `/predictions/hall-of-fame`, `/predictions/games`, `/model/metrics`,
  `/model/how-it-works`, `/teams/paok/results`, `/teams/paok/schedule`); a page's
  first tab lives at the page's own address. The first public addresses
  (06/10/2026) were greeklish (`/vathmologia`, `/omades/...`): `firebase.json`
  301-redirects them (both sites; `test_web.py` checks every destination exists).
  English edition (since 11/10/2026): every address also exists under `/en` (`/en`,
  `/en/standings`, ...), with its own `data-en.js` (`D.lang = 'en'`, `D.routes.prefix = 'en'`).
  Slugs live only in `render.PAGE_SLUGS` /
  `TAB_SLUGS` and reach the JS through `data.js` (`D.routes`). JS builds links
  with `url(page, tab)` / `teamHref(team, tab)` and navigates with `go(path)`;
  never hardcode an address. Old `#/...` links are redirected on load.
- `render.site_pages()` gives every address its own Greek `<title>` and
  description (the SEO text lives there). `render_site()` writes a ~4 KB HTML file
  per address (`standings.html`, `teams/paok.html`; Firebase `cleanUrls` +
  `trailingSlash: false` serves them at `/standings`), plus `404.html`
  (noindex) and the shared `app.css`, `app.js`, `data.js`. The sitemap lists
  every address. A new page or tab needs a slug and a `site_pages()` entry.
- The pages link the shared files by absolute path, so they need a server:
  Firebase, or `scripts/serve.py` locally (no file:// opening).
- SEO in each page's HTML (render.py): the main menu as plain links
  (`NAV_PAGES`, also used by the JS), schema.org JSON-LD (WebSite + Organization
  on home, BreadcrumbList elsewhere, from `TAB_LABELS`), and an invisible `.ssr`
  heading + description in `<main>` for crawlers without JS (the JS replaces it).
- Phones (≤ 720 px): the top menu row is replaced by a bottom tab bar (Αρχική,
  Προβλέψεις, Βαθμολογία, Ομάδες, Μενού → sheet with every page), 90-app.js.
  Tables: column options `sticky` (stays put when scrolling sideways), `hideSm`,
  and `area`/`cap` + `opts.cards` ('results' | 'log') turn rows into cards
  (≤ 640 px), see `table()` in 03-components.js. Check phone changes at 390 and
  360 px with CDP mobile emulation; nothing may overflow sideways.
- DOM via `h()` / `s()` (text nodes only, never innerHTML with data). The CSP
  allows scripts only from our own files (`script-src 'self'`): no inline
  scripts or handlers, no eval, no external scripts. Images: our own files
  (crests, icons) or data URIs. Network: same origin + Firestore only.
- Site-mode flags in `01-core.js`: `SITE`, `PUBLIC`, `SERVED`. Anything that needs
  the local server must check `SERVED`; public-only text checks `PUBLIC`.
- Every visible string is written in both languages at the call: `T('Βαθμολογία', 'Standings')`
  (JS, 01-core) / `t(...)` in `render_page`. No word-by-word dictionaries. Team names on the page
  go through `tn(team)` (English names: `config.TEAM_NAMES_EN`, chosen by Claude with the user's
  OK, 11/10/2026); data and addresses keep the canonical names. English titles/descriptions for
  search: `render.english_pages()`. The EN / ΕΛ link (`hreflang`) reloads the page (the router
  skips it); on phones it sits in the Menu sheet. Live pages carry hreflang alternates and the
  sitemap lists both languages. The desktop-only manual in `18-help.js` stays Greek.
- Every metric shown gets an entry in `02-metrics.js` (ⓘ tooltip + guide card).
- Every section gets a `sectionHead(title, plain-Greek explanation)`; the user asked
  for explanatory headings. The footer carries only the user-approved disclaimer
  (maths and algorithms, «σε καμία περίπτωση» betting advice): no data credits or timestamps there. Score boxes are labelled «Αποτέλεσμα» / «Πρόβλεψη».
- `autoScroll(strip)` (01-core) = endless self-scrolling strip with mouse drag,
  pause on hover/focus/off-screen, none under reduced motion (home ticker).
- Chart colours (`--accent`/`--neg` per theme in app.css) were validated with
  the dataviz palette checker. Re-validate if you change them or the surfaces.
- "Hit" = favourite probability >= 0.8 and correct (gold). "Sharp" = correct
  and margin within 3 points (🎯). Constants live in `01-core.js`.
- `tests/test_web.py` runs `node --check` on the bundle and checks the CSP, the
  addresses (unique, titled, same slug rule in Python and JS), the local server's
  clean addresses, site modes and rules/form consistency.
- Check visual changes with a headless Edge screenshot before calling them done.
- `build.write_site_files` copies the crests, icons (favicon.svg / .ico,
  apple-touch-icon.png) and share card `assets/og-card.jpg` (1200x630, static) next
  to the pages and writes robots.txt + sitemap.xml. Open Graph tags in
  `render.share_meta` point at `SITE_URL`. Canonical = `SITE_URL` + the page's
  address (live only).
  Search Console uses a DNS TXT record at papaki (Domain property).
- Crests: official league images (esake.gr) in `assets/crests`, fitted inside
  the round frame (`.crest` has `border-radius:50%` and a white disc in dark
  mode), served as files (`/crests/<slug>.webp`). `crop=sponsor` strips a sponsor logo below the crest; `crop=none`
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
  (papaki.gr DNS: A 199.36.158.100, TXT hosting-site=gbl-predictor, CNAME www →
  gbl-predictor.web.app.; Firebase redirects www → apex) live since 06/10/2026.
  Search Console: verified (Domain property, TXT google-site-verification at
  papaki); sitemap submitted as the full URL https://tipoff.gr/sitemap.xml.

## Ideas backlog (agreed with the user, not started)

Offer these when the user asks "what next". Ask before starting any of them.
- User's notes (07/10/2026): «Απόκλιση» (= |predicted − actual margin|) confuses,
  because it ignores each team's points. Rename it (e.g. «Λάθος διαφοράς») or keep only 🎯.
  Also show the total-points error («Σύνολο: 169 αντί 194»): the total isn't graded anywhere.
  The pick labels (πριν τον αγώνα / αναδρομική / walk-forward) need clearer wording.
- AI (Claude API, key as a GitHub secret): match previews in Greek, per-team
  news summary, injury hints from news (user approves before they count),
  weekly report. A live "ask the model" chat needs a server (Blaze plan: ask).
- Model: Monte Carlo season simulation
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

- Only one full season of data: the carry-over and promoted-start values rest on
  few season-start games (round 1 2026/27); revisit after a few rounds.
- No box-score features (pace, eFG%, ratings): FlashScore doesn't expose them.
- No live injury feed: absences are user-entered.
- The contact form has a honeypot but no App Check / rate limit yet.

## When in doubt

- Ask before editing user-curated data, adding features or new modules, or
  anything that costs money or publishes something.
- Don't ask before running tests, ruff, retraining or a local `--no-sync --no-log` build.
