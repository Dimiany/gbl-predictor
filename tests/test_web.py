"""Tests for the website package (src/web): bundling, payload safety, contact storage,
site modes (local / live / preview) and the scheduled cloud run."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from src import config as cfg
from src.web import build
from src.web.contact import ContactError, save_contact_message
from src.web.data import site_settings
from src.web.render import (
    JS_DIR,
    bundle_js,
    js_modules,
    json_payload,
    page_path,
    render_html,
    render_site,
    site_pages,
    slug,
)

ROOT = Path(__file__).resolve().parent.parent


def test_js_modules_load_core_first_and_app_last():
    names = [p.name for p in js_modules()]
    assert names[0] == "01-core.js"
    assert names[-1] == "90-app.js"
    assert names == sorted(names)


def test_bundle_is_one_strict_iife_containing_every_module():
    js = bundle_js()
    assert js.startswith("(() => {\n'use strict';")
    assert js.rstrip().endswith("})();")
    for p in js_modules():
        assert f"// ---- {p.name}" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_bundled_js_is_valid_syntax(tmp_path: Path):
    # A syntax error anywhere would blank the whole site; catch it in CI.
    path = tmp_path / "bundle.js"
    path.write_text(bundle_js(), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_json_payload_cannot_close_the_script_tag():
    out = json_payload({"team": "</script><b>x"})
    assert "</script>" not in out
    assert json.loads(out.replace("<\\/", "</")) == {"team": "</script><b>x"}


def test_json_payload_rejects_nan():
    with pytest.raises(ValueError):
        json_payload({"x": float("nan")})


SITE_DATA = {"season": "2026/27", "games": [], "standings": [{"team": "PAOK"}, {"team": "AEK"}]}


def test_render_site_has_shared_files_and_one_page_per_address():
    files = render_site(SITE_DATA)
    assert "--brand-navy" in files["app.css"]
    assert "// ---- 90-app.js" in files["app.js"]
    assert files["data.js"].startswith("window.TIPOFF_DATA = {")
    for name in (
        "index.html",
        "vathmologia.html",
        "provlepseis/istoriko.html",
        "montelo/odigos-deikton.html",
        "omades/paok.html",
        "omades/aek/apotelesmata.html",
        "404.html",
    ):
        assert name in files, name
        assert '<script src="/app.js" defer></script>' in files[name]
        assert 'data-theme="dark"' in files[name]


def test_every_address_is_unique_and_has_its_own_title():
    pages = site_pages(SITE_DATA)
    assert pages[0].path == "/"
    assert len({p.path for p in pages}) == len(pages)
    assert len({p.title for p in pages}) == len(pages)
    assert all(p.description for p in pages)
    files = render_site({**SITE_DATA, "site": {"mode": "live"}})
    page = files["omades/paok/programma.html"]
    assert "<title>PAOK: πρόγραμμα αγώνων 2026/27 · TipOff</title>" in page
    assert f'<link rel="canonical" href="{cfg.SITE_URL}/omades/paok/programma">' in page


def test_routes_reach_the_js():
    js = render_site(SITE_DATA)["data.js"]
    data = json.loads(js.removeprefix("window.TIPOFF_DATA = ").rstrip().rstrip(";"))
    meta = data["routes"]["meta"]
    assert meta["/vathmologia"][0].startswith("Βαθμολογία")
    assert data["routes"]["pages"]["teams"] == "omades"


def test_page_path_and_slug():
    assert page_path("home") == "/"
    assert page_path("predictions", "next") == "/provlepseis"  # first tab = page address
    assert page_path("model", "how") == "/montelo/pos-doulevei"
    assert (
        page_path("team", "results", "AS Karditsas Iaponiki")
        == "/omades/as-karditsas-iaponiki/apotelesmata"
    )
    assert slug("Vikos Falcons Ioanninon") == "vikos-falcons-ioanninon"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_slug_matches_python_slug():
    core = (JS_DIR / "01-core.js").read_text(encoding="utf-8")
    rule = re.search(r"^const slugOf = .*$", core, re.M).group(0)
    names = ["AS Karditsas Iaponiki", "Promitheas Vikos Cola", "PAOK", " Doxa  Lefkadas "]
    script = f"{rule}\nconsole.log(JSON.stringify({json.dumps(names)}.map(slugOf)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [slug(n) for n in names]


def test_not_found_page_is_never_indexed():
    page = render_site({**SITE_DATA, "site": {"mode": "live"}})["404.html"]
    assert 'name="robots" content="noindex' in page
    assert 'rel="canonical"' not in page


def test_write_pages_drops_pages_from_an_earlier_build(tmp_path):
    (tmp_path / "omades").mkdir()
    (tmp_path / "omades" / "panionios.html").write_text("old", encoding="utf-8")
    (tmp_path / "og-card.jpg").write_bytes(b"keep")
    assert build.write_pages(tmp_path, {"index.html": "x", "omades/paok.html": "y"}) == 2
    assert not (tmp_path / "omades" / "panionios.html").exists()
    assert (tmp_path / "omades" / "paok.html").read_text(encoding="utf-8") == "y"
    assert (tmp_path / "og-card.jpg").exists()


def test_local_server_serves_clean_addresses_like_firebase(tmp_path, monkeypatch):
    import http.server
    import threading
    import urllib.error
    import urllib.request

    from src.web.server import Handler

    (tmp_path / "index.html").write_text("home", encoding="utf-8")
    (tmp_path / "omades").mkdir()
    (tmp_path / "omades" / "paok.html").write_text("paok", encoding="utf-8")
    (tmp_path / "404.html").write_text("lost", encoding="utf-8")
    monkeypatch.setattr(cfg, "DASHBOARD_FILE", tmp_path / "index.html")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert urllib.request.urlopen(base + "/").read() == b"home"
        assert urllib.request.urlopen(base + "/omades/paok").read() == b"paok"
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/omades/nobody")
        assert err.value.code == 404 and err.value.read() == b"lost"
    finally:
        server.shutdown()
        server.server_close()


def test_save_contact_message_appends_rows_with_header(tmp_path: Path):
    path = tmp_path / "msgs.csv"
    save_contact_message(
        {"name": "Δημήτρης", "topic": "Πρόταση", "message": "γεια, σας\nνέα γραμμή"}, path
    )
    save_contact_message({"name": "Άλλος", "message": "δεύτερο"}, path)
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["name"] for r in rows] == ["Δημήτρης", "Άλλος"]
    assert rows[0]["message"] == "γεια, σας\nνέα γραμμή"  # commas/newlines survive


def test_save_contact_message_requires_name_and_message(tmp_path: Path):
    with pytest.raises(ContactError):
        save_contact_message({"name": "  ", "message": "x"}, tmp_path / "m.csv")
    with pytest.raises(ContactError):
        save_contact_message({"name": "x", "message": ""}, tmp_path / "m.csv")


def test_save_contact_message_truncates_long_fields(tmp_path: Path):
    row = save_contact_message({"name": "n" * 500, "message": "m" * 10_000}, tmp_path / "m.csv")
    assert len(row["name"]) == 80
    assert len(row["message"]) == 4000


# ---------------------------------------------------------------- site modes


def test_csp_allows_only_our_own_script_files():
    page = render_html({"season": "2026/27", "games": []})
    assert "script-src 'self';" in page
    assert "default-src 'none'" in page
    assert re.search(r"<script(?![^>]*src=)", page) is None  # no inline script at all


def test_only_preview_builds_are_noindex():
    def page(mode):
        return render_html({"season": "2026/27", "games": [], "site": {"mode": mode}})

    assert 'name="robots"' in page("preview")
    assert 'name="robots"' not in page("live")
    assert 'name="robots"' not in page("local")


def test_site_settings_local_never_exposes_firestore(monkeypatch):
    monkeypatch.setattr(cfg, "FIREBASE_PROJECT_ID", "p")
    monkeypatch.setattr(cfg, "FIREBASE_API_KEY", "k")
    assert site_settings("local")["firestore"] is None


def test_site_settings_preview_and_live_use_separate_collections(monkeypatch):
    monkeypatch.setattr(cfg, "FIREBASE_PROJECT_ID", "p")
    monkeypatch.setattr(cfg, "FIREBASE_API_KEY", "k")
    live, preview = site_settings("live")["firestore"], site_settings("preview")["firestore"]
    assert live == {"project": "p", "key": "k", "collection": "contact_messages"}
    assert preview["collection"] == "test_contact_messages"


def test_site_settings_rejects_unknown_mode():
    with pytest.raises(ValueError):
        site_settings("staging")


def test_firestore_rules_match_the_form():
    # The rules whitelist both collections and exactly the form's topics.
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    for collection in cfg.CONTACT_COLLECTIONS.values():
        assert f"'{collection}'" in rules
    js = (JS_DIR / "17-contact.js").read_text(encoding="utf-8")
    js_topics = re.search(r"const TOPICS = \[(.*?)\];", js).group(1)
    rules_topics = re.search(r"m\.topic in \[(.*?)\]", rules).group(1)
    assert js_topics.replace(" ", "") == rules_topics.replace(" ", "")


def test_firebase_hosting_serves_the_built_dashboard():
    conf = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
    sites = {h["site"]: h for h in conf["hosting"]}
    assert set(sites) == {"gbl-predictor", "gbl-predictor-test"}
    assert {h["public"] for h in sites.values()} == {cfg.DASHBOARD_FILE.parent.name}
    test_headers = {x["key"] for x in sites["gbl-predictor-test"]["headers"][0]["headers"]}
    assert "X-Robots-Tag" in test_headers  # the test site stays out of search engines
    assert conf["firestore"]["rules"] == "firestore.rules"


# ---------------------------------------------------------------- cloud run


D = pd.Timestamp


def test_sync_due_weekly_check_on_monday():
    assert build.sync_due(D("2026-10-12"), [], []) == "weekly check"  # a Monday


def test_sync_due_when_recent_results_are_expected():
    assert build.sync_due(D("2026-10-14"), [D("2026-10-11")], []) == "results due"
    # A game postponed long ago doesn't make every night sync.
    assert build.sync_due(D("2026-10-14"), [D("2026-10-01")], []) is None


def test_sync_due_before_an_unlogged_game_only():
    wed = D("2026-10-14")
    fri = D("2026-10-16")
    assert build.sync_due(wed, [fri], [fri]) == "upcoming game not logged yet"
    assert build.sync_due(wed, [fri], []) is None  # already logged
    assert build.sync_due(wed, [D("2026-10-20")], [D("2026-10-20")]) is None  # too far ahead


def test_local_refresh_pulls_instead_of_syncing_in_cloud_mode(monkeypatch):
    monkeypatch.setattr(cfg, "CLOUD_SYNC", True)
    assert build.local_refresh_kwargs() == {"sync": False, "log": False, "pull": True}
    monkeypatch.setattr(cfg, "CLOUD_SYNC", False)
    assert build.local_refresh_kwargs() == {"sync": True, "log": True, "pull": False}


def _fake_git(monkeypatch, branch="main", fail=()):
    """Stub git: ``fail`` lists sub-commands that fail (each entry fails once)."""
    calls, fail = [], list(fail)

    def fake_run(cmd, **kwargs):
        sub = cmd[1]
        calls.append(sub)
        if sub == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, branch + "\n", "")
        if sub in fail:
            fail.remove(sub)
            return subprocess.CompletedProcess(cmd, 1, "", f"fatal: {sub} failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    return calls


def test_pull_latest_fetches_then_fast_forwards(monkeypatch):
    calls = _fake_git(monkeypatch)
    assert build.pull_latest() == "Pull: up to date with GitHub."
    assert calls == ["rev-parse", "fetch", "merge"]  # never a bare `git pull`


def test_pull_latest_retries_a_transient_failure(monkeypatch):
    calls = _fake_git(monkeypatch, fail=["fetch"])
    assert build.pull_latest() == "Pull: up to date with GitHub."
    assert calls == ["rev-parse", "fetch", "fetch", "merge"]


def test_pull_latest_reports_git_failure_without_raising(monkeypatch):
    _fake_git(monkeypatch, fail=["merge", "merge"])
    assert build.pull_latest() == "Pull: skipped — fatal: merge failed"


def test_pull_latest_leaves_feature_branches_alone(monkeypatch):
    calls = _fake_git(monkeypatch, branch="new-feature")
    assert "not 'main'" in build.pull_latest()
    assert calls == ["rev-parse"]


def test_overlays_inherit_the_theme():
    # Tooltip, toast and to-top read colour tokens defined on .viz-root; outside
    # it they render with a transparent background (text over the page).
    page = render_html({"season": "2026/27", "games": []})
    root_end = page.index("</body>")
    for overlay in ('id="tip"', 'id="toast"', 'id="to-top"'):
        assert page.index('<div class="viz-root">') < page.index(overlay) < root_end
        assert page.rindex("</div>", 0, root_end) > page.index(overlay)


# ---------------------------------------------------------------- crests


def _crest_tools():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fetch_crests", ROOT / "scripts" / "fetch_crests.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_crop_to_crest_drops_a_sponsor_below_the_crest():
    from PIL import Image, ImageDraw

    tools = _crest_tools()
    img = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 10, 180, 170), fill="orange")  # the crest
    draw.rectangle((40, 220, 160, 260), fill="red")  # sponsor, 50 px below
    assert tools.crop_to_crest(img).size == (161, 161)


def test_fit_in_circle_keeps_every_pixel_inside_the_round_frame():
    import numpy as np
    from PIL import Image, ImageDraw

    tools = _crest_tools()
    shield = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
    ImageDraw.Draw(shield).rectangle((0, 0, 119, 159), fill="black")  # worst case: sharp corners
    out = tools.fit_in_circle(shield, 192)
    ys, xs = np.nonzero(np.asarray(out)[:, :, 3] > 8)
    assert out.size == (192, 192)
    assert np.sqrt((xs - 95.5) ** 2 + (ys - 95.5) ** 2).max() <= 96


def test_every_crest_source_has_a_crop_rule():
    import pandas as pd

    sources = pd.read_csv(cfg.CREST_SOURCES_CSV)
    assert set(sources["crop"]) <= {"sponsor", "none"}
    assert sources["team"].is_unique


def test_page_links_favicon_and_touch_icon_files(tmp_path):
    page = render_html({"season": "2026/27", "games": []})
    assert '<link rel="icon" type="image/svg+xml" href="/favicon.svg">' in page
    assert '<link rel="apple-touch-icon" href="/apple-touch-icon.png">' in page
    assert "img-src 'self' data:" in page  # own files + inlined fallback crests
    build.write_site_files(tmp_path, mode="live")
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        assert (tmp_path / name).stat().st_size > 100, name


def test_site_uses_the_brand_name_everywhere():
    page = render_html({"season": "2026/27", "games": []})
    assert f"<title>{cfg.SITE_NAME} · {cfg.SITE_TAGLINE}</title>" in page
    assert f"<b>{cfg.SITE_NAME}</b>" in page  # header
    assert "GBL Predictor" not in page  # the old name, gone from page text and scripts


def test_share_card_meta_points_at_the_public_site():
    page = render_html({"season": "2026/27", "games": [], "site": {"mode": "live"}})
    assert f'<meta property="og:image" content="{cfg.SITE_URL}/{cfg.SHARE_CARD_FILE}">' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert f'<link rel="canonical" href="{cfg.SITE_URL}/">' in page
    preview = render_html({"season": "2026/27", "games": [], "site": {"mode": "preview"}})
    assert 'rel="canonical"' not in preview  # only the live site claims the address


def test_site_files_invite_crawlers_only_on_live(tmp_path):
    build.write_site_files(tmp_path, mode="live")
    assert (tmp_path / cfg.SHARE_CARD_FILE).stat().st_size > 10_000
    assert f"Sitemap: {cfg.SITE_URL}/sitemap.xml" in (tmp_path / "robots.txt").read_text()
    assert f"<loc>{cfg.SITE_URL}/</loc>" in (tmp_path / "sitemap.xml").read_text()
    assert (tmp_path / "crests" / "paok.webp").exists()  # crests are files, not inlined
    build.write_site_files(tmp_path, mode="live", paths=["/", "/vathmologia"])
    assert f"<loc>{cfg.SITE_URL}/vathmologia</loc>" in (tmp_path / "sitemap.xml").read_text()
    build.write_site_files(tmp_path, mode="preview")
    assert "Disallow: /" in (tmp_path / "robots.txt").read_text()
