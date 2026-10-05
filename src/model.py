"""Model training, evaluation, and persistence.

ONE margin model drives everything a prediction shows:

  1. margin_reg — linear regression for (home_score - away_score) on a few
     pre-game signals: Elo difference (with home court), L5 form difference,
     season win-% difference.
  2. P(home win) = Phi(margin / sigma), where sigma is the margin model's
     residual spread. Probability and scoreline therefore can never disagree
     on the winner (the old setup used three independent models and could).
  3. total_reg — ridge regression for (home_score + away_score) on L5
     scoring / conceding form.

    home_score = (total + margin) / 2,  away_score = (total - margin) / 2

Why linear, not gradient boosting? A rolling walk-forward comparison on the
~180-game history (see CLAUDE.md) found the boosted classifier the worst
calibrated model of all, and the linear margin model as good as the old
ML+Elo blend on log-loss while beating the boosted regressor on margin error.
On this little data, simple wins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from src import config as cfg
from src.features import build_features

# ---------------------------------------------------------------------------
# Model inputs
# ---------------------------------------------------------------------------


def model_inputs(features: pd.DataFrame, total_fill: dict[str, float]) -> pd.DataFrame:
    """Derive the model's input columns from the feature frame, NaN-free.

    Early-season rows have NaN form / win-% (no games yet). Linear models
    can't take NaN, so "no information" is encoded as a neutral value: zero
    form difference, 50% win rate, and the training-set mean for L5 scoring.
    """
    out = pd.DataFrame(index=features.index)
    out["elo_diff_adj"] = features["elo_diff_adj"]
    out["form_diff"] = features["home_margin_L5"].fillna(0.0) - features["away_margin_L5"].fillna(
        0.0
    )
    out["win_pct_diff"] = features["home_season_win_pct"].fillna(0.5) - features[
        "away_season_win_pct"
    ].fillna(0.5)
    for col in cfg.TOTAL_FEATURES:
        out[col] = features[col].fillna(total_fill[col])
    return out


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(z, dtype=float) / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# The trained bundle
# ---------------------------------------------------------------------------


@dataclass
class PredictorBundle:
    """All trained artifacts that live together and are saved/loaded together."""

    margin_reg: LinearRegression
    total_reg: Ridge
    # Residual std of the margin model on its training data; converts a
    # predicted margin into a win probability and is the "±" on scorelines.
    margin_sigma: float
    # Fill values (training means) for L5 scoring columns that are NaN early-season.
    total_fill: dict[str, float]
    metrics: dict
    # Out-of-sample predictions from the rolling walk-forward evaluation: every
    # game after the warm-up, predicted by a model trained only on earlier days.
    test_predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Written into prediction_history.csv so each logged prediction records
    # which model made it.
    version: str = cfg.MODEL_VERSION

    def predict(self, features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (margin, total, home_win_probability) for each feature row."""
        X = model_inputs(features, self.total_fill)
        margin = self.margin_reg.predict(X[cfg.MARGIN_FEATURES])
        total = self.total_reg.predict(X[cfg.TOTAL_FEATURES])
        p_home = _normal_cdf(margin / self.margin_sigma)
        return margin, total, p_home

    def save(self, path: Path = cfg.MODEL_FILE) -> None:
        # Create parent directory if missing — avoids the classic
        # "FileNotFoundError on first run" papercut.
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path = cfg.MODEL_FILE) -> PredictorBundle:
        return joblib.load(path)


def _fit_bundle(train: pd.DataFrame) -> PredictorBundle:
    """Fit margin + total models on one block of past games."""
    total_fill = {c: float(train[c].mean()) for c in cfg.TOTAL_FEATURES}
    # A column that's all-NaN (very early) has a NaN mean: fall back to a
    # plausible league-wide scoring level.
    total_fill = {c: (v if v == v else 80.0) for c, v in total_fill.items()}
    X = model_inputs(train, total_fill)

    margin_reg = LinearRegression().fit(X[cfg.MARGIN_FEATURES], train[cfg.TARGET_MARGIN])
    residuals = train[cfg.TARGET_MARGIN] - margin_reg.predict(X[cfg.MARGIN_FEATURES])
    sigma = float(np.std(residuals)) or 12.0
    total_reg = Ridge(alpha=cfg.TOTAL_RIDGE_ALPHA).fit(
        X[cfg.TOTAL_FEATURES], train[cfg.TARGET_TOTAL]
    )
    return PredictorBundle(
        margin_reg=margin_reg,
        total_reg=total_reg,
        margin_sigma=sigma,
        total_fill=total_fill,
        metrics={},
    )


