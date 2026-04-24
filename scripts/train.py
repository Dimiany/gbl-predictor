"""Command-line entry point for training the model.

Run with:  python scripts/train.py

Kept in a separate file so the class `PredictorBundle` defined in src.model
gets pickled under its real module path — running `python -m src.model`
would pickle it as `__main__.PredictorBundle`, which then fails to load
from anywhere else.
"""

from __future__ import annotations

# Make `src` importable whether you run this as `python scripts/train.py`
# (cwd = scripts/) or `python -m scripts.train` (cwd = project root).
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src import config as cfg  # noqa: E402
from src.model import _format_metrics, train_and_save  # noqa: E402


def main() -> None:
    bundle = train_and_save()
    print("Training complete. Walk-forward test metrics:\n")
    print(_format_metrics(bundle.metrics))
    print(f"\nModel saved to: {cfg.MODEL_FILE}")


if __name__ == "__main__":
    main()
