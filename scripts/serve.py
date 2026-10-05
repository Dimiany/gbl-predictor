"""Double-click launcher target: serve the site with working Refresh / Contact buttons.

Started by "GBL Predictor.bat" (the desktop shortcut points there). All logic
lives in src/web/server.py; this is the thin CLI wrapper.

    python scripts/serve.py               # update if stale, open the browser, serve
    python scripts/serve.py --no-browser  # same, without opening a browser (tests)
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.web.server import run  # noqa: E402

if __name__ == "__main__":
    run(open_browser="--no-browser" not in sys.argv)
