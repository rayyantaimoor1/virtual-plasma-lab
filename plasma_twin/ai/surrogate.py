"""A fast learned copy of the twin, explained with SHAP: Phase 11 (Core Module 2.3, M15, AIQ-3, FR15, E27).

RULES (BUILD_STEPS.md, Phase 11, fixed 6 November 2026 before this code):
- The surrogate copies the twin's noise-free outputs. Stage 1: the twin is re-run at the 1,200 recorded
  inputs of the locked plan (no faults, no instrument noise), cached as data/ai/<id>-twin.parquet.
  Stage 2: the locked dataset, which is already noise-free.
- One multi-output XGBoost model per stage (Phase 9 parameters); a Random Forest is offered for
  comparison and a ridge on the standardised inputs is the baseline. Wide-range outputs are learned as
  log10 (H2O2 and OH with fixed floors, because they are exactly zero in many "O2 only" runs).
- R2 on the learned scale; median relative error in original units over rows whose true value is not 0.
- Speed-up: twin time (median of 20 held-out runs) over the surrogate's time per point in a 625-point
  map (the pass mark); the single-call speed-up is reported beside it.
- SHAP: TreeExplainer, global = mean |SHAP| on the random split's held-out rows.
- Twin check: if |surrogate - twin| > 5 % of |twin|, the twin value is shown and the point flagged (E27).
"""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from plasma_twin.ai import datasets
from plasma_twin.ai.registry import ModelCard, Registry, make_card, new_model_id
from plasma_twin.ai.training import BOOTSTRAP_SEED, XGBOOST_PARAMETERS, regression_metrics
from plasma_twin.config.loader import load_envelope

TASKS = {1: "surrogate_stage1", 2: "surrogate_stage2"}
ALGORITHMS = ("xgboost", "random_forest")
RF_PARAMETERS = {"n_estimators": 500}
LINES_NM = (763.5106, 811.5311, 750.3869, 842.4648)  # the four strongest lines in 690-860 nm
TWIN_TIMING_RUNS = 20
MAP_POINTS = 625


@dataclass(frozen=True)
class Output:
    name: str
    label: str
    unit: str
    log: bool = False
    floor: float = 0.0

    def learned(self, values: np.ndarray) -> np.ndarray:
        """Values on the scale the surrogate learns (log10 plus the floor for wide-range outputs)."""
        values = np.asarray(values, dtype=float)
        return np.log10(values + self.floor) if self.log else values

    def original(self, learned: np.ndarray) -> np.ndarray:
        """Learned-scale values back in original units, never below zero."""
        learned = np.asarray(learned, dtype=float)
        return np.clip(10 ** learned - self.floor, 0.0, None) if self.log else learned


STAGE1_INPUTS = ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "n2_percent", "o2_percent")
STAGE2_INPUTS = ("power_w", "frequency_khz", "width_us", "o2_flow_sccm", "water_temperature_c", "treatment_time_min",
                 "water_volume_ml", "water_ph", "power_share", "gap_mm", "water_vapour")