def scoreline(margin: float, total: float) -> tuple[int, int]:
    """Round (margin, total) to a whole-number scoreline that keeps the winner.

    The predicted margin is rounded first and never to zero, so the scoreline
    always agrees with the probability (P > 50% <=> margin > 0).
    """
    m = int(round(margin))
    if m == 0:
        m = 1 if margin >= 0 else -1
    home = int(round((total + m) / 2.0))
    return home, home - m


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def walk_forward_evaluate(features_df: pd.DataFrame) -> dict:
    """Rolling walk-forward: predict each game day from all EARLIER days only.

    After a warm-up of WALK_FORWARD_WARMUP games, the model is refit before
    every game day and predicts that day's games. This mimics real use exactly
    (you only ever know the past) and scores every later game out-of-sample,
    not just one 20% tail — far less noisy than a single split on ~180 games.
    """
    features_df = features_df.sort_values(cfg.COL_DATE, kind="stable").reset_index(drop=True)
    rows: list[pd.DataFrame] = []
    margins, totals, probs = [], [], []
    for day in sorted(features_df[cfg.COL_DATE].unique()):
        past = features_df[features_df[cfg.COL_DATE] < day]
        if len(past) < cfg.WALK_FORWARD_WARMUP:
            continue
        today = features_df[features_df[cfg.COL_DATE] == day]
        m, t, p = _fit_bundle(past).predict(today)
        rows.append(today)
        margins.extend(m)
        totals.extend(t)
        probs.extend(p)

    test = pd.concat(rows) if rows else features_df.iloc[0:0]
    margins, totals, probs = np.array(margins), np.array(totals), np.array(probs)
    y_win = test[cfg.TARGET_CLASSIFICATION].to_numpy()
    elo_prob = test["home_win_prob_elo"].to_numpy()

    metrics: dict = {"n_train": cfg.WALK_FORWARD_WARMUP, "n_test": len(test)}
    if len(test):
        metrics.update(
            {
                "accuracy": accuracy_score(y_win, (probs >= 0.5).astype(int)),
                "log_loss": log_loss(y_win, probs, labels=[0, 1]),
                "brier_score": brier_score_loss(y_win, probs),
                "margin_mae": mean_absolute_error(test[cfg.TARGET_MARGIN], margins),
                "margin_rmse": float(np.sqrt(mean_squared_error(test[cfg.TARGET_MARGIN], margins))),
                "margin_r2": r2_score(test[cfg.TARGET_MARGIN], margins),
                "total_mae": mean_absolute_error(test[cfg.TARGET_TOTAL], totals),
                "total_rmse": float(np.sqrt(mean_squared_error(test[cfg.TARGET_TOTAL], totals))),
                "total_r2": r2_score(test[cfg.TARGET_TOTAL], totals),
                # Baseline: does the model beat plain Elo?
                "elo_baseline_accuracy": accuracy_score(y_win, (elo_prob >= 0.5).astype(int)),
                "elo_baseline_log_loss": log_loss(y_win, elo_prob, labels=[0, 1]),
                "elo_baseline_brier": brier_score_loss(y_win, elo_prob),
                "home_win_rate": float(y_win.mean()),
            }
        )

    lines = [scoreline(m, t) for m, t in zip(margins, totals, strict=True)]
    home_scores = np.array([h for h, _ in lines], dtype=int)
    away_scores = np.array([a for _, a in lines], dtype=int)
    test_predictions = pd.DataFrame(
        {
            cfg.COL_DATE: test[cfg.COL_DATE].values,
            cfg.COL_HOME: test[cfg.COL_HOME].values,
            cfg.COL_AWAY: test[cfg.COL_AWAY].values,
            "actual_home_score": test[cfg.COL_HOME_SCORE].values,
            "actual_away_score": test[cfg.COL_AWAY_SCORE].values,
            "actual_winner": np.where(
                test[cfg.COL_HOME_SCORE].values > test[cfg.COL_AWAY_SCORE].values,
                test[cfg.COL_HOME].values,
                test[cfg.COL_AWAY].values,
            ),
            "predicted_home_score": home_scores,
            "predicted_away_score": away_scores,
            "predicted_margin": margins,
            "home_win_probability": probs,
            "predicted_winner": np.where(
                probs >= 0.5, test[cfg.COL_HOME].values, test[cfg.COL_AWAY].values
            ),
        }
    )
    test_predictions["winner_correct"] = (
        test_predictions["predicted_winner"] == test_predictions["actual_winner"]
    )
    metrics["test_predictions_df"] = test_predictions
    return metrics


