"""The one-call site update used by the Refresh button and scripts/build_dashboard.py."""

from __future__ import annotations

import pandas as pd

from src import config as cfg
from src.model import PredictorBundle, train_and_save
from src.prediction_log import append_predictions
from src.sync import sync_for_notebook
from src.web.data import build_dashboard
from src.web.render import render_html


def update_site(sync: bool = True, log: bool = True) -> str:
    """[sync + retrain] -> predict -> [log] -> write dashboard/index.html.

    Never raises on API trouble (sync_for_notebook swallows it); returns a
    short human-readable status for the console / the page's toast.
    """
    lines = []
    if sync or not cfg.MODEL_FILE.exists():
        if sync:
            lines.append(sync_for_notebook())
            cfg.LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            cfg.LAST_SYNC_FILE.write_text(pd.Timestamp.now().isoformat(), encoding="utf-8")
        bundle = train_and_save()
    else:
        bundle = PredictorBundle.load()
    data, preds = build_dashboard(bundle)
    if log:
        append_predictions(preds)
    cfg.DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.DASHBOARD_FILE.write_text(render_html(data), encoding="utf-8")
    lines.append(f"Dashboard written ({len(preds)} next-round prediction(s)).")
    return "\n".join(lines)


def hours_since_last_sync() -> float:
    """Hours since update_site last synced (infinity if never)."""
    try:
        last = pd.Timestamp(cfg.LAST_SYNC_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return float("inf")
    return (pd.Timestamp.now() - last).total_seconds() / 3600
