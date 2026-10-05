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

from dataclasses import dataclass, field, replace

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
    # Existing history rows stored as regulation-time ties that the API's
    # /matches/details now resolves to a real (overtime) result.
    corrected_result_rows: list[dict] = field(default_factory=list)
    # Tied games we couldn't resolve this run — left out so a fake tie is
    # never written. The next sync retries them.
    unresolved_ties: list[str] = field(default_factory=list)
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
        if self.corrected_result_rows:
            head += f"; {len(self.corrected_result_rows)} overtime score(s) corrected"
        if self.unresolved_ties:
            head += f"; {len(self.unresolved_ties)} tied game(s) skipped (retry next sync)"
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


def _history_keys(history: pd.DataFrame, *, tied: bool) -> set[tuple]:
    """Keys of history rows whose stored score is (``tied``) or isn't a tie."""
    if history.empty:
        return set()
    is_tie = history[cfg.COL_HOME_SCORE] == history[cfg.COL_AWAY_SCORE]
    rows = history[is_tie if tied else ~is_tie]
    dates = pd.to_datetime(rows[cfg.COL_DATE], dayfirst=True)
    return set(zip(dates, rows[cfg.COL_HOME], rows[cfg.COL_AWAY], strict=True))


def _resolve_overtime(
    games: list[RawGame],
    history: pd.DataFrame,
    mapping: dict[str, str],
    client: FlashScoreClient,
) -> tuple[list[RawGame], list[str]]:
    """Replace regulation-time ties with the final score from /matches/details.

    Basketball has no ties — a tied /results score means the game went to
    overtime. We only spend a details request on ties that history doesn't
    already hold a real score for, so a normal sync costs 0-2 extra calls.

    Returns (games, unresolved): ties we couldn't resolve are dropped from
    ``games`` rather than written as a fake tie.
    """
    settled = _history_keys(history, tied=False)
    resolved: list[RawGame] = []
    unresolved: list[str] = []
    for g in games:
        if g.home_score != g.away_score:
            resolved.append(g)
            continue
        home = canonicalize(g.home_team_api_name, mapping)
        away = canonicalize(g.away_team_api_name, mapping)
        # g.date is ISO (YYYY-MM-DD) — parse WITHOUT dayfirst, which would
        # swap day and month on ISO strings.
        if (pd.Timestamp(g.date), home, away) in settled:
            resolved.append(g)  # history already has the real score
            continue
        try:
            final = client.fetch_final_score(g.match_id) if g.match_id else None
        except APIClientError:
            final = None
        if final is None or final[0] == final[1]:
            unresolved.append(f"{g.date} {g.home_team_api_name} - {g.away_team_api_name}")
            continue
        resolved.append(replace(g, home_score=final[0], away_score=final[1]))
    return resolved, unresolved


def _game_rows(
    games: list[RawGame],
    mapping: dict[str, str],
    unmapped: set[str],
) -> list[dict]:
    """Translate API games to our all_fixtures.csv schema."""
    rows: list[dict] = []
    for g in games:
        home, away = _translate_teams(g.home_team_api_name, g.away_team_api_name, mapping, unmapped)
        if home is None or away is None:
            continue
        rows.append(
            {
                cfg.COL_DATE: pd.Timestamp(g.date).strftime("%d/%m/%Y"),
                cfg.COL_HOME: home,
                cfg.COL_AWAY: away,
                cfg.COL_HOME_SCORE: g.home_score,
                cfg.COL_AWAY_SCORE: g.away_score,
                "score_diff": g.home_score - g.away_score,
                cfg.COL_TOTAL: g.home_score + g.away_score,
                cfg.COL_HOME_WIN: int(g.home_score > g.away_score),
            }
        )
    return rows


def _build_tie_corrections(candidates: list[dict], history: pd.DataFrame) -> list[dict]:
    """API rows (already overtime-resolved) whose history row is still a tie."""
    tied_keys = _history_keys(history, tied=True)
    corrections: list[dict] = []
    seen: set[tuple] = set()
    for row in candidates:
        if row["score_diff"] == 0:
            continue
        row_date = pd.to_datetime(row[cfg.COL_DATE], dayfirst=True)
        key = (row_date, row[cfg.COL_HOME], row[cfg.COL_AWAY])
        if key in tied_keys and key not in seen:
            seen.add(key)
            corrections.append(row)
    return corrections


