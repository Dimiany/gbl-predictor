"""One-command sync: fetch results AND upcoming fixtures from FlashScore.

Usage:
    # Dry-run (default) — shows what it WOULD write, makes no changes:
    python scripts/sync.py

    # Actually commit the changes to disk:
    python scripts/sync.py --commit

What it does, step by step:

  1. FETCH RESULTS  — calls /tournaments/results, paginates, dedups against
     all_fixtures.csv, appends new games.
  2. FETCH FIXTURES — calls /tournaments/fixtures, paginates, filters out
     games already in all_fixtures.csv (they've been played), writes the
     rest to upcoming_fixtures.csv (REPLACING the file — the API is the
     source of truth, any stale rows get dropped).
  3. REPORT         — prints a summary: added, removed, unchanged.

Design choices:

  * Safe by default — mutations require ``--commit``, like Terraform plan/apply.
  * Single run = full reconciliation. No partial states. No "forgot to run the
    other script".
  * upcoming_fixtures.csv is overwritten wholesale (not merged). This is
    correct because the API is authoritative — any row we'd preserve that
    isn't in the API snapshot is data-rot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402
from src.api_client import (  # noqa: E402
    APIClientError,
    FlashScoreClient,
    RawFixture,
    RawGame,
)
from src.team_name_mapping import canonicalize, load_mapping  # noqa: E402

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _assert_ready() -> None:
    """Verify env vars are set. Fail with a helpful message if not."""
    missing = []
    if not cfg.RAPIDAPI_KEY:
        missing.append("RAPIDAPI_KEY")
    if not cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID:
        missing.append("FLASHSCORE_TOURNAMENT_TEMPLATE_ID")
    if not cfg.FLASHSCORE_SEASON_ID:
        missing.append("FLASHSCORE_SEASON_ID")
    if missing:
        print(
            "ERROR: the following environment variables are not set:\n  "
            + "\n  ".join(missing)
            + "\n\nFix: copy .env.example to .env and fill in the values."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Small helper: API name -> canonical name, or None
# ---------------------------------------------------------------------------


def _translate_teams(
    home_api: str,
    away_api: str,
    mapping: dict[str, str],
    unmapped: set[str],
) -> tuple[str | None, str | None]:
    """Translate a pair of API names to canonical; record any that don't map."""
    home = canonicalize(home_api, mapping)
    away = canonicalize(away_api, mapping)
    if home is None:
        unmapped.add(home_api)
    if away is None:
        unmapped.add(away_api)
    return home, away


# ---------------------------------------------------------------------------
# Step 1: RESULTS — append new completed games to all_fixtures.csv
# ---------------------------------------------------------------------------