INPUTS = {1: STAGE1_INPUTS, 2: STAGE2_INPUTS}
INPUT_LABELS = {
    "rf_power_w": "RF power (W)", "pressure_mbar": "Pressure (mbar)", "ar_flow_sccm": "Ar flow (sccm)",
    "n2_percent": "N₂ admixture (%)", "o2_percent": "O₂ admixture (%)", "power_w": "Average power (W)",
    "frequency_khz": "Pulse frequency (kHz)", "width_us": "Pulse width (µs)", "o2_flow_sccm": "O₂ flow (sccm)",
    "water_temperature_c": "Water temperature (°C)", "treatment_time_min": "Treatment time (min)",
    "water_volume_ml": "Water volume (mL)", "water_ph": "Water pH", "power_share": "Power share (-)", "gap_mm": "Gap (mm)",
    "water_vapour": "Water vapour in the bubble (0/1)",
}
OUTPUTS = {
    1: (Output("te_ev", "Electron temperature T_e", "eV"), Output("ne_m3", "Electron density n_e", "m⁻³", log=True),
        Output("tgas_k", "Gas temperature T_gas", "K"))
       + tuple(Output(f"line_{w:.3f}", f"Ar I {w:.1f} nm emission", "W m⁻³", log=True) for w in LINES_NM),
    2: (Output("te_ev", "Electron temperature T_e", "eV"), Output("ne_m3", "Electron density n_e", "m⁻³", log=True),
        Output("ozone_mg_l", "Dissolved O₃", "mg L⁻¹", log=True),
        Output("h2o2_mmol_l", "H₂O₂", "mmol L⁻¹", log=True, floor=1e-9),
        Output("oh_mol_l", "OH (steady state)", "mol L⁻¹", log=True, floor=1e-20),
        Output("temperature_rise_c", "Temperature rise", "°C", log=True),
        Output("log_reduction", "Log reduction", "log10")),
}
# settings the training runs held at their defaults (M15 warns when the open configuration differs)
FIXED = {1: ("eedf", "spatial", "chamber_diameter_cm", "chamber_height_cm", "electrode_diameter_cm", "electrode_gap_cm"),
         2: ("voltage_kv", "conductivity_us_cm", "cod_mg_l", "waste_type", "organism", "initial_count_cfu_ml")}


# ------------------------------------------------------------------------------------ configurations and the twin
def training_defaults(stage: int) -> dict[str, Any]:
    """The settings the surrogate's training runs held fixed (M15 warns when the open configuration differs)."""
    from plasma_twin.services import stage1, stage2
    if stage == 1:
        s1 = datasets.load_settings()["stage1"]
        return {**stage1.default_config(), "eedf": s1["eedf"], "spatial": s1["spatial"]}
    return stage2.default_config()


def features(stage: int, configs: list[dict[str, Any]]) -> np.ndarray:
    """The surrogate's inputs for configurations (or dataset rows). Absent gases count as 0 %."""
    rows = []
    for c in configs:
        if stage == 1:
            mixture = str(c.get("mixture", "Ar"))
            rows.append([c["rf_power_w"], c["pressure_mbar"], c["ar_flow_sccm"],
                         c["n2_percent"] if "N2" in mixture else 0.0, c["o2_percent"] if "O2" in mixture else 0.0])
        else:
            rows.append([c[k] for k in STAGE2_INPUTS[:-1]] + [1.0 if "water" in str(c["bubble_gas"]) else 0.0])
    return np.asarray(rows, dtype=float)


def config_from_features(stage: int, values: np.ndarray, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """A full twin configuration for one feature row, other settings from `base` (or the training defaults)."""
    config = dict(base or training_defaults(stage))
    for key, value in zip(INPUTS[stage], values):
        config[key] = float(value)
    if stage == 1:
        n2, o2 = config["n2_percent"] > 0, config["o2_percent"] > 0
        config["mixture"] = "Ar" + ("+N2" if n2 else "") + ("+O2" if o2 else "")
    else:
        config["bubble_gas"] = "O2 + water vapour" if config.pop("water_vapour") >= 0.5 else "O2 only"
    return config


def twin_outputs(stage: int, config: dict[str, Any]) -> dict[str, float]:
    """Run the twin itself for one configuration and return the surrogate's outputs in original units."""
    if stage == 1:
        from plasma_twin.oes.cr_model import solve_cr_for
        from plasma_twin.services import stage1
        from plasma_twin.stage1.global_model import solve
        result = solve(stage1.to_inputs(config))
        emission = solve_cr_for(result).line_emission_w_m3
        return {"te_ev": result.te_ev, "ne_m3": result.ne_center_m3, "tgas_k": result.inputs.gas_temperature_k,
                **{f"line_{w:.3f}": float(emission[w]) for w in LINES_NM}}
    from plasma_twin.services import stage2
    from plasma_twin.stage2.bubble_model import solve
    from plasma_twin.stage2.hom import survival
    from plasma_twin.stage2.liquid import solve_liquid
    bubble = solve(stage2.bubble_inputs(config))
    water = solve_liquid(bubble, stage2.water_inputs(config))
    kill = survival(water.time_s, water.ozone_mg_l, water.ozone_ct_mg_s_l, config["organism"], config["initial_count_cfu_ml"],
                    config["water_volume_ml"], config["water_temperature_c"], config["power_w"])
    return {"te_ev": bubble.te_ev, "ne_m3": bubble.ne_m3, "ozone_mg_l": float(water.ozone_mg_l[-1]),
            "h2o2_mmol_l": float(water.h2o2_mmol_l[-1]), "oh_mol_l": float(water.oh_mol_l[-1]),
            "temperature_rise_c": water.temperature_after_c - water.temperature_before_c, "log_reduction": kill.log_reduction}


def _stage1_twin_row(row: dict[str, Any]) -> dict[str, Any]:
    config = {**training_defaults(1), **{k: row[k] for k in ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture",
                                                              "n2_percent", "o2_percent")}}
    return {**{k: row[k] for k in ("index", "rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture", "n2_percent", "o2_percent")},
            **twin_outputs(1, config)}


