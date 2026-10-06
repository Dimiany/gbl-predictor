"""Build the static HTML dashboard: dashboard/index.html.

Usage:
    python scripts/build_dashboard.py            # sync + retrain + build
    python scripts/build_dashboard.py --no-sync  # use data/model already on disk
    python scripts/build_dashboard.py --auto     # scheduled cloud run: sync only if due

By default this is the whole "normal path" in one command: pull new results
from FlashScore, retrain, predict the next round, log those predictions to
data/prediction_history.csv (so the accuracy record grows), and write the page.
Day to day, the desktop shortcut (GBL Predictor.bat -> scripts/serve.py) does
the same through the page's Refresh button.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402
from src.web import update_site  # noqa: E402
from src.web.build import scheduled_sync_reason  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-sync", action="store_true", help="Skip the API sync and retrain.")
    parser.add_argument("--no-log", action="store_true", help="Don't log next-round predictions.")
    parser.add_argument("--open", action="store_true", help="Open the page in a browser.")
    parser.add_argument(
        "--auto", action="store_true", help="Sync + log only if due (src.web.build.sync_due)."
    )
    args = parser.parse_args()

    if args.auto:
        reason = scheduled_sync_reason()
        _github_output(built="true" if reason else "false")
        if not reason:
            print("Nothing due today: no API call, no rebuild.")
            return
        print(f"Sync due: {reason}")
    print(update_site(sync=not args.no_sync, log=not args.no_log))
    print(f"-> {cfg.DASHBOARD_FILE}")
    if args.open:
        webbrowser.open(cfg.DASHBOARD_FILE.as_uri())


def _github_output(**values: str) -> None:
    """Expose step outputs to the GitHub Actions workflow (no-op elsewhere)."""
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in values.items())


if __name__ == "__main__":
    main()