def train_and_save(
    raw_games: pd.DataFrame | None = None,
    save_path: Path = cfg.MODEL_FILE,
) -> PredictorBundle:
    """End-to-end training: build features → evaluate → fit on full data → save.

    The FINAL model is fit on ALL historical games — the walk-forward run gave
    us the honest error estimate; discarding data after that would be wasteful.
    """
    if raw_games is None:
        raw_games = pd.read_csv(cfg.RAW_GAMES_CSV)

    features_df = build_features(raw_games)
    metrics = walk_forward_evaluate(features_df)

    bundle = _fit_bundle(features_df)
    bundle.test_predictions = metrics.pop("test_predictions_df", pd.DataFrame())
    bundle.metrics = metrics
    bundle.save(save_path)
    return bundle


# ---------------------------------------------------------------------------
# Metrics formatter (shared by the CLI script and the notebook)
# ---------------------------------------------------------------------------


def _format_metrics(m: dict) -> str:
    """Pretty-print the metrics dict for the CLI, with plain-English notes."""
    if not m.get("n_test"):
        return "  Not enough history for a walk-forward evaluation yet."
    return (
        f"  Rolling walk-forward: {m['n_test']} games predicted out-of-sample\n"
        f"    note: after a {m['n_train']}-game warm-up, the model is refit before\n"
        f"          every game day using ONLY earlier games, then predicts that day.\n"
        f"          Exactly how it's used for real, so these numbers are honest.\n"
        f"\n  Winner (P(home) = Phi(margin / sigma)):\n"
        f"    Accuracy     : {m['accuracy']:.3f}\n"
        f"      -> picks the winner right ~{m['accuracy'] * 100:.0f}% of the time.\n"
        f"         Reference: 'always pick home' = {m['home_win_rate']:.3f} on these games.\n"
        f"    Log loss     : {m['log_loss']:.3f}  (lower is better)\n"
        f"      -> penalizes CONFIDENT wrong predictions extra hard. <0.69 = real signal.\n"
        f"    Brier score  : {m['brier_score']:.3f}  (lower is better; 0.25 = coin flip)\n"
        f"\n  Margin (home_score - away_score):\n"
        f"    MAE          : {m['margin_mae']:.2f} pts\n"
        f"      -> 'home wins by 7' really means 'home wins by 7 +/- {m['margin_mae']:.0f}'.\n"
        f"    RMSE         : {m['margin_rmse']:.2f} pts\n"
        f"    R^2          : {m['margin_r2']:.3f}  (0 = no better than the league average)\n"
        f"\n  Total points (home_score + away_score):\n"
        f"    MAE          : {m['total_mae']:.2f} pts\n"
        f"    RMSE         : {m['total_rmse']:.2f} pts\n"
        f"    R^2          : {m['total_r2']:.3f}\n"
        f"\n  Elo baseline (pure rating system, for comparison):\n"
        f"    Accuracy     : {m['elo_baseline_accuracy']:.3f}\n"
        f"    Log loss     : {m['elo_baseline_log_loss']:.3f}\n"
        f"    Brier score  : {m['elo_baseline_brier']:.3f}\n"
        f"      -> the bar to beat. Accuracy differences of a few points are noise\n"
        f"         on ~120 games (+/- ~4); compare log loss / Brier instead.\n"
    )
