"""Spectrum -> T_e, n_e and T_gas with 90 % conformal intervals: Phase 10 (Core Module 2.1, M12, AIQ-1, AIQ-3).

RULES (BUILD_STEPS.md, Phase 10, fixed 5 November 2026 before this code):
- Data: the locked Stage 1 dataset, clean runs only. Features: log10(area / strongest area) of the 20
  CR-model Ar I lines in 690-860 nm, measured exactly as on M5 (the ridge baseline's features). Line
  areas, not a resampled spectrum: an area does not change when the instrument broadens a line, so
  a model trained on 0.005 nm spectra can read a measured spectrum taken at another width.
- Targets: T_e (eV), log10 n_e and T_gas (K), one regressor each: Random Forest (500 trees) or XGBoost
  (the Phase 9 parameters). Hyperparameters fixed in advance, never tuned on a test set.
- Intervals: MAPIE split conformal (absolute residual, 90 %). The training rows are divided 75/25
  (seed 20261109): the model learns from the first part, the interval width from the second.
- Range check: an estimate is withheld if a line cannot be measured or any feature lies outside
  [min - 0.1 w, max + 0.1 w] of the fitting rows (w = max - min). Metrics use all held-out rows.
- T_gas: withheld on M12 unless it beats the training-mean baseline on the random split (p < 0.05).
- Comparisons on both splits with the ridge baseline and the Phase 4 physics line-ratio fit
  (paired bootstrap p-value; scipy.stats.bootstrap 95 % interval of the mean error difference).
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from plasma_twin.ai import datasets
from plasma_twin.ai.registry import ModelCard, Registry, make_card, new_model_id
from plasma_twin.ai.training import (BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, XGBOOST_PARAMETERS, fit_regressor, line_columns,
                                     log_line_ratios, paired_bootstrap_p, ratio_features, regression_metrics)

if TYPE_CHECKING:  # used in annotations only (MNT-3): nothing extra is imported at run time
    from plasma_twin.oes.spectrum import Spectrum

TASK = "spectrum_to_plasma"
ALGORITHMS = ("random_forest", "xgboost")
CONFIDENCE = 0.90
CALIBRATION_FRACTION = 0.25
CALIBRATION_SEED = 20261109
RANGE_MARGIN = 0.10
SIGNIFICANCE = 0.05
RF_PARAMETERS = {"n_estimators": 500}
TARGETS = ("te_ev", "log10_ne_m3", "tgas_k")
CONFIG_KEYS = ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture", "n2_percent", "o2_percent")


# ------------------------------------------------------------------------------------ targets and models
def targets(frame: pd.DataFrame) -> np.ndarray:
    """T_e (eV), log10 n_e (n_e spans an order of magnitude) and T_gas (K)."""
    return np.column_stack([frame["te_ev"].to_numpy(), np.log10(frame["ne_m3"].to_numpy()), frame["tgas_k"].to_numpy()])


def _regressor(algorithm: str, seed: int):
    if algorithm == "random_forest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(**RF_PARAMETERS, random_state=seed, n_jobs=-1)
    if algorithm == "xgboost":
        from xgboost import XGBRegressor
        return XGBRegressor(**XGBOOST_PARAMETERS, random_state=seed, n_jobs=1)
    raise ValueError(f"unknown algorithm {algorithm!r}")


def calibration_split(n: int) -> tuple[np.ndarray, np.ndarray]:
    """(fitting, calibration) positions inside a training set: seeded 75/25."""
    order = np.random.default_rng(CALIBRATION_SEED).permutation(n)
    cut = int(round(n * (1 - CALIBRATION_FRACTION)))
    return np.sort(order[:cut]), np.sort(order[cut:])


@dataclass
class ConformalModel:
    """One conformalised regressor per target, the training range of the features, and the line list."""
    algorithm: str
    regressors: list[Any]          # MAPIE SplitConformalRegressor, one per target
    feature_low: np.ndarray
    feature_high: np.ndarray
    wavelengths_nm: list[float]
    tgas_informative: bool = False

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(point, lower, upper), each of shape (rows, 3) in the target units (log10 for n_e)."""
        points, lows, highs = [], [], []
        for regressor in self.regressors:
            point, interval = regressor.predict_interval(features)
            points.append(point)
            lows.append(interval[:, 0, 0])
            highs.append(interval[:, 1, 0])
        return np.column_stack(points), np.column_stack(lows), np.column_stack(highs)

    def out_of_range(self, features: np.ndarray) -> np.ndarray:
        """True for each row with a feature outside the training range widened by the margin."""
        width = self.feature_high - self.feature_low
        low, high = self.feature_low - RANGE_MARGIN * width, self.feature_high + RANGE_MARGIN * width
        return np.any((features < low) | (features > high), axis=1)


