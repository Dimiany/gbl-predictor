"""Translate API team names to the project's canonical names.

Why this is a separate file:
    The API client (api_client.py) deliberately knows NOTHING about our
    project's canonical team naming. The mapping is a boundary concern —
    it lives at the seam between "external world" and "our world". Keeping
    it separate means we can swap APIs later without disturbing the client,
    and swap our naming convention without disturbing the mapping.

Why a CSV and not a hardcoded dict:
    Team naming drifts over time. "Promitheas Vikos Cola" became
    "Promitheas Patras" when the sponsor changed. Having the mapping in a
    user-editable CSV means you fix the drift by editing data, not code.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config as cfg

# The two columns required in the mapping CSV.
MAPPING_COLUMNS = ("api_name", "canonical_name")


def load_mapping(path: Path = cfg.TEAM_NAME_MAPPING_CSV) -> dict[str, str]:
    """Read the mapping CSV and return it as a dict.

    Empty / missing file returns an empty dict, which downstream code
    treats as "nothing mapped yet" rather than an error. That way the
    project boots fine before the mapping is populated.
    """
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}

    missing = [c for c in MAPPING_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Mapping CSV at {path} is missing columns: {missing}. "
            f"Expected columns: {list(MAPPING_COLUMNS)}"
        )

    # Drop rows with blank api_name OR canonical_name — same template
    # pattern we use for rosters.csv.
    df = df.dropna(subset=list(MAPPING_COLUMNS)).copy()
    # Strip whitespace from both sides — a common invisible source of bugs
    # ("PAOK " with a trailing space wouldn't match "PAOK").
    df["api_name"] = df["api_name"].str.strip()
    df["canonical_name"] = df["canonical_name"].str.strip()
    return dict(zip(df["api_name"], df["canonical_name"], strict=True))


def canonicalize(api_name: str, mapping: dict[str, str]) -> str | None:
    """Translate one API name to canonical. Returns None if unmapped.

    Returning None (rather than falling back to ``api_name``) is deliberate:
    it forces the caller to decide what to do with unknown names — usually
    "collect them and show the user so they can add a row to the CSV".
    Silent fallback would mask the problem.
    """
    return mapping.get(api_name)
