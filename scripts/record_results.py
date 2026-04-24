"""Interactive helper for recording completed-game results.

Run with:  python scripts/record_results.py

For each fixture in ``data/raw/upcoming_fixtures.csv``, this script prompts
you for the final score, appends a row to ``data/raw/all_fixtures.csv``
(the history file), and removes the fixture from the upcoming list. At the
end it offers to retrain the model.

Design choices (all on purpose):

* Prompt ONE fixture at a time. Much harder to accidentally swap two
  teams' scores than when typing a batch in one go.
* Validate inputs: scores must be non-negative integers; ties rejected
  (no ties in basketball).
* Write atomically: we build the new CSVs in memory first, then write in
  one shot. If you Ctrl+C midway, nothing is corrupted.
* Offer to retrain at the end. Skipping retrain is fine if you're going
  to record more results later — the model only needs the CSV to be
  up to date when you DO retrain.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Make `src` importable when this script is launched directly (cwd may be
# the project root OR the scripts/ directory — handle both).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402

# ---------------------------------------------------------------------------
# Small input helpers (all the prompt logic lives here so `main()` stays short)
# ---------------------------------------------------------------------------


def _prompt_int(message: str) -> int:
    """Prompt until the user types a non-negative integer."""
    while True:
        raw = input(message).strip()
        # Basketball scores can realistically reach ~130 but never be negative.
        # isdigit() covers the "must be a non-negative integer" case in one call.
        if raw.isdigit():
            return int(raw)
        print("  Please enter a whole number (no decimals, no negatives).")


def _prompt_choice(message: str, choices: tuple[str, ...], default: str) -> str:
    """Prompt for one of a limited set of answers. Returns lowercase match."""
    # Inline the choices in the prompt, capitalizing the default so the user
    # can see it at a glance — e.g. "[Y/n/skip]".
    rendered = "/".join(c.upper() if c == default else c for c in choices)
    while True:
        raw = input(f"{message} [{rendered}]: ").strip().lower()
        if raw == "":
            return default
        if raw in choices:
            return raw
        # Accept short unique prefixes too: typing "y" for "yes", "sk" for "skip".
        matches = [c for c in choices if c.startswith(raw)]
        if len(matches) == 1:
            return matches[0]
        print(f"  Please answer one of: {', '.join(choices)}.")


# ---------------------------------------------------------------------------
# The per-fixture interaction
# ---------------------------------------------------------------------------


def _record_one_fixture(fx: pd.Series) -> tuple[str, dict | None]:
    """Ask about a single fixture. Returns (action, row_to_append).

    action is one of:
      * "recorded" — user entered a score; row_to_append is the history row
      * "cancelled" — game didn't happen; remove from upcoming, no history row
      * "skipped"   — leave it in upcoming_fixtures for next run
    """
    print(f"\n{fx['fixture_date'].strftime('%d/%m/%Y')}  {fx['matchday']}")
    print(f"  {fx['home_team']}  vs  {fx['away_team']}")

    played = _prompt_choice("  Played?", ("y", "n", "skip"), default="y")
    if played == "skip":
        return "skipped", None
    if played == "n":
        # Cancellations are rare — confirm so a stray keystroke doesn't delete data.
        confirm = _prompt_choice(
            "  Remove fixture without recording a result?",
            ("y", "n"),
            default="n",
        )
        if confirm == "y":
            return "cancelled", None
        return "skipped", None

    # Recorded path. Ask for scores and validate there's a winner.
    while True:
        home_score = _prompt_int(f"  {fx['home_team']} score: ")
        away_score = _prompt_int(f"  {fx['away_team']} score: ")
        if home_score == away_score:
            print("  Scores are tied — basketball games don't end in ties. Re-enter.")
            continue
        break

    # Pretty-print the outcome so the user can spot a typo before we commit.
    winner = fx["home_team"] if home_score > away_score else fx["away_team"]
    print(
        f"  -> {fx['home_team']} {home_score}, {fx['away_team']} {away_score}  (winner: {winner})"
    )
    confirm = _prompt_choice("  Confirm?", ("y", "n"), default="y")
    if confirm == "n":
        # Let the user retry this fixture next run rather than re-prompting now
        # (keeps the state machine simple — each fixture seen at most once per run).
        print("  Not recorded. Re-run the script to try again.")
        return "skipped", None

    # Build the row in the exact column order the history CSV uses. The
    # derived columns (margin, total, home_win) are convenient to populate
    # but the training pipeline recomputes them from the scores anyway.
    return "recorded", {
        # Write back in the same dd/mm/yyyy format the rest of the project uses.
        cfg.COL_DATE: fx["fixture_date"].strftime("%d/%m/%Y"),
        cfg.COL_HOME: fx["home_team"],
        cfg.COL_AWAY: fx["away_team"],
        cfg.COL_HOME_SCORE: home_score,
        cfg.COL_AWAY_SCORE: away_score,
        "score_diff": home_score - away_score,
        cfg.COL_TOTAL: home_score + away_score,
        cfg.COL_HOME_WIN: int(home_score > away_score),
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main() -> None:
    if not cfg.UPCOMING_FIXTURES_CSV.exists():
        print(f"No upcoming fixtures file at {cfg.UPCOMING_FIXTURES_CSV}")
        return

    upcoming = pd.read_csv(cfg.UPCOMING_FIXTURES_CSV)
    # dayfirst=True so the European dd/mm/yyyy stored in the CSV parses correctly.
    upcoming["fixture_date"] = pd.to_datetime(upcoming["fixture_date"], dayfirst=True)

    if upcoming.empty:
        print(f"No fixtures to record in {cfg.UPCOMING_FIXTURES_CSV}.")
        return

    # Show the menu up front so the user knows what's coming.
    print(f"Found {len(upcoming)} fixture(s) in upcoming_fixtures.csv:\n")
    for i, row in upcoming.iterrows():
        # ASCII-only punctuation — Windows Greek codepage (cp1253) can't
        # render en/em dashes or right-arrows, and crashes on encode.
        print(
            f"  {i + 1}. {row['fixture_date'].strftime('%d/%m/%Y')}  "
            f"{row['matchday']}  -  {row['home_team']} vs {row['away_team']}"
        )

    # Load the full history once so we can append rows to it in one shot at the end.
    history = pd.read_csv(cfg.RAW_GAMES_CSV)

    recorded_rows: list[dict] = []
    kept_fixture_indices: list[int] = []
    cancelled_count = 0

    for idx, row in upcoming.iterrows():
        action, payload = _record_one_fixture(row)
        if action == "recorded":
            recorded_rows.append(payload)
        elif action == "cancelled":
            cancelled_count += 1
        else:
            # "skipped" — keep the fixture for next run.
            kept_fixture_indices.append(idx)

    # --- commit changes ----------------------------------------------------
    # We write both CSVs only AFTER all prompts are done — this keeps the
    # run atomic: either everything persists, or (if the user Ctrl+C'd
    # earlier) nothing does.
    if recorded_rows:
        new_history = pd.concat(
            [history, pd.DataFrame(recorded_rows)],
            ignore_index=True,
        )
        new_history.to_csv(cfg.RAW_GAMES_CSV, index=False)

    # Write whatever fixtures are left back to the upcoming CSV. Using
    # kept_fixture_indices (rather than "everything minus recorded") keeps
    # the logic robust if the user shuffles the file order.
    remaining = upcoming.loc[kept_fixture_indices].copy()
    # Re-serialize the date cleanly so a round-trip doesn't change the format.
    remaining["fixture_date"] = remaining["fixture_date"].dt.strftime("%d/%m/%Y")
    remaining.to_csv(cfg.UPCOMING_FIXTURES_CSV, index=False)

    # --- summary -----------------------------------------------------------
    print("\n" + "=" * 50)
    print(f"Recorded : {len(recorded_rows)}")
    print(f"Cancelled: {cancelled_count}")
    print(f"Skipped  : {len(kept_fixture_indices)}")
    print(f"History now has {len(history) + len(recorded_rows)} games.")
    print(f"Upcoming fixtures file has {len(remaining)} row(s) left.")

    # --- optional retrain --------------------------------------------------
    if recorded_rows:
        retrain = _prompt_choice(
            "\nRetrain the model now with the new results?",
            ("y", "n"),
            default="y",
        )
        if retrain == "y":
            # Import lazily — training pulls in scikit-learn, which takes
            # a second or two. No point paying that if the user is only
            # recording and plans to retrain later.
            from src.model import _format_metrics, train_and_save

            print("\nTraining...\n")
            bundle = train_and_save()
            print(_format_metrics(bundle.metrics))
            print(f"\nModel saved to: {cfg.MODEL_FILE}")


if __name__ == "__main__":
    main()
