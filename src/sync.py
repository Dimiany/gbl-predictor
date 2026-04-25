"""Reusable sync engine — fetch results & upcoming fixtures from FlashScore.

The CLI wrapper at ``scripts/sync.py`` and the notebook wrapper
``sync_for_notebook()`` both call ``run_sync()`` here. Keeping the orchestration
in one place means: one set of behaviors, one set of edge-case handling, one
place to fix bugs.

Two entry points:
  * ``run_sync(commit, verbose)`` — returns a ``SyncResult``; never calls sys.exit.
    Suitable for any caller (CLI, notebook, tests).
  * ``sync_for_notebook()``       — extra-friendly wrapper that swallows ALL
    exceptions and returns a one-line status string. Designed for the very
    first cell of the notebook: failure here must not block the rest of the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src import config as cfg
from src.api_client import APIClientError, FlashScoreClient, RawFixture, RawGame
from src.team_name_mapping import canonicalize, load_mapping


@dataclass
class SyncResult:
    """Structured outcome of a sync run.

    ``error`` being non-None means the run did NOT complete normally; all
    other counts will reflect whatever was done before the failure.
    """

    new_result_rows: list[dict] = field(default_factory=list)
    upcoming_rows: list[dict] = field(default_factory=list)
    unmapped_team_names: set[str] = field(default_factory=set)
    committed: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def summary_line(self) -> str:
        """One-line human-readable summary suitable for notebook display."""
        if not self.ok:
            return f"Sync: skipped — {self.error}"
        n_new = len(self.new_result_rows)
        n_up = len(self.upcoming_rows)
        if n_new == 0:
            head = "Sync: no new results"
        else:
            most_recent_date = max(r[cfg.COL_DATE] for r in self.new_result_rows)
            head = f"Sync: {n_new} new result(s) added (most recent {most_recent_date})"
        return f"{head}; {n_up} upcoming fixture(s) on file."


def _missing_env_vars() -> list[str]:
    missing = []
    if not cfg.RAPIDAPI_KEY:
        missing.append("RAPIDAPI_KEY")
    if not cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID:
        missing.append("FLASHSCORE_TOURNAMENT_TEMPLATE_ID")
    if not cfg.FLASHSCORE_SEASON_ID:
        missing.append("FLASHSCORE_SEASON_ID")
    return missing


def _translate_teams(
    home_api: str,
    away_api: str,
    mapping: dict[str, str],
    unmapped: set[str],
) -> tuple[str | None, str | None]:
    home = canonicalize(home_api, mapping)
    away = canonicalize(away_api, mapping)
    if home is None:
        unmapped.add(home_api)
    if away is None:
        unmapped.add(away_api)
    return home, away


def _build_result_rows(
    games: list[RawGame],
    history: pd.DataFrame,
    mapping: dict[str, str],
    unmapped: set[str],
) -> list[dict]:
    """Translate API games to our schema and return only rows new to history."""
    candidates: list[dict] = []
    for g in games:
        home, away = _translate_teams(g.home_team_api_name, g.away_team_api_name, mapping, unmapped)
        if home is None or away is None:
            continue
        our_date = pd.Timestamp(g.date).strftime("%d/%m/%Y")
        candidates.append(
            {
                cfg.COL_DATE: our_date,
                cfg.COL_HOME: home,
                cfg.COL_AWAY: away,
                cfg.COL_HOME_SCORE: g.home_score,
                cfg.COL_AWAY_SCORE: g.away_score,
                "score_diff": g.home_score - g.away_score,
                cfg.COL_TOTAL: g.home_score + g.away_score,
                cfg.COL_HOME_WIN: int(g.home_score > g.away_score),
            }
        )

    if history.empty:
        return candidates

    history_dates = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    new_rows = []
    for row in candidates:
        row_date = pd.to_datetime(row[cfg.COL_DATE], dayfirst=True)
        exists = (
            (history_dates == row_date)
            & (history[cfg.COL_HOME] == row[cfg.COL_HOME])
            & (history[cfg.COL_AWAY] == row[cfg.COL_AWAY])
        ).any()
        if not exists:
            new_rows.append(row)
    return new_rows


def _build_upcoming_rows(
    fixtures: list[RawFixture],
    full_history: pd.DataFrame,
    mapping: dict[str, str],
    unmapped: set[str],
) -> list[dict]:
    """Build the rows that REPLACE upcoming_fixtures.csv, dropping already-played games."""
    played_keys: set[tuple[pd.Timestamp, str, str]] = set()
    if not full_history.empty:
        hist_dates = pd.to_datetime(full_history[cfg.COL_DATE], dayfirst=True)
        for date, home, away in zip(
            hist_dates,
            full_history[cfg.COL_HOME],
            full_history[cfg.COL_AWAY],
            strict=True,
        ):
            played_keys.add((date, home, away))

    rows: list[dict] = []
    for f in fixtures:
        home, away = _translate_teams(f.home_team_api_name, f.away_team_api_name, mapping, unmapped)
        if home is None or away is None:
            continue
        fx_date = pd.Timestamp(f.date)
        if (fx_date, home, away) in played_keys:
            continue
        rows.append(
            {
                "fixture_date": fx_date.strftime("%d/%m/%Y"),
                "fixture_time": f.time,
                "matchday": "",
                "home_team": home,
                "away_team": away,
            }
        )
    rows.sort(
        key=lambda r: (
            pd.to_datetime(r["fixture_date"], dayfirst=True),
            r["fixture_time"],
        )
    )
    return rows


def run_sync(commit: bool = False, verbose: bool = False) -> SyncResult:
    """Pull results + upcoming fixtures, optionally writing them to disk.

    Never calls sys.exit. Returns a ``SyncResult``; ``result.ok`` is False if
    anything went wrong (missing env vars, API failure, etc.). Callers decide
    how to surface that — the CLI prints + exits non-zero, the notebook
    wrapper just shows the message.
    """
    missing = _missing_env_vars()
    if missing:
        return SyncResult(
            error=(
                "missing env vars: " + ", ".join(missing) + " (copy .env.example to .env)"
            )
        )

    client = FlashScoreClient(
        api_key=cfg.RAPIDAPI_KEY,
        base_url=cfg.FLASHSCORE_BASE_URL,
        host=cfg.FLASHSCORE_HOST,
    )
    mapping = load_mapping()
    unmapped: set[str] = set()

    if verbose:
        print("STEP 1 - Fetching completed results...")
    try:
        results = client.fetch_all_results(
            cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID,
            cfg.FLASHSCORE_SEASON_ID,
        )
    except APIClientError as exc:
        return SyncResult(error=f"API error fetching results: {exc}")
    if verbose:
        print(f"  API returned {len(results)} finished game(s)")

    history = pd.read_csv(cfg.RAW_GAMES_CSV)
    new_result_rows = _build_result_rows(results, history, mapping, unmapped)
    if verbose:
        print(f"  New rows to append: {len(new_result_rows)}")

    tentative_full_history = history
    if new_result_rows:
        tentative_full_history = pd.concat(
            [history, pd.DataFrame(new_result_rows)], ignore_index=True
        )

    if verbose:
        print("\nSTEP 2 - Fetching upcoming fixtures...")
    try:
        fixtures = client.fetch_all_fixtures(
            cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID,
            cfg.FLASHSCORE_SEASON_ID,
        )
    except APIClientError as exc:
        # Partial result — we did fetch results but couldn't get fixtures.
        # Still return what we got; caller can decide what to do.
        return SyncResult(
            new_result_rows=new_result_rows,
            unmapped_team_names=unmapped,
            error=f"API error fetching fixtures: {exc}",
        )
    if verbose:
        print(f"  API returned {len(fixtures)} upcoming fixture(s)")

    upcoming_rows = _build_upcoming_rows(fixtures, tentative_full_history, mapping, unmapped)
    if verbose:
        print(f"  Upcoming rows (after filtering played): {len(upcoming_rows)}")

    result = SyncResult(
        new_result_rows=new_result_rows,
        upcoming_rows=upcoming_rows,
        unmapped_team_names=unmapped,
    )

    if not commit:
        return result

    # Write to disk. We treat the two files separately: only rewrite history
    # if there's something new, but ALWAYS overwrite upcoming_fixtures.csv
    # because the API snapshot is authoritative.
    if new_result_rows:
        updated_history = pd.concat(
            [history, pd.DataFrame(new_result_rows)],
            ignore_index=True,
        )
        # Sort chronologically (oldest first, newest at the bottom) so the file
        # reads naturally and new rows always appear at the end. dayfirst=True
        # is required because dates are dd/mm/yyyy (CLAUDE.md rule #4).
        updated_history = updated_history.assign(
            _sort_key=pd.to_datetime(updated_history[cfg.COL_DATE], dayfirst=True)
        )
        updated_history = (
            updated_history.sort_values("_sort_key", kind="stable")
            .drop(columns=["_sort_key"])
            .reset_index(drop=True)
        )
        updated_history.to_csv(cfg.RAW_GAMES_CSV, index=False)

    pd.DataFrame(
        upcoming_rows,
        columns=["fixture_date", "fixture_time", "matchday", "home_team", "away_team"],
    ).to_csv(cfg.UPCOMING_FIXTURES_CSV, index=False)

    result.committed = True
    return result


def sync_for_notebook() -> str:
    """Notebook-safe sync: never raises, always returns a status line.

    Designed for the first cell of ``predictor.ipynb`` so a transient API
    blip can never block the rest of the workflow. If the sync fails, you
    still get to train and predict on whatever data is already on disk.
    """
    try:
        result = run_sync(commit=True, verbose=False)
    except Exception as exc:  # noqa: BLE001 - notebook UX takes precedence over typed exceptions
        return f"Sync: skipped — unexpected error: {exc}"
    return result.summary_line()