def fit_conformal(algorithm: str, features: np.ndarray, target: np.ndarray, wavelengths_nm: list[float],
                  seed: int = BOOTSTRAP_SEED) -> ConformalModel:
    """Fit on 75 % of the rows, then conformalise the 90 % interval on the other 25 %."""
    from mapie.regression import SplitConformalRegressor
    fit_rows, calibration_rows = calibration_split(len(features))
    regressors = []
    for k in range(target.shape[1]):
        model = _regressor(algorithm, seed).fit(features[fit_rows], target[fit_rows, k])
        conformal = SplitConformalRegressor(model, confidence_level=CONFIDENCE, conformity_score="absolute", prefit=True)
        regressors.append(conformal.conformalize(features[calibration_rows], target[calibration_rows, k]))
    return ConformalModel(algorithm, regressors, features[fit_rows].min(axis=0), features[fit_rows].max(axis=0), list(wavelengths_nm))


# ------------------------------------------------------------------------------------ comparison statistics
def bootstrap_interval(model_abs_error: np.ndarray, other_abs_error: np.ndarray) -> tuple[float, float]:
    """95 % interval of mean(model error - other error) by scipy.stats.bootstrap (paired); below 0 = model better."""
    from scipy.stats import bootstrap
    if len(model_abs_error) < 3:
        return float("nan"), float("nan")
    difference = np.asarray(model_abs_error) - np.asarray(other_abs_error)
    if np.ptp(difference) == 0:  # identical errors: no spread to resample (BCa would return NaN)
        return float(difference[0]), float(difference[0])
    found = bootstrap((model_abs_error, other_abs_error), lambda a, b, axis: np.mean(a - b, axis=axis), paired=True,
                      vectorized=True, n_resamples=BOOTSTRAP_RESAMPLES, confidence_level=0.95,
                      rng=np.random.default_rng(BOOTSTRAP_SEED))
    return float(found.confidence_interval.low), float(found.confidence_interval.high)


def _compare(result: dict[str, Any], name: str, model_error: np.ndarray, other_error: np.ndarray) -> None:
    result[f"p_value_{name}"] = paired_bootstrap_p(model_error, other_error)
    result[f"ci_{name}_low"], result[f"ci_{name}_high"] = bootstrap_interval(model_error, other_error)


# ------------------------------------------------------------------------------------ physics line-ratio fit
def _physics_row(row: dict[str, Any]) -> dict[str, float]:
    """The Phase 4 line-ratio fit on one row's line areas, given its known gas, EEDF and geometry."""
    from plasma_twin.oes.boltzmann import LinePoint
    from plasma_twin.oes.line_ratio import fit_spectrum_points
    from plasma_twin.services import stage1
    from plasma_twin.stage1.global_model import solve
    s1 = datasets.load_settings()["stage1"]
    config = {**stage1.default_config(), **{k: row[k] for k in CONFIG_KEYS}, "eedf": s1["eedf"], "spatial": s1["spatial"]}
    known = solve(stage1.to_inputs(config))  # only the gas density, T_gas, EEDF, geometry and quenching are used
    wavelength = {f"line_{w:.3f}": w for w in datasets.stage1_line_wavelengths()}
    points = [LinePoint(wavelength[c], float(row[c]), 0, 0.0, 0.0) for c in wavelength if row[c] > 0]
    try:
        found = fit_spectrum_points(points, known)
        return {"index": row["index"], "te_physics": found.te_ev if found.success else np.nan,
                "ne_physics": found.ne_m3 if found.success else np.nan}
    except ValueError:
        return {"index": row["index"], "te_physics": np.nan, "ne_physics": np.nan}


