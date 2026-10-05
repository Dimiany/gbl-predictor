"""Local web server for the dashboard, so the page's Refresh button works.

Started by double-clicking "GBL Predictor.bat" (or its desktop shortcut):

  1. Re-syncs + retrains if the last sync is older than AUTO_SYNC_AFTER_HOURS,
     otherwise just rebuilds the page from data on disk (no API calls).
  2. Serves dashboard/ at http://127.0.0.1:SERVE_PORT and opens the browser.
  3. POST /api/refresh runs the full update (sync, retrain, predict, log).

Bound to 127.0.0.1 only — nothing outside this computer can reach it. The
refresh endpoint also requires a custom header, which a foreign web page
can't send without a CORS preflight this server never approves.
If the server is already running, a second launch just opens the browser.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import sys
import threading
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402
from src.dashboard import hours_since_last_sync, update_site  # noqa: E402

URL = f"http://127.0.0.1:{cfg.SERVE_PORT}/"
REFRESH_HEADER = "X-GBL-Refresh"
_refresh_lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(cfg.DASHBOARD_FILE.parent), **kwargs)

    def end_headers(self) -> None:
        # Always serve the freshly built page, never a cached copy.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path != "/api/refresh" or self.headers.get(REFRESH_HEADER) != "1":
            self.send_error(404)
            return
        if not _refresh_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "message": "Ήδη τρέχει μια ανανέωση."})
            return
        try:
            print("Ανανέωση από τη σελίδα...")
            message = update_site(sync=True, log=True)
            print(message)
            ok = "skipped" not in message
            self._json(200, {"ok": ok, "message": message})
        except Exception as exc:  # noqa: BLE001 - report anything to the page
            print(f"Σφάλμα: {exc}")
            self._json(500, {"ok": False, "message": str(exc)})
        finally:
            _refresh_lock.release()

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass  # keep the console window readable


def main() -> None:
    open_browser = "--no-browser" not in sys.argv  # flag used by tests
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", cfg.SERVE_PORT), Handler)
    except OSError:
        # Already running (e.g. the shortcut was double-clicked twice).
        if open_browser:
            webbrowser.open(URL)
        return

    stale = hours_since_last_sync() > cfg.AUTO_SYNC_AFTER_HOURS
    print("Φέρνω νέα αποτελέσματα και ενημερώνω..." if stale else "Ετοιμάζω τη σελίδα...")
    try:
        print(update_site(sync=stale, log=stale))
    except Exception as exc:  # noqa: BLE001 - still serve the last good page
        print(f"Η ενημέρωση απέτυχε ({exc}). Δείχνω την τελευταία έκδοση.")

    print(f"\nΗ σελίδα είναι ανοιχτή στο {URL}")
    print("Μην κλείσεις αυτό το παράθυρο όσο χρησιμοποιείς τη σελίδα.")
    print("Για να σταματήσεις: κλείσε αυτό το παράθυρο.\n")
    if open_browser:
        webbrowser.open(URL)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()
