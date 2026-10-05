"""The GBL Predictor website: data assembly, rendering, local server.

data.py     every number the pages show (build_dashboard)
render.py   HTML shell + bundled assets/app.css and assets/js/*.js
build.py    update_site(): sync -> retrain -> predict -> log -> write page
server.py   127.0.0.1 server behind the Refresh button and contact form
contact.py  contact-form storage
"""

from src.web.build import hours_since_last_sync, update_site
from src.web.data import build_dashboard
from src.web.render import render_html

__all__ = ["build_dashboard", "hours_since_last_sync", "render_html", "update_site"]