def held_out_indices(clean: pd.DataFrame) -> np.ndarray:
    """Dataset indices of the clean held-out rows of both splits (where the physics fit is needed)."""
    rows = np.union1d(datasets.split(clean, 1, "random")[1], datasets.split(clean, 1, "region")[1])
    return clean["index"].to_numpy()[rows]


def physics_estimates(frame: pd.DataFrame, card: datasets.DatasetCard, workers: int = 6, cache: bool = True) -> pd.DataFrame:
    """Physics line-ratio T_e and n_e for the clean held-out rows, cached next to the dataset (about 2 s per row)."""
    path = datasets.data_dir() / f"{card.dataset_id}-physics.parquet"
    clean = frame[frame["fault"] == "none"].reset_index(drop=True)
    wanted = held_out_indices(clean)
    if cache and path.exists():
        cached = pd.read_parquet(path)
        if set(wanted) <= set(cached["index"]):
            return cached
    jobs = [row for row in clean.to_dict("records") if row["index"] in set(wanted)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            out = list(pool.map(_physics_row, jobs, chunksize=2))
    else:
        out = [_physics_row(job) for job in jobs]
    table = pd.DataFrame(out, columns=["index", "te_physics", "ne_physics"])
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)
    return table


# ------------------------------------------------------------------------------------ training and evaluation
def _evaluate(model: ConformalModel, baseline, x: np.ndarray, y: np.ndarray, physics: pd.DataFrame | None,
              indices: np.ndarray, train_mean_tgas: float) -> tuple[dict[str, Any], dict[str, Any]]:
    point, low, high = model.predict(x)
    base = baseline.predict(x)
    te, ne, tgas = y[:, 0], 10 ** y[:, 1], y[:, 2]
    result: dict[str, Any] = {"test_rows": int(len(y))}
    model_metrics = {**{f"te_{k}": v for k, v in regression_metrics(te, point[:, 0]).items()},
                     **{f"ne_{k}": v for k, v in regression_metrics(ne, 10 ** point[:, 1]).items()},
                     **{f"tgas_{k}": v for k, v in regression_metrics(tgas, point[:, 2]).items()}}
    inside = (y >= low) & (y <= high)
    model_metrics.update({"te_coverage": float(inside[:, 0].mean()), "ne_coverage": float(inside[:, 1].mean()),
                          "tgas_coverage": float(inside[:, 2].mean()),
                          "te_interval_median_width_ev": float(np.median(high[:, 0] - low[:, 0])),
                          "ne_interval_median_factor": float(np.median(10 ** ((high[:, 1] - low[:, 1]) / 2))),
                          "tgas_interval_median_width_k": float(np.median(high[:, 2] - low[:, 2])),
                          "withheld_share": float(model.out_of_range(x).mean())})
    result["model"] = model_metrics
    result["baseline"] = {**{f"te_{k}": v for k, v in regression_metrics(te, base[:, 0]).items()},
                          **{f"ne_{k}": v for k, v in regression_metrics(ne, 10 ** base[:, 1]).items()}}
    te_error, ne_error = np.abs(point[:, 0] - y[:, 0]), np.abs(point[:, 1] - y[:, 1])
    _compare(result, "te_vs_ridge", te_error, np.abs(base[:, 0] - y[:, 0]))
    _compare(result, "ne_vs_ridge", ne_error, np.abs(base[:, 1] - y[:, 1]))
    result["p_value"] = result["p_value_te_vs_ridge"]  # the headline p-value M16 shows (T_e against the ridge)
    _compare(result, "tgas_vs_mean", np.abs(point[:, 2] - y[:, 2]), np.abs(train_mean_tgas - y[:, 2]))
    predictions = {"te_twin": te.tolist(), "ne_twin": ne.tolist(), "tgas_twin": tgas.tolist(),
                   "te_model": point[:, 0].tolist(), "ne_model": (10 ** point[:, 1]).tolist(), "tgas_model": point[:, 2].tolist(),
                   "te_low": low[:, 0].tolist(), "te_high": high[:, 0].tolist(),
                   "ne_low": (10 ** low[:, 1]).tolist(), "ne_high": (10 ** high[:, 1]).tolist(),
                   "te_baseline": base[:, 0].tolist(), "ne_baseline": (10 ** base[:, 1]).tolist()}
    if physics is not None:
        found = physics.set_index("index").reindex(indices)
        ok = found["te_physics"].notna().to_numpy()
        predictions["te_physics"] = found["te_physics"].tolist()
        predictions["ne_physics"] = found["ne_physics"].tolist()
        if ok.sum() >= 3:
            p_te, p_ne = found["te_physics"].to_numpy()[ok], found["ne_physics"].to_numpy()[ok]
            result["physics"] = {**{f"te_{k}": v for k, v in regression_metrics(te[ok], p_te).items()},
                                 **{f"ne_{k}": v for k, v in regression_metrics(ne[ok], p_ne).items()},
                                 "rows": int(ok.sum()), "failed_fits": int((~ok).sum())}
            _compare(result, "te_vs_physics", te_error[ok], np.abs(p_te - te[ok]))
            _compare(result, "ne_vs_physics", ne_error[ok], np.abs(np.log10(p_ne) - y[ok, 1]))
    return result, predictions


