"""Physics-relationship anomaly detection: Phase 12 (Core Module 2.2, M13, FR13, AIQ-2, E24).

RULES (BUILD_STEPS.md, Phase 12, fixed 7 November 2026 before this code):
- Features are residuals between what was observed and what the twin expects at the recorded inputs
  (noise-free twin, instruments without noise): three OES residuals (total intensity, tilt, pattern)
  and four probe residuals (saturation amplitude, knee position, knee, whole-curve RMS). Amended
  before any detector was trained: tilt and pattern use lines >= 5 % of the expected strongest, and
  the knee position (10 % of the expected end current) replaced a noise-dominated floating potential.
- Isolation Forests (300 trees, seed 20261110) learn from clean training runs only: a full detector,
  an OES-only one and a probe-only one (for measured files).
- Score: 0.5 + 0.1 (raw - m) / (q - m), clipped to 0-1, where m and q are the median and 95th
  percentile of the raw score on a held-back quarter of the clean training runs. Warning >= 0.60,
  Critical >= 0.75 (envelope.toml), so Warning starts at the clean 95th percentile.
- Contribution of a residual = minus its SHAP value; the largest is the likely cause.
- Baseline: the Phase 9 range check on the raw features. Detector vs baseline: exact one-sided McNemar.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from plasma_twin.ai import datasets
from plasma_twin.ai.registry import ModelCard, Registry, make_card, new_model_id
from plasma_twin.ai.training import RangeCheck, anomaly_features, detection_metrics, ratio_features
from plasma_twin.config.loader import load_envelope

TASK = "anomaly_residual"
ALGORITHM = "isolation_forest"
SEED = 20261110
TREES = 300
CALIBRATION_FRACTION = 0.25
FEATURES = ("oes_intensity", "oes_tilt", "oes_pattern", "iv_amplitude", "iv_knee_position", "iv_knee", "iv_shape_rms")
STRONG_LINE_SHARE = 0.05  # amendment: tilt and pattern use lines >= 5 % of the expected strongest
KNEE_CURRENT_SHARE = 0.10  # amendment: the knee position is where the current reaches 10 % of the expected end current
DETECTORS = {"full": FEATURES, "oes": ("oes_tilt", "oes_pattern"), "probe": FEATURES[3:]}
CAUSES = {
    "oes_intensity": "overall line brightness: the power or density differs from the recorded settings",
    "oes_tilt": "spectral tilt: the spectrometer's response has drifted",
    "oes_pattern": "line pattern: lines missing or shifted (wavelength calibration), or T_e or the gas mixture differ (a leak)",
    "iv_amplitude": "probe saturation current: the density differs (power or gas), or the probe current is limited",
    "iv_knee_position": "knee position: RF on the probe, a changed electron temperature or tip contamination",
    "iv_knee": "probe knee shape: T_e, tip contamination or RF",
    "iv_shape_rms": "probe curve shape: tip contamination, RF or a damaged tip",
}
CONFIG_KEYS = ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture", "n2_percent", "o2_percent")


def thresholds() -> tuple[float, float]:
    ai = load_envelope()["ai"]
    return float(ai["anomaly_warning_score"]), float(ai["anomaly_critical_score"])


def severity(score: float) -> str:
    warning, critical = thresholds()
    return "Critical" if score >= critical else "Warning" if score >= warning else "Normal"


# ------------------------------------------------------------------------------------ the twin's expectation
def _window() -> tuple[float, float, float]:
    spec = datasets.load_settings()["stage1"]["spectrometer"]
    return float(spec["window_nm"][0]), float(spec["window_nm"][1]), float(spec["fwhm_nm"])


def expected_diagnostics(result, probe=None) -> dict[str, Any]:
    """Noise-free line areas (as on M5) and probe curve for a solved plasma (RF 0, noise 0)."""
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.cr_model import level_data
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    low, high, fwhm = _window()
    spectrum = spectrum_for(result, SpectrometerSettings(fwhm, low, high, 0.0))
    lines = [line for line in level_data().lines if low <= line.wavelength_nm <= high]
    areas = {round(p.wavelength_nm, 3): p.intensity for p in integrated_intensities(spectrum, lines)}
    settings = probe or ProbeSettings.defaults()
    settings = ProbeSettings(**{**settings.__dict__, "noise_percent": 0.0, "rf_amplitude_v": 0.0})
    plasma = plasma_from(result)
    curve = generate(plasma, settings)
    return {"areas": areas, "voltage": curve.voltage_v, "current": curve.current_a, "vp": plasma.plasma_potential_v}


def _expected_row(row: dict[str, Any]) -> dict[str, Any]:
    from plasma_twin.services import stage1
    from plasma_twin.stage1.global_model import solve
    s1 = datasets.load_settings()["stage1"]
    config = {**stage1.default_config(), **{k: row[k] for k in CONFIG_KEYS}, "eedf": s1["eedf"], "spatial": s1["spatial"]}
    found = expected_diagnostics(solve(stage1.to_inputs(config)))
    return {"index": row["index"], "vp_exp": found["vp"], **{f"exp_line_{w:.3f}": a for w, a in found["areas"].items()},
            **{f"exp_iv_{k:03d}": float(i) for k, i in enumerate(found["current"])}}


def expected_table(frame: pd.DataFrame, card: datasets.DatasetCard, workers: int = 6, cache: bool = True) -> pd.DataFrame:
    """The twin's expectation at every row's recorded inputs, cached next to the dataset."""
    path = datasets.data_dir() / f"{card.dataset_id}-expected.parquet"
    if cache and path.exists():
        table = pd.read_parquet(path)
        if set(frame["index"]) <= set(table["index"]):
            return table.set_index("index").loc[frame["index"]].reset_index()
    jobs = frame[["index", *CONFIG_KEYS]].to_dict("records")
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_expected_row, jobs, chunksize=4))
    else:
        rows = [_expected_row(job) for job in jobs]
    table = pd.DataFrame(rows).sort_values("index").reset_index(drop=True)
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)
    return table


# ------------------------------------------------------------------------------------ residuals
def oes_residuals(observed: np.ndarray, expected: np.ndarray, wavelengths_nm: np.ndarray) -> np.ndarray:
    """(rows, 3): log10 total-intensity ratio, tilt of the line-ratio residuals, and their RMS after mean and tilt."""
    observed, expected = np.atleast_2d(observed).astype(float), np.atleast_2d(expected).astype(float)
    low, high, _ = _window()
    x = (np.asarray(wavelengths_nm, dtype=float) - (low + high) / 2) / ((high - low) / 2)
    total_expected = expected.sum(axis=1)
    total_observed = np.clip(observed.sum(axis=1), 1e-6 * total_expected, None)
    residual = ratio_features(observed) - ratio_features(expected)
    strong = expected >= STRONG_LINE_SHARE * expected.max(axis=1, keepdims=True)  # chosen from the expectation only
    tilt, pattern = np.empty(len(residual)), np.empty(len(residual))
    for r in range(len(residual)):
        keep = strong[r]
        design = np.column_stack([np.ones(keep.sum()), x[keep]])
        coefficients, *_ = np.linalg.lstsq(design, residual[r, keep], rcond=None)
        tilt[r] = coefficients[1]
        pattern[r] = np.sqrt(np.mean((residual[r, keep] - design @ coefficients) ** 2))
    return np.column_stack([np.log10(total_observed / total_expected), tilt, pattern])


def crossing(voltage: np.ndarray, current: np.ndarray, level: float = 0.0) -> float:
    """Where the current first reaches `level` going up (linear interpolation); the sweep end if it never does."""
    above = np.flatnonzero(current >= level)
    if len(above) == 0:
        return float(voltage[-1])
    k = int(above[0])
    if k == 0:
        return float(voltage[0])
    v0, v1, i0, i1 = voltage[k - 1], voltage[k], current[k - 1], current[k]
    return float(v0 + (level - i0) * (v1 - v0) / (i1 - i0))


def probe_residuals(voltage: np.ndarray, observed: np.ndarray, expected: np.ndarray, vp_expected: np.ndarray) -> np.ndarray:
    """(rows, 4): log10 end-current ratio, knee-position shift, mean knee residual, whole-curve RMS residual."""
    observed, expected = np.atleast_2d(observed).astype(float), np.atleast_2d(expected).astype(float)
    vp_expected = np.atleast_1d(vp_expected)
    out = np.empty((len(observed), 4))
    for r in range(len(observed)):
        scale = abs(expected[r, -1])
        normalised = (observed[r] - expected[r]) / scale
        level = KNEE_CURRENT_SHARE * expected[r, -1]
        position = crossing(voltage, observed[r], level) - crossing(voltage, expected[r], level)
        vf_exp = crossing(voltage, expected[r])  # noise-free, so its zero crossing is well defined
        knee = (voltage >= vf_exp) & (voltage <= vp_expected[r])
        out[r] = [np.log10(max(observed[r, -1], 1e-6 * scale) / scale), position,
                  float(np.mean(normalised[knee])) if knee.any() else 0.0, float(np.sqrt(np.mean(normalised**2)))]
    return out


def dataset_residuals(frame: pd.DataFrame, expected: pd.DataFrame) -> pd.DataFrame:
    """The seven residuals of every dataset row (frame and expected aligned by 'index')."""
    from plasma_twin.probe.iv_model import ProbeSettings
    expected = expected.set_index("index").loc[frame["index"]]
    lines = sorted((c for c in frame.columns if c.startswith("line_")), key=lambda c: float(c[5:]))
    iv = sorted(c for c in frame.columns if c.startswith("iv_"))
    oes = oes_residuals(frame[lines].to_numpy(), expected[[f"exp_{c}" for c in lines]].to_numpy(), np.array([float(c[5:]) for c in lines]))
    probe = probe_residuals(ProbeSettings.defaults().voltages(), frame[iv].to_numpy(), expected[[f"exp_{c}" for c in iv]].to_numpy(),
                            expected["vp_exp"].to_numpy())
    return pd.DataFrame(np.hstack([oes, probe]), columns=FEATURES, index=frame.index)


# ------------------------------------------------------------------------------------ detectors
@dataclass
class ResidualDetector:
    features: tuple[str, ...]
    forest: Any
    median: float
    q95: float

    def raw(self, x: np.ndarray) -> np.ndarray:
        return -self.forest.score_samples(np.atleast_2d(x))  # the original paper's score: near 1 = anomalous

    def score(self, x: np.ndarray) -> np.ndarray:
        return np.clip(0.5 + 0.1 * (self.raw(x) - self.median) / (self.q95 - self.median), 0.0, 1.0)

    def contributions(self, x: np.ndarray) -> np.ndarray:
        """(rows, features): minus the SHAP values of the path length; larger means more anomalous."""
        import shap
        return -np.asarray(shap.TreeExplainer(self.forest).shap_values(np.atleast_2d(x)))


def fit_detector(x_clean: np.ndarray, features: tuple[str, ...], seed: int = SEED) -> ResidualDetector:
    from sklearn.ensemble import IsolationForest
    order = np.random.default_rng(seed).permutation(len(x_clean))
    cut = int(round(len(x_clean) * (1 - CALIBRATION_FRACTION)))
    forest = IsolationForest(n_estimators=TREES, random_state=seed).fit(x_clean[order[:cut]])
    raw = -forest.score_samples(x_clean[order[cut:]])
    return ResidualDetector(features, forest, float(np.median(raw)), float(np.quantile(raw, 0.95)))


@dataclass
class AnomalyModel:
    detectors: dict[str, ResidualDetector]
    range_check: RangeCheck
    line_wavelengths_nm: list[float]
    probe_voltage_v: np.ndarray = field(default_factory=lambda: np.array([]))


def _metrics(is_fault: np.ndarray, flagged: np.ndarray, faults: np.ndarray) -> dict[str, float]:
    out = detection_metrics(is_fault, flagged)
    for kind in datasets.FAULT_TYPES:
        rows = faults == kind
        if rows.any():
            out[f"recall_{kind}"] = float(flagged[rows].mean())
    return out


def mcnemar_p(detector: np.ndarray, baseline: np.ndarray) -> float:
    """Exact one-sided McNemar test on faulty runs: is the detector's recall higher than the baseline's?"""
    from scipy.stats import binomtest
    only_detector, only_baseline = int(np.sum(detector & ~baseline)), int(np.sum(baseline & ~detector))
    if only_detector + only_baseline == 0:
        return 1.0
    return float(binomtest(only_detector, only_detector + only_baseline, 0.5, alternative="greater").pvalue)


def train(frame: pd.DataFrame, card: datasets.DatasetCard, registry: Registry | None = None, workers: int = 6,
          seed: int = SEED) -> ModelCard:
    """Fit the three detectors and the range check on clean training runs; evaluate on both splits; register."""
    from plasma_twin.probe.iv_model import ProbeSettings
    registry = registry or Registry()
    frame = frame.reset_index(drop=True)
    expected = expected_table(frame, card, workers)
    residuals = dataset_residuals(frame, expected).to_numpy()
    raw = anomaly_features(frame)
    faults = frame["fault"].to_numpy()
    is_fault = faults != "none"
    warning, _ = thresholds()
    metrics: dict[str, Any] = {}
    for kind in ("random", "region"):
        train_rows, test_rows = datasets.split(frame, 1, kind)
        clean_train = train_rows[~is_fault[train_rows]]
        if len(clean_train) < 20 or len(test_rows) < 5:
            metrics[kind] = {"note": "not enough rows for this split"}
            continue
        check = RangeCheck().fit(raw[clean_train])
        baseline_flags = check.flag(raw[test_rows])
        result: dict[str, Any] = {"test_rows": int(len(test_rows)), "test_faults": int(is_fault[test_rows].sum()),
                                  "baseline": _metrics(is_fault[test_rows], baseline_flags, faults[test_rows])}
        for name, columns in DETECTORS.items():
            k = [FEATURES.index(c) for c in columns]
            detector = fit_detector(residuals[clean_train][:, k], columns, seed)
            scores = detector.score(residuals[test_rows][:, k])
            flagged = scores >= warning
            label = "model" if name == "full" else f"{name}_only"
            result[label] = _metrics(is_fault[test_rows], flagged, faults[test_rows])
            if name == "full":
                result["model"]["critical_share_of_flags"] = float(np.mean([severity(s) == "Critical" for s in scores[flagged]])) if flagged.any() else 0.0
                faulty = is_fault[test_rows]
                result["p_value_vs_range_check"] = mcnemar_p(flagged[faulty], baseline_flags[faulty])
        metrics[kind] = result
    clean = np.flatnonzero(~is_fault)
    final = AnomalyModel({name: fit_detector(residuals[clean][:, [FEATURES.index(c) for c in columns]], columns, seed)
                          for name, columns in DETECTORS.items()},
                         RangeCheck().fit(raw[clean]),
                         sorted(float(c[5:]) for c in frame.columns if c.startswith("line_")),
                         ProbeSettings.defaults().voltages())
    hyper = {"trees": TREES, "calibration_fraction": CALIBRATION_FRACTION,
             **{f"{n}_median": d.median for n, d in final.detectors.items()}, **{f"{n}_q95": d.q95 for n, d in final.detectors.items()}}
    notes = ["features: seven residuals between observation and the twin's noise-free expectation at the recorded inputs",
             "score 0.5 = a typical clean run; Warning (0.60) starts at the clean 95th percentile; Critical at 0.75",
             "baseline: the Phase 9 range check on the raw features; p_value_vs_range_check is an exact one-sided McNemar test",
             "oes_only and probe_only are the detectors used for single measured files"]
    model_card = make_card(new_model_id(TASK), TASK, ALGORITHM, card.dataset_id, seed, hyper, list(FEATURES), ["anomaly score"],
                           metrics, notes)
    return registry.register(model_card, final, None)


# ------------------------------------------------------------------------------------ checking a run (M13)
@dataclass(frozen=True)
class Assessment:
    detector: str
    score: float
    severity: str
    likely_cause: str
    likely_residual: str
    residuals: dict[str, float]
    contributions: dict[str, float]
    range_check: str  # flagged, passed or not applicable


def assess(model: AnomalyModel, which: str, residual_values: dict[str, float], raw_features: np.ndarray | None = None) -> Assessment:
    detector = model.detectors[which]
    x = np.array([[residual_values[f] for f in detector.features]])
    score = float(detector.score(x)[0])
    contributions = dict(zip(detector.features, detector.contributions(x)[0].tolist()))
    top = max(contributions, key=contributions.get)
    range_result = "not applicable"
    if raw_features is not None and raw_features.shape[-1] == len(model.range_check.low):
        range_result = "flagged" if model.range_check.flag(np.atleast_2d(raw_features))[0] else "passed"
    level = severity(score)
    cause = CAUSES[top] if level != "Normal" else "none (within the normal spread of clean runs)"
    return Assessment(which, score, level, cause, top, {f: float(residual_values[f]) for f in detector.features}, contributions, range_result)


def assess_stage1_config(model: AnomalyModel, config: dict[str, Any], spectrometer=None, probe=None) -> Assessment:
    """The open plasma or a saved session: its synthetic diagnostics (with the given instruments) against the twin."""
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.cr_model import level_data
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    from plasma_twin.services import stage1
    result = stage1.run(config)
    low, high, default_fwhm = _window()
    instrument = spectrometer or SpectrometerSettings.defaults(fwhm_nm=default_fwhm)
    spectrum = spectrum_for(result, SpectrometerSettings(instrument.fwhm_nm, low - 2, high + 2, instrument.noise_percent, instrument.seed))
    wanted = {round(w, 3) for w in model.line_wavelengths_nm}
    lines = [line for line in level_data().lines if round(line.wavelength_nm, 3) in wanted]
    observed = {round(p.wavelength_nm, 3): p.intensity for p in integrated_intensities(spectrum, lines)}
    probe = probe or ProbeSettings.defaults()
    curve = generate(plasma_from(result), probe)
    expected = expected_diagnostics(result, probe)
    common = [w for w in sorted(wanted) if w in observed and w in expected["areas"]]
    oes = oes_residuals(np.array([observed[w] for w in common]), np.array([expected["areas"][w] for w in common]), np.array(common))[0]
    iv = probe_residuals(curve.voltage_v, curve.current_a, expected["current"], np.array([expected["vp"]]))[0]
    values = dict(zip(FEATURES, [*oes, *iv]))
    raw = None
    if len(common) == len(wanted) and len(curve.voltage_v) == len(model.probe_voltage_v) and np.allclose(curve.voltage_v, model.probe_voltage_v):
        raw = np.hstack([ratio_features(np.array([observed[w] for w in common]))[0], curve.current_a / np.abs(curve.current_a).max()])
    return assess(model, "full", values, raw)


def assess_measured(model: AnomalyModel, store, record, open_config: dict[str, Any]) -> Assessment:
    """A measured Stage 1 file against the twin at its recorded conditions (else the open plasma's settings)."""
    from plasma_twin.data_io.validation import spectrum_from_arrays
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.cr_model import level_data
    from plasma_twin.probe.iv_model import ProbeSettings
    from plasma_twin.services import stage1
    conditions = record.metadata.get("conditions") or {}
    result = stage1.run({**open_config, **conditions})
    x, y, _ = store.load(record.file_id)
    if record.diagnostic == "probe":
        geometry = record.metadata["probe"]
        settings = ProbeSettings.defaults(tip_radius_mm=float(geometry["tip_radius_mm"]), exposed_length_mm=float(geometry["exposed_length_mm"]))
        expected = expected_diagnostics(result, settings)
        inside = (x >= expected["voltage"][0]) & (x <= expected["voltage"][-1])
        exp_current = np.interp(x[inside], expected["voltage"], expected["current"])
        iv = probe_residuals(x[inside], y[inside], exp_current, np.array([expected["vp"]]))[0]
        return assess(model, "probe", dict(zip(FEATURES[3:], iv)))
    spectrum = spectrum_from_arrays(x, y, float(record.metadata["instrument_fwhm_nm"]), result.inputs.gas_temperature_k)
    wanted = {round(w, 3) for w in model.line_wavelengths_nm}
    lines = [line for line in level_data().lines if round(line.wavelength_nm, 3) in wanted]
    observed = {round(p.wavelength_nm, 3): p.intensity for p in integrated_intensities(spectrum, lines)}
    expected = expected_diagnostics(result)
    common = [w for w in sorted(wanted) if w in observed and w in expected["areas"]]
    if len(common) < 3:
        raise ValueError(f"only {len(common)} of the model's argon lines lie in this file's range; at least 3 are needed")
    oes = oes_residuals(np.array([observed[w] for w in common]), np.array([expected["areas"][w] for w in common]), np.array(common))[0]
    return assess(model, "oes", dict(zip(FEATURES[:3], oes)))


def current_models(registry: Registry | None = None) -> list[ModelCard]:
    registry = registry or Registry()
    return [c for c in registry.cards() if c.task == TASK and registry.status(c) == "current"]