def training_table(stage: int, workers: int = 6, runs: int | None = None) -> pd.DataFrame:
    """Stage 1: the twin re-run noise-free at the locked plan's inputs (cached). Stage 2: the locked dataset."""
    if stage == 2:
        frame, _ = datasets.load(datasets.dataset_id(2))
        return frame if runs is None else frame.head(runs).copy()
    path = datasets.data_dir() / f"{datasets.dataset_id(1)}-twin.parquet"
    if runs is None and path.exists():
        return pd.read_parquet(path)
    plan = datasets.stage1_plan(datasets.load_settings(), runs)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_stage1_twin_row, plan, chunksize=4))
    else:
        rows = [_stage1_twin_row(row) for row in plan]
    table = pd.DataFrame(rows).sort_values("index").reset_index(drop=True)
    if runs is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)
    return table


def learned_targets(stage: int, table: pd.DataFrame) -> np.ndarray:
    """Every output of a training table on its learned scale, one column per output."""
    return np.column_stack([o.learned(table[o.name].to_numpy()) for o in OUTPUTS[stage]])


# ------------------------------------------------------------------------------------ the model
def _regressor(algorithm: str, seed: int):
    if algorithm == "xgboost":
        from xgboost import XGBRegressor
        return XGBRegressor(**XGBOOST_PARAMETERS, random_state=seed)  # multi-output: one tree per output per round
    if algorithm == "random_forest":
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(**RF_PARAMETERS, random_state=seed, n_jobs=-1)
    raise ValueError(f"unknown algorithm {algorithm!r}")


@dataclass
class Surrogate:
    stage: int
    algorithm: str
    model: Any
    input_low: np.ndarray
    input_high: np.ndarray

    @property
    def inputs(self) -> tuple[str, ...]:
        """The surrogate's input names for its stage."""
        return INPUTS[self.stage]

    @property
    def outputs(self) -> tuple[Output, ...]:
        """The surrogate's outputs for its stage."""
        return OUTPUTS[self.stage]

    def predict_learned(self, x: np.ndarray) -> np.ndarray:
        """Every output on its learned scale, one row per configuration."""
        return np.asarray(self.model.predict(np.atleast_2d(x)), dtype=float).reshape(len(np.atleast_2d(x)), -1)

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Every output for every row, in original units (rows, outputs)."""
        learned = self.predict_learned(x)
        return np.column_stack([o.original(learned[:, k]) for k, o in enumerate(self.outputs)])

    def shap(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(SHAP values (rows, inputs, outputs), expected values (outputs,)) on each output's learned scale."""
        import shap
        explainer = shap.TreeExplainer(self.model)
        values = explainer.shap_values(np.atleast_2d(x))
        values = np.stack(values, axis=-1) if isinstance(values, list) else np.asarray(values)
        if values.ndim == 2:
            values = values[:, :, None]
        return values, np.atleast_1d(np.asarray(explainer.expected_value, dtype=float))


def fit(stage: int, algorithm: str, x: np.ndarray, y_learned: np.ndarray, seed: int = BOOTSTRAP_SEED) -> Surrogate:
    """Train one multi-output surrogate and record the training range of each input."""
    return Surrogate(stage, algorithm, _regressor(algorithm, seed).fit(x, y_learned), x.min(axis=0), x.max(axis=0))


