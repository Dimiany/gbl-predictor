# AGENTS.md

The full project guide is **[CLAUDE.md](CLAUDE.md)**. Read it before any change: it
covers the user, the cloud setup, the model, the website conventions and the rules
(tests, ruff, secrets, user-curated data). It applies to every coding agent, not only Claude.

The essentials:

- The user is Greek-speaking and never uses the terminal. Reply in Greek, in plain words.
- Work on a branch and open a PR. The PR is published to the test site
  https://gbl-predictor-test.web.app; merging to `main` deploys the live site tipoff.gr.
  Merge only when the user says so («ανέβασέ το», «κάν' το live»).
- Before you finish: `python -m pytest tests/`, `ruff check .` and `ruff format --check .` must pass.
- Never print or commit secrets (`.env`, the Firebase service account).
- GitHub Actions owns data sync and prediction logging. Never hand-edit the CSVs the bot writes.
