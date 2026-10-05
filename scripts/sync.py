"""One-command sync: fetch results AND upcoming fixtures from FlashScore.

Usage:
    # Dry-run (default) — shows what it WOULD write, makes no changes:
    python scripts/sync.py

    # Actually commit the changes to disk:
    python scripts/sync.py --commit

The actual sync logic lives in ``src/sync.py``. This script is just a thin
CLI wrapper so the same engine can be called from the notebook (see
``src.sync.sync_for_notebook``).

Design choices (unchanged from the original implementation):

  * Safe by default — mutations require ``--commit``, like Terraform plan/apply.
  * Single run = full reconciliation. No partial states.
  * upcoming_fixtures.csv is overwritten wholesale (not merged) — the API
    snapshot is authoritative.
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
from src.sync import run_sync  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to all_fixtures.csv and upcoming_fixtures.csv (default is dry-run).",
    )
    args = parser.parse_args()

    # Read BEFORE syncing — a --commit run overwrites the file.
    current_upcoming = pd.DataFrame()
    if cfg.UPCOMING_FIXTURES_CSV.exists():
        current_upcoming = pd.read_csv(cfg.UPCOMING_FIXTURES_CSV)

    result = run_sync(commit=args.commit, verbose=True)

    # --- report ---------------------------------------------------------
    if result.unmapped_team_names:
        print("\nUnmapped team names — add these to team_name_mapping.csv and re-run:")
        for name in sorted(result.unmapped_team_names):
            print(f"  {name},<canonical name>")

    if result.new_result_rows:
        print("\nResults to add:")
        for r in result.new_result_rows:
            print(
                f"  {r[cfg.COL_DATE]}  {r[cfg.COL_HOME]} {r[cfg.COL_HOME_SCORE]} "
                f"- {r[cfg.COL_AWAY_SCORE]} {r[cfg.COL_AWAY]}"
            )

    if result.corrected_result_rows:
        print("\nOvertime scores to correct (stored as regulation-time ties):")
        for r in result.corrected_result_rows:
            print(
                f"  {r[cfg.COL_DATE]}  {r[cfg.COL_HOME]} {r[cfg.COL_HOME_SCORE]} "
                f"- {r[cfg.COL_AWAY_SCORE]} {r[cfg.COL_AWAY]}"
            )

    if result.unresolved_ties:
        print("\nTied games skipped (final score unavailable; retried next sync):")
        for label in result.unresolved_ties:
            print(f"  {label}")

    print(
        f"\nUpcoming fixtures: {len(current_upcoming)} currently -> "
        f"{len(result.upcoming_rows)} after sync"
    )

    if not result.ok:
        print(f"\nERROR: {result.error}")
        sys.exit(1)

    if not result.committed:
        print("\nDry-run. Re-run with --commit to write changes.")
        return

    if result.new_result_rows:
        print(f"\nWrote {len(result.new_result_rows)} new result(s) to {cfg.RAW_GAMES_CSV.name}.")
    if result.corrected_result_rows:
        print(f"Corrected {len(result.corrected_result_rows)} overtime score(s).")
    print(
        f"Replaced {cfg.UPCOMING_FIXTURES_CSV.name} with "
        f"{len(result.upcoming_rows)} upcoming fixture(s)."
    )


if __name__ == "__main__":
    main()
