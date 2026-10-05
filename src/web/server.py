"""Local web server behind the site's Refresh button and contact form.

Bound to 127.0.0.1 only — nothing outside this computer can reach it. Both POST
endpoints require a custom header, which a foreign web page can't send without
a CORS preflight this server never approves (so other sites can't trigger
refreshes or post messages through the user's browser).

    POST /api/refresh   sync + retrain + predict + log + rebuild
    POST /api/contact   store a contact-form message
"""

from __future__ import annotations

import contextlib
import http.server
import json
import threading
import webbrowser

from src import config as cfg
from src.web.build import hours_since_last_sync, update_site
from src.web.contact import ContactError, save_contact_message

URL = f"http://127.0.0.1:{cfg.SERVE_PORT}/"
GUARD_HEADER = "X-GBL-Refresh"
MAX_BODY_BYTES = 20_000
_refresh_lock = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(cfg.DASHBOARD_FILE.parent), **kwargs)

    def end_headers(self) -> None:
        # Always serve the freshly built page, never a cached copy.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.headers.get(GUARD_HEADER) != "1":
            self.send_error(404)
            return
        if self.path == "/api/refresh":
            self._refresh()
        elif self.path == "/api/contact":
            self._contact()
        else:
            self.send_error(404)

    def _refresh(self) -> None:
        if not _refresh_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "message": "Ήδη τρέχει μια ανανέωση."})
            return
        try:
            print("Ανανέωση από τη σελίδα...")
            message = update_site(sync=True, log=True)
            print(message)
            self._json(200, {"ok": "skipped" not in message, "message": message})
        except Exception as exc:  # noqa: BLE001 - report anything to the page
            print(f"Σφάλμα: {exc}")
            self._json(500, {"ok": False, "message": str(exc)})
        finally:
            _refresh_lock.release()

    def _contact(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY_BYTES:
            self._json(413, {"ok": False, "message": "Πολύ μεγάλο μήνυμα."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            row = save_contact_message(payload if isinstance(payload, dict) else {})
        except (ValueError, ContactError) as exc:
            self._json(400, {"ok": False, "message": str(exc)})
            return
        print(f"Νέο μήνυμα από {row['name']} ({row['topic']})")
        self._json(200, {"ok": True, "message": "Αποθηκεύτηκε."})

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass  # keep the console window readable


def run(open_browser: bool = True) -> None:
    """Update if stale, then serve until the console window is closed."""
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
