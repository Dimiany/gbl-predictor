"""Model training, evaluation, and persistence.

We train THREE models jointly:
  1. win_clf      — classifier for P(home team wins).
  2. margin_reg   — regressor for (home_score - away_score).
  3. total_reg    — regressor for (home_score + away_score).

From margin + total we derive home_score and away_score:
    home_score = (total + margin) / 2
    away_score = (total - margin) / 2

Predicting margin and total separately (rather than the two scores directly)
gives the regressors cleaner learning signals, because margin and total are
roughly uncorrelated whereas home_score and away_score are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import TimeSeriesSplit

from src import config as cfg
from src.features import build_features

# ---------------------------------------------------------------------------
# Data class for the trained bundle
# ---------------------------------------------------------------------------


@dataclass
class PredictorBundle:
    """All trained artifacts that live together and are saved/loaded together."""

    win_clf: HistGradientBoostingClassifier
    margin_reg: HistGradientBoostingRegressor
    total_reg: HistGradientBoostingRegressor
    feature_cols: list[str]
    # Blend weight for ML probability vs. Elo probability (see config for details).
    ensemble_ml_weight: float
    # Store the training metrics too so predictions can report the expected error bar.
    metrics: dict
    # Predictions on the walk-forward test set, for the "predicted vs actual" view.
    # This is HONEST backtest data — these games are NOT in the model's training set,
    # so comparing predictions here to actuals shows the model's real-world accuracy.
    # Empty on first load of older bundles (before this field existed) — the
    # ``field(default_factory=...)`` keeps them backwards-compatible.
    test_predictions: pd.DataFrame = field(default_factory=pd.DataFrame)

    def save(self, path: Path = cfg.MODEL_FILE) -> None:
        # Create parent directory if missing — avoids the classic
        # "FileNotFoundError on first run" papercut.
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path = cfg.MODEL_FILE) -> PredictorBundle:
        return joblib.load(path)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def _fit_bundle(
    X: pd.DataFrame, y_win: pd.Series, y_margin: pd.Series, y_total: pd.Series
) -> PredictorBundle:
    """Fit the three models on one training split. Internal helper."""
    win_clf = HistGradientBoostingClassifier(**cfg.GBM_PARAMS)
    margin_reg = HistGradientBoostingRegressor(**cfg.GBM_PARAMS)
    total_reg = HistGradientBoostingRegressor(**cfg.GBM_PARAMS)

    win_clf.fit(X, y_win)
    margin_reg.fit(X, y_margin)
    total_reg.fit(X, y_total)

    return PredictorBundle(
        win_clf=win_clf,
        margin_reg=margin_reg,
        total_reg=total_reg,
        feature_cols=list(X.columns),
        ensemble_ml_weight=cfg.ENSEMBLE_ML_WEIGHT_DEFAULT,
        metrics={},  # populated by the walk-forward evaluator
    )


# ---------------------------------------------------------------------------
# Ensemble blending — the key "accuracy win" on small datasets
# ---------------------------------------------------------------------------


def blend_probabilities(p_ml: np.ndarray, p_elo: np.ndarray, w_ml: float) -> np.ndarray:
    """Weighted average of two probability arrays, clipped to [0, 1].

    A weight of 0 means "use Elo only"; 1.0 means "use ML only"; 0.5 is a
    neutral blend. Clipping guards against tiny floating-point drift past
    the [0,1] boundary when both inputs are already at the extremes.
    """
    return np.clip(w_ml * p_ml + (1.0 - w_ml) * p_elo, 0.0, 1.0)


def _tune_blend_weight(
    p_ml: np.ndarray,
    p_elo: np.ndarray,
    y_true: np.ndarray,
) -> float:
    """Pick the ML/Elo blend weight that minimises log-loss on the data given.

    We sweep weights from 0 to 1 in 0.05 steps — small enough to be
    accurate, coarse enough to finish instantly on small data.
    """
    best_weight = cfg.ENSEMBLE_ML_WEIGHT_DEFAULT
    best_loss = float("inf")
    for w in np.arange(0.0, 1.01, 0.05):
        blended = blend_probabilities(p_ml, p_elo, float(w))
        try:
            loss = log_loss(y_true, blended, labels=[0, 1])
        except ValueError:
            # Can happen if all y_true are the same class — skip that weight.
            continue
        if loss < best_loss:
            best_loss = loss
            best_weight = float(w)
    return best_weight


def walk_forward_evaluate(features_df: pd.DataFrame) -> dict:
    """Train on the first TRAIN_FRACTION of games (by date), test on the rest.

    This is the HONEST way to evaluate a time-series predictor. Random
    train/test splits (what scikit-learn does by default) leak information
    from the future into the training set: you could end up training on a
    March game and testing on a February one. Walk-forward mimics how the
    model is actually used — you only ever know the past.
    """
    # Games are already sorted by date inside build_features, but re-sort
    # defensively in case a caller passes an unsorted frame.
    features_df = features_df.sort_values(cfg.COL_DATE, kind="stable").reset_index(drop=True)

    split_idx = int(len(features_df) * cfg.TRAIN_FRACTION)
    train = features_df.iloc[:split_idx]
    test = features_df.iloc[split_idx:]

    X_train = train[cfg.FEATURE_COLS]
    X_test = test[cfg.FEATURE_COLS]

    bundle = _fit_bundle(
        X_train,
        train[cfg.TARGET_CLASSIFICATION],
        train[cfg.TARGET_MARGIN],
        train[cfg.TARGET_TOTAL],
    )

    # --- Classification metrics --------------------------------------------
    # predict_proba[:, 1] = probability of the POSITIVE class (home win).
    win_probs = bundle.win_clf.predict_proba(X_test)[:, 1]
    win_preds = (win_probs >= 0.5).astype(int)
    y_win_test = test[cfg.TARGET_CLASSIFICATION]

    # Brier score = mean squared error on probabilities. Lower = better-calibrated.
    # For reference: always predicting 0.5 gives Brier = 0.25.
    # Log loss penalizes confident-and-wrong predictions heavily.
    cls_metrics = {
        "accuracy": accuracy_score(y_win_test, win_preds),
        "log_loss": log_loss(y_win_test, win_probs, labels=[0, 1]),
        "brier_score": brier_score_loss(y_win_test, win_probs),
    }

    # --- Ensemble: tune ML/Elo blend weight on the TRAINING set -------------
    # We re-predict the training set out-of-fold using time-series CV so the
    # tuned weight isn't biased by overfitting on the train set's in-sample
    # predictions. Then we evaluate the chosen blend on the (untouched) test set.
    tscv = TimeSeriesSplit(n_splits=5)
    oof_ml = np.full(len(X_train), np.nan)  # out-of-fold predictions
    for fold_train_idx, fold_val_idx in tscv.split(X_train):
        fold_model = HistGradientBoostingClassifier(**cfg.GBM_PARAMS)
        fold_model.fit(
            X_train.iloc[fold_train_idx],
            train[cfg.TARGET_CLASSIFICATION].iloc[fold_train_idx],
        )
        oof_ml[fold_val_idx] = fold_model.predict_proba(X_train.iloc[fold_val_idx])[:, 1]
    # Only use rows that actually got an OOF prediction (first fold's train data won't).
    valid = ~np.isnan(oof_ml)
    oof_elo = X_train["home_win_prob_elo"].to_numpy()[valid]
    oof_y = train[cfg.TARGET_CLASSIFICATION].to_numpy()[valid]
    tuned_weight = _tune_blend_weight(oof_ml[valid], oof_elo, oof_y)

    # Apply the tuned blend to the held-out test set.
    elo_prob_test = X_test["home_win_prob_elo"].to_numpy()
    blended_probs = blend_probabilities(win_probs, elo_prob_test, tuned_weight)
    blended_preds = (blended_probs >= 0.5).astype(int)
    ensemble_metrics = {
        "ensemble_ml_weight": tuned_weight,
        "ensemble_accuracy": accuracy_score(y_win_test, blended_preds),
        "ensemble_log_loss": log_loss(y_win_test, blended_probs, labels=[0, 1]),
        "ensemble_brier": brier_score_loss(y_win_test, blended_probs),
    }

    # --- Regression metrics ------------------------------------------------
    margin_preds = bundle.margin_reg.predict(X_test)
    total_preds = bundle.total_reg.predict(X_test)

    # MAE (mean absolute error) is more intuitive than RMSE for the user:
    # "our margin predictions are off by ~X points on average."
    reg_metrics = {
        "margin_mae": mean_absolute_error(test[cfg.TARGET_MARGIN], margin_preds),
        "margin_rmse": float(np.sqrt(mean_squared_error(test[cfg.TARGET_MARGIN], margin_preds))),
        "margin_r2": r2_score(test[cfg.TARGET_MARGIN], margin_preds),
        "total_mae": mean_absolute_error(test[cfg.TARGET_TOTAL], total_preds),
        "total_rmse": float(np.sqrt(mean_squared_error(test[cfg.TARGET_TOTAL], total_preds))),
        "total_r2": r2_score(test[cfg.TARGET_TOTAL], total_preds),
    }

    # --- Baseline: Elo alone -----------------------------------------------
    # Sanity check: does the ML model actually beat "use Elo's implied
    # probability"? If it doesn't, the extra features aren't pulling weight.
    elo_prob = test["home_win_prob_elo"].to_numpy()
    elo_pred = (elo_prob >= 0.5).astype(int)
    baseline_metrics = {
        "elo_baseline_accuracy": accuracy_score(y_win_test, elo_pred),
        "elo_baseline_log_loss": log_loss(y_win_test, elo_prob, labels=[0, 1]),
        "elo_baseline_brier": brier_score_loss(y_win_test, elo_prob),
    }

    # ----------------------------------------------------------------------
    # Build the per-game "predicted vs actual" DataFrame for the test set.
    # This is what powers the backtest view. Every row is one held-out game
    # the model never saw during training — so the predictions here are a
    # faithful measure of out-of-sample accuracy.
    # ----------------------------------------------------------------------
    pred_home_scores = (total_preds + margin_preds) / 2.0
    pred_away_scores = (total_preds - margin_preds) / 2.0
    test_predictions = pd.DataFrame(
        {
            cfg.COL_DATE: test[cfg.COL_DATE].values,
            cfg.COL_HOME: test[cfg.COL_HOME].values,
            cfg.COL_AWAY: test[cfg.COL_AWAY].values,
            # Actuals (what really happened) — copied straight from the history.
            "actual_home_score": test[cfg.COL_HOME_SCORE].values,
            "actual_away_score": test[cfg.COL_AWAY_SCORE].values,
            "actual_winner": np.where(
                test[cfg.COL_HOME_SCORE].values > test[cfg.COL_AWAY_SCORE].values,
                test[cfg.COL_HOME].values,
                test[cfg.COL_AWAY].values,
            ),
            # Predicted values. We round at DISPLAY time, not here — keeping the
            # raw floats lets callers show finer-grained error analysis.
            "predicted_home_score": pred_home_scores,
            "predicted_away_score": pred_away_scores,
            "home_win_probability": blended_probs,
            "predicted_winner": np.where(
                pred_home_scores > pred_away_scores,
                test[cfg.COL_HOME].values,
                test[cfg.COL_AWAY].values,
            ),
        }
    )
    # Mark whether each pick was right. Useful for quick mental math — the
    # user can scan the column and see how often the model wins.
    test_predictions["winner_correct"] = (
        test_predictions["predicted_winner"] == test_predictions["actual_winner"]
    )

    metrics = {
        "n_train": len(train),
        "n_test": len(test),
        **cls_metrics,
        **reg_metrics,
        **baseline_metrics,
        **ensemble_metrics,
    }
    # Attach the test predictions alongside metrics. ``walk_forward_evaluate``
    # historically returned only a dict; callers now check for this key.
    metrics["test_predictions_df"] = test_predictions
    return metrics


def train_and_save(
    raw_games: pd.DataFrame | None = None,
    save_path: Path = cfg.MODEL_FILE,
) -> PredictorBundle:
    """End-to-end training: build features → evaluate → fit on full data → save.

    We fit the FINAL model on ALL historical games (not just the training
    split) — the walk-forward run gave us the honest error estimate, and
    discarding 20% of the data after that would be wasteful.
    """
    if raw_games is None:
        raw_games = pd.read_csv(cfg.RAW_GAMES_CSV)

    features_df = build_features(raw_games)

    # Get honest test-set metrics first…
    metrics = walk_forward_evaluate(features_df)

    # …then refit on everything for deployment.
    X_full = features_df[cfg.FEATURE_COLS]
    bundle = _fit_bundle(
        X_full,
        features_df[cfg.TARGET_CLASSIFICATION],
        features_df[cfg.TARGET_MARGIN],
        features_df[cfg.TARGET_TOTAL],
    )
    # Extract the test-predictions DataFrame before stuffing metrics on the
    # bundle — it's kept as a separate attribute so serialization stays
    # predictable (a DataFrame hidden inside a dict-of-floats metric is a
    # nasty surprise for anyone else reading the code).
    test_predictions_df = metrics.pop("test_predictions_df", pd.DataFrame())
    bundle.metrics = metrics
    bundle.test_predictions = test_predictions_df
    # Carry the walk-forward-tuned blend weight into the deployed model, so
    # predictions use the weight that actually scored best on held-out data.
    bundle.ensemble_ml_weight = float(
        metrics.get("ensemble_ml_weight", cfg.ENSEMBLE_ML_WEIGHT_DEFAULT)
    )
    bundle.save(save_path)
    return bundle


# ---------------------------------------------------------------------------
# Metrics formatter (shared by the CLI script and the notebook)
# ---------------------------------------------------------------------------


def _format_metrics(m: dict) -> str:
    """Pretty-print the metrics dict for the CLI.

    Output is annotated with plain-English notes so a non-ML reader can make
    sense of each number. The notes are deliberately conservative — pointing
    out the comparison points (coin flip, always-pick-home, etc.) rather than
    making absolute "good/bad" claims that depend on the sport and dataset.
    """
    ml_w = m["ensemble_ml_weight"]
    elo_w = 1 - ml_w
    return (
        f"  Train / test games: {m['n_train']} / {m['n_test']}\n"
        f"    note: we train on the oldest {m['n_train']} games and TEST on the\n"
        f"          most recent {m['n_test']}. The model never sees the test games\n"
        f"          during training, so the metrics below are a fair estimate of\n"
        f"          how well it would do on truly unseen future games.\n"
        f"\n  Win classifier (does it pick the right winner?):\n"
        f"    Accuracy     : {m['accuracy']:.3f}\n"
        f"      -> picks the winner right ~{m['accuracy'] * 100:.0f}% of the time.\n"
        f"         Reference points: 0.50 = coin flip, ~0.60 = 'always pick home team'.\n"
        f"    Log loss     : {m['log_loss']:.3f}  (lower is better)\n"
        f"      -> penalizes CONFIDENT wrong predictions extra hard.\n"
        f"         <0.69 means the probabilities carry real signal; <0.50 is genuinely good.\n"
        f"    Brier score  : {m['brier_score']:.3f}  (lower is better)\n"
        f"      -> mean squared error on the predicted probabilities.\n"
        f"         0.25 = always guessing 50/50; below that = the probabilities are informative.\n"
        f"\n  Margin regressor (home_score - away_score):\n"
        f"    MAE          : {m['margin_mae']:.2f} pts\n"
        f"      -> on average, the predicted margin is off by ~{m['margin_mae']:.0f} points.\n"
        f"         So 'home wins by 7' really means 'home wins by 7 +/- {m['margin_mae']:.0f}'.\n"
        f"    RMSE         : {m['margin_rmse']:.2f} pts\n"
        f"      -> like MAE but squares the errors first, so big misses count more.\n"
        f"         The gap RMSE - MAE shows how often the model has BIG misses.\n"
        f"    R^2          : {m['margin_r2']:.3f}\n"
        f"      -> fraction of margin variation the model explains. 1.0 = perfect,\n"
        f"         0 = no better than always guessing the league average margin,\n"
        f"         <0 = WORSE than that. Basketball margin is genuinely hard; Vegas ~0.15.\n"
        f"\n  Total regressor (home_score + away_score):\n"
        f"    MAE          : {m['total_mae']:.2f} pts\n"
        f"      -> predicted TOTAL points typically off by ~{m['total_mae']:.0f}.\n"
        f"    RMSE         : {m['total_rmse']:.2f} pts\n"
        f"    R^2          : {m['total_r2']:.3f}\n"
        f"      -> totals are usually easier to predict than margins (no sign-flipping).\n"
        f"\n  Elo baseline (for comparison — pure rating system, no ML at all):\n"
        f"    Accuracy     : {m['elo_baseline_accuracy']:.3f}\n"
        f"    Log loss     : {m['elo_baseline_log_loss']:.3f}\n"
        f"    Brier score  : {m['elo_baseline_brier']:.3f}\n"
        f"      -> this is the bar to beat. If ML alone can't top Elo, the extra\n"
        f"         complexity isn't earning its keep — that's exactly when the\n"
        f"         ENSEMBLE below saves us by leaning more on Elo.\n"
        f"\n  Ensemble (ML * {ml_w:.2f} + Elo * {elo_w:.2f}):\n"
        f"    Accuracy     : {m['ensemble_accuracy']:.3f}\n"
        f"    Log loss     : {m['ensemble_log_loss']:.3f}\n"
        f"    Brier score  : {m['ensemble_brier']:.3f}\n"
        f"      -> we blend ML and Elo probabilities and the auto-tuner picked\n"
        f"         the weights ({ml_w:.0%} ML / {elo_w:.0%} Elo) by minimising log-loss\n"
        f"         on training data via time-series cross-validation. A weight\n"
        f"         heavily tilted toward Elo means Elo is doing most of the work\n"
        f"         on this dataset — common when training history is small.\n"
    )
