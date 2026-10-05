"""Tests for the website package (src/web): bundling, payload safety, contact storage."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.web.contact import ContactError, save_contact_message
from src.web.render import bundle_js, js_modules, json_payload, render_html


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


def test_render_html_embeds_data_css_and_js():
    page = render_html({"season": "2026/27", "games": []})
    assert '<script id="data" type="application/json">' in page
    assert "--brand-navy" in page  # stylesheet inlined
    assert "// ---- 90-app.js" in page  # scripts inlined
    assert 'data-theme="dark"' in page


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