def _apply_corrections(history: pd.DataFrame, corrections: list[dict]) -> pd.DataFrame:
    """Overwrite the score columns of every history row matching a correction."""
    history = history.copy()
    dates = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    score_cols = [
        cfg.COL_HOME_SCORE,
        cfg.COL_AWAY_SCORE,
        "score_diff",
        cfg.COL_TOTAL,
        cfg.COL_HOME_WIN,
    ]
    for row in corrections:
        mask = (
            (dates == pd.to_datetime(row[cfg.COL_DATE], dayfirst=True))
            & (history[cfg.COL_HOME] == row[cfg.COL_HOME])
            & (history[cfg.COL_AWAY] == row[cfg.COL_AWAY])
        )
        history.loc[mask, score_cols] = [row[c] for c in score_cols]
    return history


def _build_result_rows(
    games: list[RawGame],
    history: pd.DataFrame,
    mapping: dict[str, str],
    unmapped: set[str],
) -> list[dict]:
    """Translate API games to our schema and return only rows new to history.

    The API occasionally lists the same game twice, so duplicates within the
    response are dropped too — not just games already in history.
    """
    candidates = _game_rows(games, mapping, unmapped)

    known: set[tuple] = set()
    if not history.empty:
        history_dates = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
        known = set(zip(history_dates, history[cfg.COL_HOME], history[cfg.COL_AWAY], strict=True))

    new_rows = []
    for row in candidates:
        key = (
            pd.to_datetime(row[cfg.COL_DATE], dayfirst=True),
            row[cfg.COL_HOME],
            row[cfg.COL_AWAY],
        )
        if key not in known:
            known.add(key)
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
        played_keys.add((fx_date, home, away))  # also skips API-side duplicates
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
            error=("missing env vars: " + ", ".join(missing) + " (copy .env.example to .env)")
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
    results, unresolved_ties = _resolve_overtime(results, history, mapping, client)
    new_result_rows = _build_result_rows(results, history, mapping, unmapped)
    corrected_rows = _build_tie_corrections(_game_rows(results, mapping, set()), history)
    if verbose:
        print(f"  New rows to append: {len(new_result_rows)}")
        print(f"  Overtime scores to correct: {len(corrected_rows)}")
        if unresolved_ties:
            print(f"  Unresolved tied games (skipped, retried next sync): {len(unresolved_ties)}")

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
            corrected_result_rows=corrected_rows,
            unresolved_ties=unresolved_ties,
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
        corrected_result_rows=corrected_rows,
        unresolved_ties=unresolved_ties,
        upcoming_rows=upcoming_rows,
        unmapped_team_names=unmapped,
    )

    if not commit:
        return result

    # Write to disk. We treat the two files separately: only rewrite history
    # if there's something new, but ALWAYS overwrite upcoming_fixtures.csv
    # because the API snapshot is authoritative.
    if new_result_rows or corrected_rows:
        updated_history = pd.concat(
            [_apply_corrections(history, corrected_rows), pd.DataFrame(new_result_rows)],
            ignore_index=True,
        )
        # Sort chronologically (oldest first, newest at the bottom) so the file
        # reads naturally and new rows always appear at the end. dayfirst=True
        # is required because dates are dd/mm/yyyy (CLAUDE.md rule #4).
        updated_history = updated_history.assign(
            _sort_key=pd.to_datetime(updated_history[cfg.COL_DATE], dayfirst=True)
        )
        # One row per game: rows written before API-side duplicates were
        # filtered can appear twice, double-counting that game in Elo and W-L.
        updated_history = (
            updated_history.sort_values("_sort_key", kind="stable")
            .drop_duplicates(subset=["_sort_key", cfg.COL_HOME, cfg.COL_AWAY], keep="first")
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
