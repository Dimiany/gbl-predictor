"""Predicted-vs-actual reporting.

What this file does: take the walk-forward test predictions that were
captured during training, and render them as a table you can actually read
and interpret.

Why it's a separate module: ``model.py`` is about training and
persistence. ``predict.py`` is about forecasting the future. Showing an
honest retrospective — "here's what the model said about games it hadn't
seen, and here's what really happened" — is a third thing, presentation
of backtest data. Keeping it in its own file makes that boundary explicit.

Honesty matters here. The rows in the comparison table are walk-forward
test predictions: the model was trained on all games BEFORE this point in
the season and asked to predict the remaining games. That's a faithful
measure of out-of-sample accuracy — it's how well the model would have
done if you'd deployed it earlier in the season.
"""

from __future__ import annotations

import pandas as pd

from src import config as cfg
from src.model import PredictorBundle


def build_comparison_table(bundle: PredictorBundle) -> pd.DataFrame:
    """Return a tidy 'predicted vs actual' DataFrame for the test set.

    Each row is one held-out game, with predicted and actual scores side by
    side plus derived error columns. Columns chosen to be readable in a
    DataFrame display or exportable to CSV without extra formatting.
    """
    df = bundle.test_predictions.copy()
    if df.empty:
        # Older bundles (trained before backtest support landed) won't have
        # this data. Return an empty frame with the expected schema so the
        # caller's display code still works.
        return pd.DataFrame(
            columns=[
                cfg.COL_DATE,
                cfg.COL_HOME,
                cfg.COL_AWAY,
                "predicted",
                "actual",
                "winner_predicted",
                "winner_actual",
                "home_win_prob",
                "margin_error",
                "correct",
            ]
        )

    # Round scores at display time — raw floats aren't useful to look at.
    df["pred_home_int"] = df["predicted_home_score"].round().astype(int)
    df["pred_away_int"] = df["predicted_away_score"].round().astype(int)

    # Combined "predicted" and "actual" columns — the user's explicit ask
    # was "predicted result and actual result SAME LINE". Each as a compact
    # scoreline string keeps the table narrow and skimmable.
    df["predicted"] = df["pred_home_int"].astype(str) + "-" + df["pred_away_int"].astype(str)
    df["actual"] = df["actual_home_score"].astype(str) + "-" + df["actual_away_score"].astype(str)

    # Error diagnostics. ``margin_error`` is how many points the predicted
    # margin was off by, ignoring sign — a quick-read "how close were we".
    df["predicted_margin"] = df["pred_home_int"] - df["pred_away_int"]
    df["actual_margin"] = df["actual_home_score"] - df["actual_away_score"]
    df["margin_error"] = (df["predicted_margin"] - df["actual_margin"]).abs()

    # Human-readable probability column — "62%" is faster to parse than 0.623.
    df["home_win_prob_pct"] = (df["home_win_probability"] * 100).round(0).astype(int).astype(
        str
    ) + "%"

    # Final selection + rename for presentation.
    out = df[
        [
            cfg.COL_DATE,
            cfg.COL_HOME,
            cfg.COL_AWAY,
            "predicted",
            "actual",
            "predicted_winner",
            "actual_winner",
            "home_win_prob_pct",
            "margin_error",
            "winner_correct",
        ]
    ].rename(
        columns={
            cfg.COL_DATE: "date",
            cfg.COL_HOME: "home",
            cfg.COL_AWAY: "away",
            "predicted_winner": "winner_pred",
            "actual_winner": "winner_real",
            "home_win_prob_pct": "home_win_prob",
            "winner_correct": "correct",
        }
    )

    # Chronological order — easier to scan than whatever internal index.
    out = out.sort_values("date").reset_index(drop=True)
    return out


def comparison_summary(bundle: PredictorBundle) -> str:
    """Short multi-line summary string — handy for a notebook print cell."""
    df = bundle.test_predictions
    if df.empty:
        return "No backtest data in this bundle. Retrain with the new model.py to populate it."
    n = len(df)
    n_correct = int(df["winner_correct"].sum())
    accuracy_pct = 100.0 * n_correct / n
    mean_margin_err = (
        (
            (df["predicted_home_score"] - df["predicted_away_score"])
            - (df["actual_home_score"] - df["actual_away_score"])
        )
        .abs()
        .mean()
    )
    return (
        f"Walk-forward test backtest: {n} games held out.\n"
        f"  Winner called correctly : {n_correct}/{n}  ({accuracy_pct:.1f}%)\n"
        f"  Mean absolute margin err: {mean_margin_err:.1f} points"
    )