def _sync_results(
    games: list[RawGame],
    mapping: dict[str, str],
    unmapped: set[str],
) -> tuple[list[dict], pd.DataFrame]:
    """Compute the new result rows and return them + the live history DataFrame.

    We read-modify-potentially-write, returning the rows to append. The caller
    decides whether to actually write (controlled by --commit).
    """
    history = pd.read_csv(cfg.RAW_GAMES_CSV)

    # Translate and shape the API rows to our CSV schema.
    candidate_rows: list[dict] = []
    for g in games:
        home, away = _translate_teams(g.home_team_api_name, g.away_team_api_name, mapping, unmapped)
        if home is None or away is None:
            continue
        our_date = pd.Timestamp(g.date).strftime("%d/%m/%Y")
        candidate_rows.append(
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

    # Dedup: only keep rows not already in history.
    if history.empty:
        return candidate_rows, history
    history_dates = pd.to_datetime(history[cfg.COL_DATE], dayfirst=True)
    new_rows = []
    for row in candidate_rows:
        row_date = pd.to_datetime(row[cfg.COL_DATE], dayfirst=True)
        exists = (
            (history_dates == row_date)
            & (history[cfg.COL_HOME] == row[cfg.COL_HOME])
            & (history[cfg.COL_AWAY] == row[cfg.COL_AWAY])
        ).any()
        if not exists:
            new_rows.append(row)
    return new_rows, history


# ---------------------------------------------------------------------------
# Step 2: FIXTURES — replace upcoming_fixtures.csv with the API snapshot
# ---------------------------------------------------------------------------


def _sync_fixtures(
    fixtures: list[RawFixture],
    mapping: dict[str, str],
    unmapped: set[str],
    full_history: pd.DataFrame,  # may include rows we just appended
) -> list[dict]:
    """Build the rows that will REPLACE upcoming_fixtures.csv.

    We drop any fixture that corresponds to a game already in history —
    that's a played game the API still happens to list as a fixture (rare,
    but worth guarding against).
    """
    # Build the (date, home, away) set of already-played games, using
    # canonical team names so the comparison is apples-to-apples.
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
            # Already played — don't list as upcoming.
            continue
        rows.append(
            {
                "fixture_date": fx_date.strftime("%d/%m/%Y"),
                # Kickoff time in Athens local (HH:MM 24h). Already parsed by
                # the API client; we just carry it through to the CSV.
                "fixture_time": f.time,
                # FlashScore doesn't surface matchday/round info in this response.
                # Leave blank; the user can fill in by hand if they care about it.
                "matchday": "",
                "home_team": home,
                "away_team": away,
            }
        )
    # Sort chronologically (by date then time) for a stable, readable CSV.
    rows.sort(
        key=lambda r: (
            pd.to_datetime(r["fixture_date"], dayfirst=True),
            r["fixture_time"],
        )
    )
    return rows


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to all_fixtures.csv and upcoming_fixtures.csv (default is dry-run).",
    )
    args = parser.parse_args()

    _assert_ready()

    client = FlashScoreClient(
        api_key=cfg.RAPIDAPI_KEY,
        base_url=cfg.FLASHSCORE_BASE_URL,
        host=cfg.FLASHSCORE_HOST,
    )
    mapping = load_mapping()
    unmapped: set[str] = set()

    # --- step 1: results -------------------------------------------------
    print("STEP 1 - Fetching completed results...")
    try:
        results = client.fetch_all_results(
            cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID,
            cfg.FLASHSCORE_SEASON_ID,
        )
    except APIClientError as exc:
        print(f"ERROR talking to the API (/results): {exc}")
        sys.exit(1)
    print(f"  API returned {len(results)} finished game(s)")
    new_result_rows, history = _sync_results(results, mapping, unmapped)
    print(f"  New rows to append: {len(new_result_rows)}")

    # --- step 2: fixtures -----------------------------------------------
    # Use a 'full history' that already includes the rows we plan to
    # append — that way an upcoming fixture that just became a result
    # (same API call window) is correctly classified as played.
    tentative_full_history = history
    if new_result_rows:
        tentative_full_history = pd.concat(
            [history, pd.DataFrame(new_result_rows)],
            ignore_index=True,
        )

    print("\nSTEP 2 - Fetching upcoming fixtures...")
    try:
        fixtures = client.fetch_all_fixtures(
            cfg.FLASHSCORE_TOURNAMENT_TEMPLATE_ID,
            cfg.FLASHSCORE_SEASON_ID,
        )
    except APIClientError as exc:
        print(f"ERROR talking to the API (/fixtures): {exc}")
        sys.exit(1)
    print(f"  API returned {len(fixtures)} upcoming fixture(s)")
    new_upcoming_rows = _sync_fixtures(fixtures, mapping, unmapped, tentative_full_history)
    print(f"  Upcoming rows (after filtering played): {len(new_upcoming_rows)}")

    # --- report ---------------------------------------------------------
    if unmapped:
        print("\nUnmapped team names — add these to team_name_mapping.csv and re-run:")
        for name in sorted(unmapped):
            print(f"  {name},<canonical name>")

    if new_result_rows:
        print("\nResults to add:")
        for r in new_result_rows:
            print(
                f"  {r[cfg.COL_DATE]}  {r[cfg.COL_HOME]} {r[cfg.COL_HOME_SCORE]} "
                f"- {r[cfg.COL_AWAY_SCORE]} {r[cfg.COL_AWAY]}"
            )

    # Compare the new upcoming snapshot to the current file for change display.
    current_upcoming = pd.DataFrame()
    if cfg.UPCOMING_FIXTURES_CSV.exists():
        current_upcoming = pd.read_csv(cfg.UPCOMING_FIXTURES_CSV)
    current_count = len(current_upcoming)
    print(f"\nUpcoming fixtures: {current_count} currently -> {len(new_upcoming_rows)} after sync")

    if not args.commit:
        print("\nDry-run. Re-run with --commit to write changes.")
        return

    # --- write ----------------------------------------------------------
    if new_result_rows:
        updated_history = pd.concat(
            [history, pd.DataFrame(new_result_rows)],
            ignore_index=True,
        )
        updated_history.to_csv(cfg.RAW_GAMES_CSV, index=False)
        print(
            f"\nWrote {len(new_result_rows)} new result(s) to "
            f"{cfg.RAW_GAMES_CSV.name}. Total: {len(updated_history)} games."
        )

    # Always overwrite upcoming_fixtures.csv — the API snapshot is authoritative.
    pd.DataFrame(
        new_upcoming_rows,
        columns=["fixture_date", "fixture_time", "matchday", "home_team", "away_team"],
    ).to_csv(cfg.UPCOMING_FIXTURES_CSV, index=False)
    print(
        f"Replaced {cfg.UPCOMING_FIXTURES_CSV.name} with "
        f"{len(new_upcoming_rows)} upcoming fixture(s)."
    )


if __name__ == "__main__":
    main()
