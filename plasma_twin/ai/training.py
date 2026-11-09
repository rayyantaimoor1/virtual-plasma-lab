"""Training and evaluation framework with baselines: Phase 9 (FR16.2, FR16.3, FR17.19, AIQ-1, AIQ-2).

RULES (BUILD_STEPS.md, Phase 9, fixed before this code):
- Every model is trained together with its baseline on twin data only, and both are evaluated on the
  random AND the region split; both results are always reported.
- Baselines: ridge regression on log line ratios (each line over the strongest) for T_e and n_e; a
  range check for anomalies (flag a run if any feature is outside the training range).
- Metrics: MAE, median relative error and R2 for regression; recall and false-alarm rate for
  anomalies. Model against baseline: a paired bootstrap of absolute errors (seeded, 2,000 resamples).
- Results are reported as they come; nothing is tuned on the test set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from plasma_twin.ai import datasets
from plasma_twin.ai.registry import ModelCard, Registry, make_card, new_model_id

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261108
TASKS = {
    "spectrum_to_plasma": "Stage 1: spectrum -> T_e, n_e, T_gas with 90 % intervals (Phase 10, M12)",
    "spectrum_to_te_ne": "Stage 1: OES line areas -> T_e and n_e (Phase 9 framework check)",
    "anomaly_residual": "Stage 1: is a run faulty? Physics residuals + Isolation Forest (Phase 12, M13)",
    "anomaly_range_check": "Stage 1: is a run faulty? (range-check baseline)",
    "surrogate_stage1": "Stage 1 surrogate: power, pressure, flow, mixture -> T_e, n_e, T_gas, lines (Phase 11, M15)",
    "surrogate_stage2": "Stage 2 surrogate: pulse, gas, water, time -> species, log reduction (Phase 11, M15)",
}
ALGORITHMS = {"spectrum_to_plasma": ("random_forest", "xgboost"), "spectrum_to_te_ne": ("ridge", "xgboost"),
              "anomaly_residual": ("isolation_forest",), "anomaly_range_check": ("range_check",), "surrogate_stage1": ("xgboost", "random_forest"),
              "surrogate_stage2": ("xgboost", "random_forest")}


# ------------------------------------------------------------------------------------ features
def line_columns(frame: pd.DataFrame) -> list[str]:
    """The line-area columns of a dataset, in wavelength order."""
    return sorted((c for c in frame.columns if c.startswith("line_")), key=lambda c: float(c[5:]))


def ratio_features(areas: np.ndarray) -> np.ndarray:
    """log10(each line area / the run's strongest line area); areas at or below zero (noise) are floored.
    Ratios need no absolute calibration, and the logarithm keeps weak and strong lines on one scale."""
    areas = np.atleast_2d(np.asarray(areas, dtype=float))
    strongest = areas.max(axis=1, keepdims=True)
    return np.log10(np.clip(areas, 1e-6 * strongest, None) / strongest)


def log_line_ratios(frame: pd.DataFrame) -> np.ndarray:
    """The line-ratio features of every row of a dataset (columns in wavelength order)."""
    return ratio_features(frame[line_columns(frame)].to_numpy(dtype=float))


def anomaly_features(frame: pd.DataFrame) -> np.ndarray:
    """Line ratios and the probe curve scaled by its own largest current: shape, not size."""
    iv = frame[[c for c in frame.columns if c.startswith("iv_")]].to_numpy(dtype=float)
    return np.hstack([log_line_ratios(frame), iv / np.abs(iv).max(axis=1, keepdims=True)])


def targets(frame: pd.DataFrame) -> np.ndarray:
    """T_e (eV) and log10 n_e: n_e spans an order of magnitude, so it is learned on a log scale."""
    return np.column_stack([frame["te_ev"].to_numpy(), np.log10(frame["ne_m3"].to_numpy())])


# ------------------------------------------------------------------------------------ metrics
def regression_metrics(true: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """MAE, RMSE, R2 and median relative error: the regression metrics fixed in the Phase 9 rules."""
    error = predicted - true
    total = np.sum((true - true.mean()) ** 2)
    return {"mae": float(np.mean(np.abs(error))), "median_relative_error": float(np.median(np.abs(error) / np.abs(true))),
            "r2": float(1 - np.sum(error**2) / total) if total > 0 else float("nan")}


def paired_bootstrap_p(model_abs_error: np.ndarray, baseline_abs_error: np.ndarray, resamples: int = BOOTSTRAP_RESAMPLES,
                       seed: int = BOOTSTRAP_SEED) -> float:
    """One-sided p-value that the model is NOT better: share of resampled mean differences >= 0."""
    difference = model_abs_error - baseline_abs_error
    rng = np.random.default_rng(seed)
    means = difference[rng.integers(0, len(difference), size=(resamples, len(difference)))].mean(axis=1)
    return float((np.sum(means >= 0) + 1) / (resamples + 1))


def detection_metrics(is_fault: np.ndarray, flagged: np.ndarray) -> dict[str, float]:
    """Recall on faulty rows and false-alarm rate on clean rows (AIQ-2)."""
    faults, clean = is_fault.astype(bool), ~is_fault.astype(bool)
    return {"recall": float(flagged[faults].mean()) if faults.any() else float("nan"),
            "false_alarm_rate": float(flagged[clean].mean()) if clean.any() else float("nan")}


# ------------------------------------------------------------------------------------ models
class RangeCheck:
    """The anomaly baseline: flag a run if any feature lies outside the range seen in clean training runs."""

    def fit(self, features: np.ndarray) -> "RangeCheck":
        """Learn each feature's minimum and maximum on clean training data (the baseline detector)."""
        self.low, self.high = features.min(axis=0), features.max(axis=0)
        return self

    def flag(self, features: np.ndarray) -> np.ndarray:
        """Flag rows with any feature outside the learned range."""
        return np.any((features < self.low) | (features > self.high), axis=1)


@dataclass
class TwoTargetRegressor:
    """One fitted regressor per target column (T_e, log10 n_e)."""
    models: list[Any]

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict each target with its own model, one column per target."""
        return np.column_stack([m.predict(features) for m in self.models])


def _ridge():
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-4, 3, 15)))


def _xgboost(seed: int):
    from xgboost import XGBRegressor
    return XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9,
                        random_state=seed, n_jobs=1)


XGBOOST_PARAMETERS = {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.9, "colsample_bytree": 0.9}


def fit_regressor(algorithm: str, features: np.ndarray, target: np.ndarray, seed: int) -> TwoTargetRegressor:
    """Train one model per target with the fixed Phase 9 hyperparameters."""
    make = _ridge if algorithm == "ridge" else (lambda: _xgboost(seed))
    return TwoTargetRegressor([make().fit(features, target[:, k]) for k in range(target.shape[1])])


# ------------------------------------------------------------------------------------ training
def train(task: str, algorithm: str, frame: pd.DataFrame, card: datasets.DatasetCard, registry: Registry | None = None,
          seed: int = BOOTSTRAP_SEED) -> ModelCard:
    """FR16.2: train a model and its baseline, evaluate both on both splits, log and register (E23)."""
    if algorithm not in ALGORITHMS.get(task, ()):
        raise ValueError(f"algorithm {algorithm!r} is not offered for task {task!r}")
    if task == "spectrum_to_plasma":  # Phase 10: conformal intervals, range check and the physics comparison
        from plasma_twin.ai import inference
        return inference.train(algorithm, frame, card, registry)
    if task == "anomaly_residual":  # Phase 12: residuals against the twin's expectation
        from plasma_twin.ai import anomaly
        return anomaly.train(frame, card, registry)
    if task.startswith("surrogate_stage"):  # Phase 11: learns the twin's noise-free outputs, not this frame
        from plasma_twin.ai import surrogate
        return surrogate.train(int(task[-1]), algorithm, registry)
    registry = registry or Registry()
    metrics: dict[str, Any] = {}
    predictions: dict[str, Any] = {}
    notes: list[str] = []
    if task == "spectrum_to_te_ne":
        clean = frame[frame["fault"] == "none"].reset_index(drop=True)
        x, y = log_line_ratios(clean), targets(clean)
        for kind in ("random", "region"):
            train_rows, test_rows = datasets.split(clean, 1, kind)
            if len(test_rows) == 0 or len(train_rows) < 5:
                metrics[kind] = {"note": "not enough rows for this split"}
                continue
            baseline = fit_regressor("ridge", x[train_rows], y[train_rows], seed)
            model = baseline if algorithm == "ridge" else fit_regressor(algorithm, x[train_rows], y[train_rows], seed)
            result: dict[str, Any] = {"test_rows": int(len(test_rows))}
            predictions[kind] = {"te_twin": y[test_rows, 0].tolist(), "ne_twin": (10 ** y[test_rows, 1]).tolist()}
            for who, fitted in (("model", model), ("baseline", baseline)):
                predicted = fitted.predict(x[test_rows])
                truth = y[test_rows]
                predictions[kind][f"te_{who}"] = predicted[:, 0].tolist()
                predictions[kind][f"ne_{who}"] = (10 ** predicted[:, 1]).tolist()
                te, ne = regression_metrics(truth[:, 0], predicted[:, 0]), regression_metrics(10 ** truth[:, 1], 10 ** predicted[:, 1])
                result[who] = {**{f"te_{k}": v for k, v in te.items()}, **{f"ne_{k}": v for k, v in ne.items()}}
                result[f"{who}_abs_error"] = np.abs(predicted[:, 0] - truth[:, 0])
            model_error, baseline_error = result.pop("model_abs_error"), result.pop("baseline_abs_error")
            result["p_value"] = paired_bootstrap_p(model_error, baseline_error) if algorithm != "ridge" else None
            metrics[kind] = result
        final = fit_regressor(algorithm, x, y, seed)  # the registered model learns from every clean row
        features = line_columns(clean)
        names = ["te_ev", "log10_ne_m3"]
        hyper = {"alphas": "logspace(-4, 3, 15), chosen by RidgeCV"} if algorithm == "ridge" else XGBOOST_PARAMETERS
        notes.append("the p-value compares T_e absolute errors with the ridge baseline (paired bootstrap)")
    else:  # anomaly_range_check
        x = anomaly_features(frame)
        is_fault = (frame["fault"] != "none").to_numpy()
        for kind in ("random", "region"):
            train_rows, test_rows = datasets.split(frame, 1, kind)
            fit_rows = train_rows[~is_fault[train_rows]]  # the range is learned from clean runs only
            if len(test_rows) == 0 or len(fit_rows) < 5:
                metrics[kind] = {"note": "not enough rows for this split"}
                continue
            check = RangeCheck().fit(x[fit_rows])
            result = {"test_rows": int(len(test_rows)), "model": detection_metrics(is_fault[test_rows], check.flag(x[test_rows]))}
            result["baseline"] = result["model"]  # the range check is its own baseline
            metrics[kind] = result
        final = RangeCheck().fit(x[~is_fault])
        features, names, hyper = ["log line ratios", "scaled probe curve"], ["fault"], {}
    model_id = new_model_id(task)
    model_card = make_card(model_id, task, algorithm, card.dataset_id, seed, hyper, features, names, metrics, notes)
    return registry.register(model_card, final, predictions)