def train(algorithm: str, frame: pd.DataFrame, card: datasets.DatasetCard, registry: Registry | None = None,
          seed: int = BOOTSTRAP_SEED, physics_workers: int = 6, with_physics: bool = True) -> ModelCard:
    """Train, conformalise and evaluate on both splits against the ridge and the physics fit; register (FR16.2)."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"algorithm {algorithm!r} is not offered for {TASK}")
    registry = registry or Registry()
    clean = frame[frame["fault"] == "none"].reset_index(drop=True)
    columns = line_columns(clean)
    wavelengths = [float(c[5:]) for c in columns]
    x, y = log_line_ratios(clean), targets(clean)
    physics = physics_estimates(frame, card, workers=physics_workers) if with_physics else None
    metrics: dict[str, Any] = {}
    predictions: dict[str, Any] = {}
    for kind in ("random", "region"):
        train_rows, test_rows = datasets.split(clean, 1, kind)
        if len(test_rows) < 3 or len(train_rows) < 12:
            metrics[kind] = {"note": "not enough rows for this split"}
            continue
        model = fit_conformal(algorithm, x[train_rows], y[train_rows], wavelengths, seed)
        baseline = fit_regressor("ridge", x[train_rows], y[train_rows, :2], seed)
        metrics[kind], predictions[kind] = _evaluate(model, baseline, x[test_rows], y[test_rows], physics,
                                                     clean["index"].to_numpy()[test_rows], float(y[train_rows, 2].mean()))
    informative = bool(metrics.get("random", {}).get("p_value_tgas_vs_mean", 1.0) < SIGNIFICANCE)
    final = fit_conformal(algorithm, x, y, wavelengths, seed)  # the registered model: every clean row (75/25)
    final.tgas_informative = informative
    hyper = {**(RF_PARAMETERS if algorithm == "random_forest" else XGBOOST_PARAMETERS), "confidence": CONFIDENCE,
             "calibration_fraction": CALIBRATION_FRACTION, "calibration_seed": CALIBRATION_SEED, "range_margin": RANGE_MARGIN}
    notes = ["features: log10 line-area ratios of the 20 Ar I lines in 690-860 nm (the ridge baseline's features)",
             "90 % split-conformal intervals (MAPIE); the model learns from 75 % of the training rows, the ridge from 100 %",
             "metrics use every held-out row; withheld_share is the share the range check would withhold",
             "the physics line-ratio fit is given the known gas density, T_gas and mixture; the AI sees only the spectrum",
             f"T_gas from this window is {'informative' if informative else 'NOT informative'} "
             "(random split, against the training mean); M12 withholds it when not informative"]
    model_card = make_card(new_model_id(TASK), TASK, algorithm, card.dataset_id, seed, hyper, columns, list(TARGETS), metrics, notes)
    return registry.register(model_card, final, predictions)


# ------------------------------------------------------------------------------------ inference (M12)
@dataclass(frozen=True)
class Estimate:
    """An AI estimate with its 90 % intervals, or the reasons it was withheld."""
    withheld: bool
    reasons: tuple[str, ...]
    te_ev: float = float("nan")
    te_interval_ev: tuple[float, float] = (float("nan"), float("nan"))
    ne_m3: float = float("nan")
    ne_interval_m3: tuple[float, float] = (float("nan"), float("nan"))
    tgas_k: float | None = None
    tgas_interval_k: tuple[float, float] | None = None
    tgas_note: str = ""
    seconds: float = 0.0
    areas: dict[float, float] = field(default_factory=dict)


def spectrum_features(spectrum: Spectrum, wavelengths_nm: list[float]) -> tuple[np.ndarray | None, dict[float, float], list[str]]:
    """Measure the model's lines on a spectrum exactly as on M5; (features, areas, problems)."""
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.cr_model import level_data
    wanted = {round(w, 3) for w in wavelengths_nm}
    lines = [line for line in level_data().lines if round(line.wavelength_nm, 3) in wanted]
    measured = {round(p.wavelength_nm, 3): p.intensity for p in integrated_intensities(spectrum, lines)}
    problems = []
    for w in wavelengths_nm:
        if round(w, 3) not in measured:
            inside = spectrum.settings.start_nm < w < spectrum.settings.end_nm
            problems.append(f"line {w:.3f} nm " + ("cannot be measured (blended at this instrument width)" if inside
                                                    else "is outside the spectrum's wavelength range"))
    if problems:
        return None, measured, problems
    areas = np.array([measured[round(w, 3)] for w in wavelengths_nm])
    if areas.max() <= 0:
        return None, measured, ["no line rises above the background"]
    return ratio_features(areas), measured, []


