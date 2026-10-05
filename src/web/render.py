"""HTML rendering: the page shell plus the bundled CSS and JavaScript.

The JavaScript lives in ``assets/js/*.js``, one file per concern, loaded in
file-name order (``01-core`` → ``90-app``) and concatenated into a single
strict-mode IIFE. No build tool, no CDN: the output is one self-contained
``index.html`` that works offline.
"""

from __future__ import annotations

import json
from pathlib import Path

ASSETS_DIR = Path(__file__).with_name("assets")
JS_DIR = ASSETS_DIR / "js"


def js_modules() -> list[Path]:
    """The JavaScript modules in load order (numeric file-name prefix)."""
    return sorted(JS_DIR.glob("*.js"))


def bundle_js() -> str:
    """Concatenate every module into one IIFE so they share a private scope."""
    parts = [f"// ---- {p.name}\n{p.read_text(encoding='utf-8')}" for p in js_modules()]
    return "(() => {\n'use strict';\n" + "\n".join(parts) + "\n})();\n"


def bundle_css() -> str:
    return (ASSETS_DIR / "app.css").read_text(encoding="utf-8")


def json_payload(data: dict) -> str:
    """Serialise data for a <script type="application/json"> block.

    ``allow_nan=False`` fails loudly instead of emitting NaN (invalid JSON), and
    escaping ``</`` stops a team name from ever closing the script tag.
    """
    return json.dumps(data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")


def render_html(data: dict) -> str:
    """Return the full single-file site."""
    return f"""<!doctype html>
<html lang="el" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="description" content="Προβλέψεις, βαθμολογία και στατιστικά για την Stoiximan Basket League {data["season"]}">
<title>GBL Predictor · {data["season"]}</title>
<style>{bundle_css()}</style>
</head>
<body>
<div class="viz-root">
  <header class="site-head">
    <a class="brand" href="#/" aria-label="GBL Predictor, αρχική"><span class="brand-badge" id="brand-badge" aria-hidden="true"></span><span class="brand-text"><b>GBL Predictor</b><small id="brand-season"></small></span></a>
    <nav id="nav" aria-label="Κύρια πλοήγηση"></nav>
    <div class="head-tools">
      <button id="refresh" class="btn btn-primary" type="button" title="Φέρνει νέα αποτελέσματα και ξαναβγάζει τις προβλέψεις"><span class="spin" aria-hidden="true">⟳</span> Ανανέωση</button>
      <label class="focus-pick"><span>Η ομάδα μου</span><select id="focus"></select></label>
      <a class="icon-btn" href="#/help" aria-label="Οδηγίες" title="Οδηγίες">?</a>
      <button id="theme" class="icon-btn" type="button" aria-label="Αλλαγή θέματος" title="Σκοτεινό / φωτεινό">◐</button>
    </div>
    <div class="scroll-progress" id="scroll-progress" aria-hidden="true"></div>
  </header>
  <main id="app" tabindex="-1"></main>
  <footer class="site-foot" id="foot"></footer>
</div>
<button class="to-top" id="to-top" type="button" aria-label="Πάνω">↑</button>
<div id="tip" class="tip" role="tooltip" hidden></div>
<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>
<script id="data" type="application/json">{json_payload(data)}</script>
<script>{bundle_js()}</script>
</body>
</html>"""
