"""Tests for the team-name mapping loader."""

from __future__ import annotations

import pytest

from src.team_name_mapping import canonicalize, load_mapping


def test_load_mapping_missing_file_returns_empty_dict(tmp_path):
    # Graceful first-run behaviour: no file means no mapping, not a crash.
    assert load_mapping(tmp_path / "does_not_exist.csv") == {}


def test_load_mapping_parses_rows(tmp_path):
    path = tmp_path / "map.csv"
    path.write_text("api_name,canonical_name\nKolossos Rhodes,Kolossos Rodou\nAEK Athens,AEK\n")
    mapping = load_mapping(path)
    assert mapping["Kolossos Rhodes"] == "Kolossos Rodou"
    assert mapping["AEK Athens"] == "AEK"


def test_load_mapping_strips_whitespace(tmp_path):
    # CSVs often accrue accidental spaces. We want "PAOK " to match "PAOK".
    path = tmp_path / "map.csv"
    path.write_text("api_name,canonical_name\n  PAOK  ,  PAOK  \n")
    mapping = load_mapping(path)
    assert mapping["PAOK"] == "PAOK"


def test_load_mapping_raises_on_missing_column(tmp_path):
    path = tmp_path / "map.csv"
    path.write_text("api_name\nAEK Athens\n")
    with pytest.raises(ValueError) as exc_info:
        load_mapping(path)
    assert "canonical_name" in str(exc_info.value)


def test_canonicalize_returns_none_for_unknown_name():
    # Critical: unknown names must return None so the caller can flag them,
    # NOT silently fall back to the original. Silent fallback would mask typos.
    mapping = {"AEK Athens": "AEK"}
    assert canonicalize("New Team", mapping) is None


def test_canonicalize_returns_canonical_for_known_name():
    mapping = {"AEK Athens": "AEK"}
    assert canonicalize("AEK Athens", mapping) == "AEK"
