"""Log retroactive predictions for already-played games (a missed round).

Usage:
    python scripts/backfill_predictions.py 03/10/2026 04/10/2026

The model is fit only on games before the first date and predicts every game
in the range from that pre-round state (src.prediction_log.predict_retroactively).
Rows are only added for fixtures not logged yet, never replacing a real
pre-game prediction. Their prediction_made_at is after the game, so the site
labels them "αναδρομική" and keeps them out of the pre-game record.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.prediction_log import append_predictions, predict_retroactively  # noqa: E402


def main(start: str, end: str) -> None:
    first, last = (pd.to_datetime(d, dayfirst=True) for d in (start, end))
    preds = predict_retroactively(first, last)
    for p in preds:
        print(f"{p.date} {p.home} {p.predicted_home_score}-{p.predicted_away_score} {p.away}")
    append_predictions(preds, overwrite=False)
    print(f"{len(preds)} retroactive prediction(s); existing rows were kept.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
