"""Contact-form messages, stored locally (data/contact_messages.csv, gitignored)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

from src import config as cfg

FIELDS = ("received_at", "name", "email", "topic", "message")
MAX_LEN = {"name": 80, "email": 120, "topic": 40, "message": 4000}
# Same check as the form (17-contact.js) and firestore.rules: something@something.tld
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class ContactError(ValueError):
    """The submitted form is missing required fields."""


def save_contact_message(payload: dict, path: Path = cfg.CONTACT_MESSAGES_CSV) -> dict:
    """Validate, trim and append one message. Returns the stored row.

    Length limits keep a runaway paste from bloating the file; ``csv`` quoting
    keeps commas and newlines inside messages intact.
    """
    row = {k: str(payload.get(k) or "").strip()[:limit] for k, limit in MAX_LEN.items()}
    if not row["name"] or not row["email"] or not row["message"]:
        raise ContactError("Όνομα, email και μήνυμα είναι υποχρεωτικά.")
    if not EMAIL_RE.fullmatch(row["email"]):
        raise ContactError("Το email δεν φαίνεται σωστό.")
    row = {"received_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), **row}
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return row