def estimate(spectrum: Spectrum, model: ConformalModel) -> Estimate:
    """T_e, n_e and (if informative) T_gas from one spectrum, or withheld with the reasons (rules above)."""
    started = time.perf_counter()
    features, areas, problems = spectrum_features(spectrum, model.wavelengths_nm)
    if features is None:
        return Estimate(True, tuple(problems), seconds=time.perf_counter() - started, areas=areas)
    if model.out_of_range(features)[0]:
        width = model.feature_high - model.feature_low
        outside = [f"{w:.3f} nm" for w, value, low, high in zip(model.wavelengths_nm, features[0], model.feature_low - RANGE_MARGIN * width,
                                                                 model.feature_high + RANGE_MARGIN * width) if not low <= value <= high]
        return Estimate(True, (f"the line ratio of {', '.join(outside)} lies outside the training range: the model "
                               "would be extrapolating",), seconds=time.perf_counter() - started, areas=areas)
    point, low, high = (a[0] for a in model.predict(features))
    tgas = dict(tgas_k=float(point[2]), tgas_interval_k=(float(low[2]), float(high[2]))) if model.tgas_informative else {}
    note = "" if model.tgas_informative else ("withheld: this window carries no T_gas information (it did not beat the training "
                                              "mean); use the Doppler width or the N2 rotational band on M5")
    return Estimate(False, (), float(point[0]), (float(low[0]), float(high[0])), float(10 ** point[1]),
                    (float(10 ** low[1]), float(10 ** high[1])), tgas_note=note, seconds=time.perf_counter() - started,
                    areas=areas, **tgas)


FIXED_IN_TRAINING = ("eedf", "spatial", "chamber_diameter_cm", "chamber_height_cm", "electrode_diameter_cm", "electrode_gap_cm")


def untrained_settings(config: dict[str, Any]) -> list[str]:
    """Settings the training runs held fixed (EEDF, spatial model, geometry) where this configuration differs."""
    from plasma_twin.services import stage1
    s1 = datasets.load_settings()["stage1"]
    trained = {**stage1.default_config(), "eedf": s1["eedf"], "spatial": s1["spatial"]}
    return [f"{key} = {trained[key]}" for key in FIXED_IN_TRAINING if key in config and config[key] != trained[key]]


def current_models(registry: Registry | None = None) -> list[ModelCard]:
    """Phase 10 models that may be used (current twin version, file present), newest first (E22)."""
    registry = registry or Registry()
    return [c for c in registry.cards() if c.task == TASK and registry.status(c) == "current"]