def _ridge(x: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-4, 3, 15))).fit(x, y)


# ------------------------------------------------------------------------------------ evaluation
def output_metrics(stage: int, true_learned: np.ndarray, predicted_learned: np.ndarray) -> dict[str, float]:
    """R2 on the learned scale; median relative error (rows with a non-zero true value) and MAE in original units."""
    out: dict[str, float] = {}
    for k, o in enumerate(OUTPUTS[stage]):
        r2 = regression_metrics(true_learned[:, k], predicted_learned[:, k])["r2"]
        true, predicted = o.original(true_learned[:, k]), o.original(predicted_learned[:, k])
        nonzero = np.abs(true) > 0
        out[f"{o.name}_r2"] = r2
        out[f"{o.name}_median_relative_error"] = (float(np.median(np.abs(predicted[nonzero] - true[nonzero]) / np.abs(true[nonzero])))
                                                  if nonzero.any() else float("nan"))
        out[f"{o.name}_mae"] = float(np.mean(np.abs(predicted - true)))
    return out


def timings(stage: int, surrogate: Surrogate, table: pd.DataFrame, rows: np.ndarray) -> dict[str, float]:
    """Twin time (median of up to 20 held-out runs) against the surrogate per map point and per single call."""
    base = training_defaults(stage)
    twin = []
    for i in rows[:TWIN_TIMING_RUNS]:
        row = table.iloc[int(i)].to_dict()
        if stage == 1:
            config = {**base, **{k: row[k] for k in ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture", "n2_percent", "o2_percent")}}
        else:
            config = {**base, **{k: row[k] for k in STAGE2_INPUTS[:-1]}, "bubble_gas": row["bubble_gas"]}
        started = time.perf_counter()
        twin_outputs(stage, config)
        twin.append(time.perf_counter() - started)
    x = features(stage, table.iloc[rows].to_dict("records"))
    grid = np.resize(x, (MAP_POINTS, x.shape[1]))
    surrogate.predict(grid)  # first call loads the libraries
    per_map = []
    for _ in range(5):
        started = time.perf_counter()
        surrogate.predict(grid)
        per_map.append(time.perf_counter() - started)
    single = []
    for k in range(50):
        started = time.perf_counter()
        surrogate.predict(x[k % len(x)][None, :])
        single.append(time.perf_counter() - started)
    twin_s, point_s, single_s = float(np.median(twin)), float(np.median(per_map)) / MAP_POINTS, float(np.median(single))
    return {"twin_seconds": twin_s, "surrogate_seconds_per_map_point": point_s, "surrogate_seconds_single_call": single_s,
            "speedup_map": twin_s / point_s, "speedup_single_call": twin_s / single_s}


def train(stage: int, algorithm: str, registry: Registry | None = None, table: pd.DataFrame | None = None,
          seed: int = BOOTSTRAP_SEED, workers: int = 6, timing: bool = True) -> ModelCard:
    """Train on both splits, evaluate against the ridge, time against the twin, explain with SHAP; register."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"algorithm {algorithm!r} is not offered for the surrogate")
    registry = registry or Registry()
    table = training_table(stage, workers) if table is None else table
    x = features(stage, table.to_dict("records"))
    y = learned_targets(stage, table)
    metrics: dict[str, Any] = {}
    predictions: dict[str, Any] = {}
    for kind in ("random", "region"):
        train_rows, test_rows = datasets.split(table, stage, kind)
        if len(test_rows) < 3 or len(train_rows) < 10:
            metrics[kind] = {"note": "not enough rows for this split"}
            continue
        model = fit(stage, algorithm, x[train_rows], y[train_rows], seed)
        baseline = _ridge(x[train_rows], y[train_rows])
        predicted, base = model.predict_learned(x[test_rows]), baseline.predict(x[test_rows])
        result: dict[str, Any] = {"test_rows": int(len(test_rows)), "model": output_metrics(stage, y[test_rows], predicted),
                                  "baseline": output_metrics(stage, y[test_rows], base)}
        result["worst_r2"] = min(v for k, v in result["model"].items() if k.endswith("_r2"))
        result["worst_median_relative_error"] = max(v for k, v in result["model"].items() if k.endswith("_median_relative_error"))
        if kind == "random":
            shap_values, _ = model.shap(x[test_rows])
            result["shap_importance"] = {o.name: {name: float(np.mean(np.abs(shap_values[:, j, k])))
                                                  for j, name in enumerate(INPUTS[stage])} for k, o in enumerate(OUTPUTS[stage])}
            if timing:
                result.update(timings(stage, model, table, test_rows))
        predictions[kind] = {f"{short}_{who}": OUTPUTS[stage][k].original(values[:, k]).tolist()
                             for short, k in (("te", 0), ("ne", 1))
                             for who, values in (("twin", y[test_rows]), ("model", predicted), ("baseline", base))}
        metrics[kind] = result
    final = fit(stage, algorithm, x, y, seed)
    hyper = {**(XGBOOST_PARAMETERS if algorithm == "xgboost" else RF_PARAMETERS), "multi_output": True}
    notes = ["learns the twin's noise-free outputs" + (" (the twin re-run at the locked Stage 1 plan's inputs)" if stage == 1 else ""),
             "R2 on the learned scale (log10 for wide-range outputs); median relative error in original units",
             "speedup_map is the pass mark (per point in a 625-point map); speedup_single_call is reported beside it",
             "the baseline is a ridge regression on the standardised inputs"]
    if stage == 2:
        notes.append("every Stage 2 row reaches the one-cell cap, so log reduction follows the water volume only")
    card = make_card(new_model_id(TASKS[stage]), TASKS[stage], algorithm, datasets.dataset_id(stage), seed, hyper,
                     list(INPUTS[stage]), [o.name for o in OUTPUTS[stage]], metrics, notes)
    return registry.register(card, final, predictions)


# ------------------------------------------------------------------------------------ twin check (FR15.3, E27)
def tolerance() -> float:
    """The surrogate-twin disagreement limit (E27) as a fraction, from envelope.toml."""
    return load_envelope()["ai"]["surrogate_twin_disagreement_percent"] / 100


@dataclass(frozen=True)
class TwinCheck:
    output: str
    label: str
    unit: str
    surrogate: float
    twin: float
    relative_difference: float
    disagrees: bool

    @property
    def shown(self) -> float:
        """FR17.22: the twin value whenever the two disagree."""
        return self.twin if self.disagrees else self.surrogate


def check_with_twin(surrogate: Surrogate, config: dict[str, Any]) -> list[TwinCheck]:
    """Re-run one configuration through the twin and compare every output (E27 when they differ by > 5 %)."""
    predicted = surrogate.predict(features(surrogate.stage, [config]))[0]
    twin = twin_outputs(surrogate.stage, config)
    limit = tolerance()
    checks = []
    for k, o in enumerate(surrogate.outputs):
        s, t = float(predicted[k]), float(twin[o.name])
        if t == 0:
            difference, disagrees = (0.0 if s <= o.floor else float("inf")), s > o.floor
        else:
            difference = abs(s - t) / abs(t)
            disagrees = difference > limit
        checks.append(TwinCheck(o.name, o.label, o.unit, s, t, difference, disagrees))
    return checks


def untrained_settings(stage: int, config: dict[str, Any]) -> list[str]:
    """Settings the training runs held at their defaults where this configuration differs."""
    trained = training_defaults(stage)
    return [f"{key} = {trained[key]}" for key in FIXED[stage] if key in config and config[key] != trained[key]]


def current_models(stage: int, registry: Registry | None = None) -> list[ModelCard]:
    """Current surrogates of a stage: XGBoost first (the rules' default on M15), then newest first."""
    registry = registry or Registry()
    found = [c for c in registry.cards() if c.task == TASKS[stage] and registry.status(c) == "current"]
    return sorted(found, key=lambda c: c.algorithm != "xgboost")  # stable: newest first within each algorithm
