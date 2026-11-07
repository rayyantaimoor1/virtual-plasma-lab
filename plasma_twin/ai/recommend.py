"""Counterfactual recommendations verified by the twin: Phase 13 (Core Module 2.4, M14, AIQ-4, PER-10, FR14, E25, E26).

RULES (BUILD_STEPS.md, Phase 13, fixed 7 November 2026 before this code):
- Search the Phase 11 surrogate's inputs with differential evolution (seed 20261111, Latin-hypercube start,
  population 20 per searched setting, at most 60 generations, no polish), inside the envelope narrowed to
  the surrogate's training range. Everything else comes from the open configuration.
- Fixed settings: Stage 1 always keeps its gas mixture; Stage 2 always keeps the power share (the model's
  uncertainty, not a knob) and by default the water (volume, pH, temperature) and the bubble gas.
- A point that meets the aim scores its cost scaled to 0-1; one that misses scores 1 + its miss.
- Top 3: the best evaluated points at least 0.1 apart (searched settings scaled to 0-1). Each is re-run
  through the twin; a candidate whose twin run fails is dropped and listed. Nothing leaves this module
  without a twin outcome (CON-12).
- Twin repair: a candidate that misses a target goal has the one setting the goal rises with (RF power for
  n_e and T_gas, treatment time for log reduction) adjusted by bisection on the twin, at most 12 twin runs.
- Ranked by the twin: met first, then the lowest cost; misses by the smallest miss. "Maximise" goals by the
  highest twin value. No met candidate means the goal is unreachable (E26) and the closest one is shown.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

from plasma_twin.ai import datasets, surrogate
from plasma_twin.config.loader import load_envelope

SEARCH_SEED = 20261111
BENCHMARK_SEEDS = {1: 20261111, 2: 20261112}
BENCHMARK_GOALS = {1: 20, 2: 10}
POPULATION = 20
GENERATIONS = 60
DISTINCT = 0.10
REPAIR_RUNS = 12
CAP_MARGIN = 0.05  # amendment (7 Nov 2026): the aim never asks for more than cap - 0.05 (about 8x the surrogate's MAE)
INTEGER = ("gap_mm", "water_vapour")
ALWAYS_FIXED = {1: (), 2: ("power_share",)}
WATER = ("water_volume_ml", "water_ph", "water_temperature_c", "water_vapour")
BENCHMARK_FILE = "recommend-benchmark.json"


@dataclass(frozen=True)
class Objective:
    key: str
    stage: int
    label: str
    kind: str  # "band" (two-sided target), "at_least" or "maximise"
    output: str | None  # surrogate output; None when the user chooses it (the strongest line)
    tolerance: float = 0.0  # when the twin says the goal is met
    aim: float = 0.0  # what the search asks of the surrogate (tighter, for its own error)
    relative: bool = False
    repair: str | None = None  # the setting the goal rises with


OBJECTIVES = {
    "ne_target": Objective("ne_target", 1, "Reach a target electron density n_e", "band", "ne_m3", 0.10, 0.05, True, "rf_power_w"),
    "tgas_target": Objective("tgas_target", 1, "Reach a target gas temperature T_gas", "band", "tgas_k", 0.5, 0.25, False, "rf_power_w"),
    "line_max": Objective("line_max", 1, "Make a chosen Ar line as strong as possible", "maximise", None),
    "lr_least_energy": Objective("lr_least_energy", 2, "Reach a target log reduction with the least energy per litre", "at_least",
                                 "log_reduction", 0.01, 0.10, False, "treatment_time_min"),
    "lr_budget": Objective("lr_budget", 2, "Maximise the log reduction within an energy budget", "maximise", "log_reduction"),
}


@dataclass(frozen=True)
class Goal:
    objective: str
    target: float | None = None  # n_e (m^-3), T_gas (K) or log reduction
    line: str | None = None  # the output name of the chosen line (line_max)
    budget_kj_l: float | None = None  # lr_budget

    @property
    def spec(self) -> Objective:
        return OBJECTIVES[self.objective]

    @property
    def stage(self) -> int:
        return self.spec.stage

    @property
    def output(self) -> str:
        return self.spec.output or str(self.line)

    def describe(self) -> str:
        s = self.spec
        if s.key == "ne_target":
            return f"n_e = {self.target:.3g} m⁻³ (±10 %), least RF power"
        if s.key == "tgas_target":
            return f"T_gas = {self.target:.2f} K (±0.5 K), least RF power"
        if s.key == "line_max":
            return f"strongest {surrogate_label(self.output)}"
        if s.key == "lr_least_energy":
            return f"log reduction ≥ {self.target:.2f} with the least energy per litre"
        return f"largest log reduction within {self.budget_kj_l:.3g} kJ/L"

    def check(self) -> None:
        if self.objective not in OBJECTIVES:
            raise ValueError(f"unknown objective {self.objective!r}")
        s = self.spec
        if s.kind != "maximise" and (self.target is None or not np.isfinite(self.target)):
            raise ValueError("this goal needs a target value")
        if s.key == "ne_target" and not self.target > 0:
            raise ValueError("the target electron density must be greater than zero")
        if s.key == "line_max" and self.line not in [o.name for o in surrogate.OUTPUTS[1] if o.name.startswith("line_")]:
            raise ValueError("choose one of the four surrogate lines")
        if s.key == "lr_budget" and not (self.budget_kj_l and self.budget_kj_l > 0):
            raise ValueError("the energy budget must be greater than zero")


def surrogate_label(output: str) -> str:
    for stage in (1, 2):
        for o in surrogate.OUTPUTS[stage]:
            if o.name == output:
                return o.label
    return output


# ------------------------------------------------------------------------------------ the search space
def bounds(stage: int) -> dict[str, tuple[float, float]]:
    """The envelope narrowed to the surrogate's training range, for every surrogate input."""
    env = load_envelope()
    if stage == 1:
        e = env["stage1"]
        mix = e["admixture_percent_of_ar"]
        return {"rf_power_w": (e["rf_power_w"]["min"], e["rf_power_w"]["max"]),
                "pressure_mbar": (e["pressure_mbar"]["min"], e["pressure_mbar"]["max"]),
                "ar_flow_sccm": (e["ar_flow_sccm"]["min"], e["ar_flow_sccm"]["max"]),
                "n2_percent": (mix["min"], mix["max"]), "o2_percent": (mix["min"], mix["max"])}
    e, s2 = env["stage2"], datasets.load_settings()["stage2"]
    gaps = e["options"]["electrode_gap_mm"]
    return {"power_w": (e["average_power_w"]["min"], e["average_power_w"]["max"]),
            "frequency_khz": (e["pulse_frequency_khz"]["min"], e["pulse_frequency_khz"]["max"]),
            "width_us": tuple(s2["width_us"]), "o2_flow_sccm": (e["o2_flow_sccm"]["min"], e["o2_flow_sccm"]["max"]),
            "water_temperature_c": (e["water_temperature_c"]["min"], e["water_temperature_c"]["max"]),
            "treatment_time_min": (e["treatment_time_min"]["min"], e["treatment_time_min"]["max"]),
            "water_volume_ml": (e["water_volume_ml"]["min"], e["water_volume_ml"]["max"]),
            "water_ph": (e["water_ph"]["min"], e["water_ph"]["max"]), "power_share": tuple(s2["power_share"]),
            "gap_mm": (min(gaps), max(gaps)), "water_vapour": (0, 1)}
    # all floats except the two whole-number settings (INTEGER)


def searchable(stage: int, config: dict[str, Any]) -> list[str]:
    """Settings the user may search or fix: the surrogate inputs, without the always-fixed ones and absent gases."""
    names = [n for n in surrogate.INPUTS[stage] if n not in ALWAYS_FIXED[stage]]
    if stage == 1:
        mixture = str(config.get("mixture", "Ar"))
        names = [n for n in names if not (n == "n2_percent" and "N2" not in mixture) and not (n == "o2_percent" and "O2" not in mixture)]
    return names


def default_fixed(stage: int) -> set[str]:
    """FR14.2 defaults: Stage 2 keeps the water being treated and the bubble gas."""
    return set() if stage == 1 else set(WATER)


def energy_kj_per_l(config: dict[str, Any]) -> float:
    """Average power x treatment time / water volume (exact, never learned)."""
    return config["power_w"] * config["treatment_time_min"] * 60.0 / 1000.0 / (config["water_volume_ml"] / 1000.0)


def cost_of(stage: int, config: dict[str, Any]) -> float:
    """Stage 1: RF power (W). Stage 2: energy per litre (kJ/L)."""
    return float(config["rf_power_w"]) if stage == 1 else energy_kj_per_l(config)


COST_LABEL = {1: ("RF power", "W"), 2: ("Energy per litre", "kJ/L")}


def _candidate_config(stage: int, values: np.ndarray, base: dict[str, Any]) -> dict[str, Any]:
    config = surrogate.config_from_features(stage, values, base)
    if stage == 1:  # an absent gas keeps the base value of its (hidden) admixture field
        for gas, name in (("N2", "n2_percent"), ("O2", "o2_percent")):
            if gas not in config["mixture"]:
                config[name] = base[name]
    else:
        config["gap_mm"] = float(round(config["gap_mm"]))
    return config


# ------------------------------------------------------------------------------------ scoring
def _miss(goal: Goal, value: np.ndarray, judging: bool, cap: np.ndarray | None = None) -> np.ndarray:
    """How far a value is from the goal (0 = good enough).

    judging=True: the twin's test of the rules (n_e within ±10 %, T_gas within ±0.5 K, log reduction >= target - 0.01).
    judging=False: the search's aim on the surrogate, tighter to leave room for its error (±5 %, ±0.25 K, >= target + 0.1;
    amended: never above the one-cell cap - 0.05, which `cap` gives for each point).
    """
    s = goal.spec
    if s.kind == "band":
        margin = s.tolerance if judging else s.aim
        distance = np.abs(value / goal.target - 1.0) if s.relative else np.abs(value - goal.target)
        return np.maximum(0.0, distance - margin) / s.tolerance
    if judging:  # at_least
        floor = goal.target - s.tolerance
    else:
        floor = goal.target + s.aim
        if cap is not None:
            floor = np.minimum(floor, cap - CAP_MARGIN)
    return np.maximum(0.0, floor - value)


def _search_scores(goal: Goal, predicted: np.ndarray, costs: np.ndarray, cost_range: tuple[float, float],
                   cap: np.ndarray | None = None) -> np.ndarray:
    """Lower is better. Meeting the aim always beats missing it (rules: cost in 0-1, a miss scores 1 + miss)."""
    s = goal.spec
    scaled = (costs - cost_range[0]) / (cost_range[1] - cost_range[0])
    if s.kind == "maximise":
        if goal.objective == "lr_budget":
            over = np.maximum(0.0, costs - goal.budget_kj_l) / goal.budget_kj_l
            return np.where(over > 0, 100.0 + over, -predicted + 1e-3 * scaled)
        return -np.log10(np.maximum(predicted, 1e-300))
    miss = _miss(goal, predicted, judging=False, cap=cap)
    return np.where(miss > 0, 1.0 + miss, scaled)


def one_cell_cap(initial_cfu_ml: float, volume_ml: np.ndarray) -> np.ndarray:
    """The largest possible log reduction: one live cell left in the whole volume (hom.py), exact, never learned."""
    return np.log10(initial_cfu_ml * np.asarray(volume_ml, dtype=float))


def _costs(stage: int, x: np.ndarray) -> np.ndarray:
    names = surrogate.INPUTS[stage]
    if stage == 1:
        return x[:, names.index("rf_power_w")]
    p, t, v = (x[:, names.index(k)] for k in ("power_w", "treatment_time_min", "water_volume_ml"))
    return p * t * 60.0 / 1000.0 / (v / 1000.0)


def _cost_range(stage: int) -> tuple[float, float]:
    b = bounds(stage)
    if stage == 1:
        return b["rf_power_w"]
    low = b["power_w"][0] * b["treatment_time_min"][0] * 0.06 / (b["water_volume_ml"][1] / 1000)
    high = b["power_w"][1] * b["treatment_time_min"][1] * 0.06 / (b["water_volume_ml"][0] / 1000)
    return low, high


# ------------------------------------------------------------------------------------ results
@dataclass
class Candidate:
    config: dict[str, Any]
    searched: dict[str, float]
    surrogate_value: float  # the surrogate's prediction of the goal output at the searched point
    twin: dict[str, float]  # every twin output (original units)
    value: float  # the twin's value of the goal output
    cost: float
    met: bool
    miss: float  # in tolerance units (0 when met)
    repair_runs: int = 0  # > 0: repaired by the twin
    met_before_repair: bool = False


@dataclass
class Recommendation:
    goal: Goal
    stage: int
    model_id: str
    fixed: dict[str, Any]
    searched: list[str]
    candidates: list[Candidate]
    dropped: list[dict[str, Any]]
    evaluated: int
    seconds: float
    warnings: list[str] = field(default_factory=list)

    @property
    def reachable(self) -> bool:
        return any(c.met for c in self.candidates)

    @property
    def reachable_without_repair(self) -> bool:
        return any(c.met_before_repair for c in self.candidates)

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    def to_json(self) -> str:
        """FR14.7: the goal, the fixed settings and every candidate with its twin outcome."""
        payload = {"goal": asdict(self.goal), "goal_text": self.goal.describe(), "stage": self.stage, "surrogate": self.model_id,
                   "fixed": self.fixed, "searched": self.searched, "reachable": self.reachable,
                   "candidates": [asdict(c) for c in self.candidates], "dropped": self.dropped,
                   "surrogate_points_evaluated": self.evaluated, "seconds": self.seconds, "warnings": self.warnings}
        return json.dumps(payload, indent=2, default=float)


# ------------------------------------------------------------------------------------ the twin
def twin_outcome(stage: int, config: dict[str, Any]) -> dict[str, float]:
    """The twin's outputs for one configuration, with the cost added."""
    return {**surrogate.twin_outputs(stage, config), "cost": cost_of(stage, config)}


def _judge(goal: Goal, value: float, predicted: float, cost: float) -> tuple[bool, float]:
    s = goal.spec
    if s.kind == "maximise":
        agrees = abs(predicted - value) <= surrogate.tolerance() * abs(value) if value else predicted == 0
        within = goal.budget_kj_l is None or cost <= goal.budget_kj_l * (1 + 1e-9)
        return agrees and within, 0.0 if agrees and within else abs(predicted - value) / max(abs(value), 1e-300)
    miss = float(_miss(goal, np.array([value]), judging=True)[0])
    return miss == 0.0, miss


def _verify(goal: Goal, sur: surrogate.Surrogate, config: dict[str, Any], searched: dict[str, float],
            twin: Callable[[int, dict[str, Any]], dict[str, float]]) -> Candidate:
    stage = goal.stage
    index = [o.name for o in sur.outputs].index(goal.output)
    predicted = float(sur.predict(surrogate.features(stage, [config]))[0, index])
    outcome = twin(stage, config)
    value, cost = float(outcome[goal.output]), cost_of(stage, config)
    met, miss = _judge(goal, value, predicted, cost)
    return Candidate(config, searched, predicted, outcome, value, cost, met, miss, 0, met)


def _repair(goal: Goal, sur: surrogate.Surrogate, candidate: Candidate, free: list[str],
            twin: Callable[[int, dict[str, Any]], dict[str, float]]) -> Candidate:
    """Bisection on the one setting the goal rises with, using the twin only (at most REPAIR_RUNS twin runs)."""
    s = goal.spec
    name = s.repair
    if candidate.met or s.kind == "maximise" or name not in free:
        return candidate
    low, high = bounds(goal.stage)[name]
    start = candidate.config[name]
    raise_it = candidate.value < goal.target
    far = high if raise_it else low
    if far == start:
        return candidate
    runs = 0

    def run_at(x: float) -> tuple[dict[str, Any], dict[str, float]]:
        nonlocal runs
        runs += 1
        config = {**candidate.config, name: float(x)}
        return config, twin(goal.stage, config)

    def side(outcome: dict[str, float]) -> int:
        """-1: still short of the goal in the direction we move; 0: met; +1: past it."""
        value = float(outcome[goal.output])
        if float(_miss(goal, np.array([value]), judging=True)[0]) == 0.0:
            return 0
        return -1 if (value < goal.target) == raise_it else 1

    try:
        config, outcome = run_at(far)
    except Exception:  # noqa: BLE001 - a failed twin run ends the repair; the candidate stays as it was
        return candidate
    where = side(outcome)
    if where == -1:  # even the limit of the setting does not reach the goal
        return candidate
    found = (config, outcome) if where == 0 else None
    near, beyond = start, far  # the goal lies between them
    while runs < REPAIR_RUNS and not (found and s.kind == "band"):
        middle = 0.5 * (near + beyond)
        try:
            config, outcome = run_at(middle)
        except Exception:  # noqa: BLE001
            break
        where = side(outcome)
        if where == 0:
            found = (config, outcome)
            if s.kind == "band":
                break
            beyond = middle  # at_least: keep looking for a smaller (cheaper) time that still meets it
        elif where == -1:
            near = middle
        else:
            beyond = middle
    if found is None:
        return candidate
    config, outcome = found
    repaired = _verify(goal, sur, config, {**candidate.searched, name: float(config[name])}, lambda *_: outcome)
    repaired.repair_runs, repaired.met_before_repair = runs, False
    return repaired


def _rank(goal: Goal, candidates: list[Candidate]) -> list[Candidate]:
    if goal.spec.kind == "maximise":
        over = (lambda c: goal.budget_kj_l is not None and c.cost > goal.budget_kj_l * (1 + 1e-9))
        return sorted(candidates, key=lambda c: (over(c), -c.value))
    return sorted(candidates, key=lambda c: (not c.met, 0.0 if c.met else c.miss, c.cost))


# ------------------------------------------------------------------------------------ recommend (FR14.3, E25, E26)
def _distinct(order: np.ndarray, unit: np.ndarray, count: int = 3) -> list[int]:
    chosen: list[int] = []
    for i in order:
        if all(np.linalg.norm(unit[i] - unit[j]) >= DISTINCT for j in chosen):
            chosen.append(int(i))
            if len(chosen) == count:
                break
    return chosen


def recommend(goal: Goal, sur: surrogate.Surrogate, config: dict[str, Any], fixed: set[str] | None = None,
              model_id: str = "", twin: Callable[[int, dict[str, Any]], dict[str, float]] = twin_outcome,
              progress: Callable[[str], None] | None = None) -> Recommendation:
    """Search on the surrogate, re-run the best three through the twin, repair, rank by the twin."""
    from scipy.optimize import differential_evolution
    goal.check()
    stage = goal.stage
    if sur.stage != stage:
        raise ValueError("the surrogate is for the other stage")
    if stage == 2 and config.get("organism") != "E. coli":
        raise ValueError(f"{config.get('organism')}: no published kinetics parameters, so no log reduction can be predicted (LI-6)")
    started = time.perf_counter()
    fixed = default_fixed(stage) if fixed is None else set(fixed)
    allowed = searchable(stage, config)
    free = [n for n in allowed if n not in fixed]
    names = list(surrogate.INPUTS[stage])
    base = surrogate.features(stage, [config])[0]
    limits = bounds(stage)
    columns = [names.index(n) for n in free]
    low = np.array([limits[n][0] for n in free], dtype=float)
    high = np.array([limits[n][1] for n in free], dtype=float)
    index = [o.name for o in sur.outputs].index(goal.output)
    cost_range = _cost_range(stage)
    seen_x: list[np.ndarray] = []
    seen_f: list[np.ndarray] = []

    def score(x_free: np.ndarray) -> np.ndarray:  # x_free: (searched settings, points), the whole population
        x = np.repeat(base[None, :], x_free.shape[1], axis=0)
        x[:, columns] = x_free.T
        values = sur.predict(x)[:, index]
        cap = (one_cell_cap(config["initial_count_cfu_ml"], x[:, names.index("water_volume_ml")])
               if goal.objective == "lr_least_energy" else None)
        f = _search_scores(goal, values, _costs(stage, x), cost_range, cap)
        seen_x.append(x)
        seen_f.append(f)
        return f

    if progress:
        progress(f"Searching {len(free)} settings on the surrogate...")
    if free:
        differential_evolution(score, list(zip(low, high)), seed=SEARCH_SEED, popsize=POPULATION, maxiter=GENERATIONS,
                               polish=False, init="latinhypercube", vectorized=True, updating="deferred",
                               integrality=[n in INTEGER for n in free])
    else:
        score(np.empty((0, 1)))
    xs, fs = np.vstack(seen_x), np.concatenate(seen_f)
    span = np.where(high > low, high - low, 1.0)
    unit = (xs[:, columns] - low) / span if free else np.zeros((len(xs), 1))
    picks = _distinct(np.argsort(fs, kind="stable"), unit)

    candidates, dropped = [], []
    for n, i in enumerate(picks, start=1):
        if progress:
            progress(f"Re-simulating candidate {n} of {len(picks)} with the digital twin...")
        candidate_config = _candidate_config(stage, xs[i], config)
        searched = {name: float(candidate_config[name]) if name in candidate_config else float(xs[i][names.index(name)])
                    for name in free}
        try:
            verified = _verify(goal, sur, candidate_config, searched, twin)
        except Exception as problem:  # noqa: BLE001 - E25: a failed twin run drops the candidate, never shows it
            dropped.append({"searched": searched, "reason": f"{type(problem).__name__}: {problem}"})
            continue
        if not verified.met:
            if progress:
                progress(f"Candidate {n} misses the goal: adjusting {goal.spec.repair} with the twin...")
            verified = _repair(goal, sur, verified, free, twin)
        candidates.append(verified)
    warnings = [f"the surrogate was trained with {w}" for w in surrogate.untrained_settings(stage, config)]
    for name in names:
        if name in surrogate.INPUTS[stage] and name not in free and name in limits:
            value = base[names.index(name)]
            if stage == 1 and name in ("n2_percent", "o2_percent") and value == 0:
                continue
            lo, hi = limits[name]
            if not lo <= value <= hi:
                warnings.append(f"{name} = {value:g} is fixed outside the surrogate's training range {lo:g}-{hi:g}")
    fixed_values = {n: (config[n] if n in config else float(base[names.index(n)])) for n in names if n not in free}
    if stage == 1:
        fixed_values["mixture"] = config.get("mixture", "Ar")
    else:
        fixed_values["bubble_gas"] = config.get("bubble_gas")
    return Recommendation(goal, stage, model_id, fixed_values, free, _rank(goal, candidates), dropped, int(len(xs)),
                          time.perf_counter() - started, warnings)


# ------------------------------------------------------------------------------------ what-if (FR14.6)
def what_if(stage: int, config: dict[str, Any], setting: str, value: Any) -> list[dict[str, Any]]:
    """Change one setting of the open configuration; both rows come from the twin (no surrogate)."""
    from plasma_twin.services import stage1, stage2
    changed = {**config, setting: value}
    problems = stage1.validate_config(changed) if stage == 1 else stage2.validate_config(changed)[0]
    if problems:
        raise ValueError("; ".join(f"{k}: {v}" for k, v in problems.items()))
    before, after = twin_outcome(stage, config), twin_outcome(stage, changed)
    rows = []
    for o in surrogate.OUTPUTS[stage]:
        rows.append({"output": o.label, "unit": o.unit, "current": before[o.name], "changed": after[o.name]})
    label, unit = COST_LABEL[stage]
    rows.append({"output": label, "unit": unit, "current": before["cost"], "changed": after["cost"]})
    return rows


# ------------------------------------------------------------------------------------ benchmark (AIQ-4)
def benchmark_goals() -> list[tuple[Goal, dict[str, Any], set[str]]]:
    """30 reachable goals: each target is the twin's own value at settings drawn with a fixed seed."""
    goals = []
    rng = np.random.default_rng(BENCHMARK_SEEDS[1])
    b = bounds(1)
    mixtures = load_envelope()["stage1"]["options"]["gas_mixtures"]
    for k in range(BENCHMARK_GOALS[1]):
        config = {**surrogate.training_defaults(1), "rf_power_w": float(rng.uniform(*b["rf_power_w"])),
                  "pressure_mbar": float(rng.uniform(*b["pressure_mbar"])), "ar_flow_sccm": float(rng.uniform(*b["ar_flow_sccm"])),
                  "mixture": str(mixtures[int(rng.integers(len(mixtures)))]),
                  "n2_percent": float(rng.uniform(*b["n2_percent"])), "o2_percent": float(rng.uniform(*b["o2_percent"]))}
        twin = surrogate.twin_outputs(1, config)
        objective, output = ("ne_target", "ne_m3") if k < BENCHMARK_GOALS[1] // 2 else ("tgas_target", "tgas_k")
        goals.append((Goal(objective, target=float(twin[output])), config, set()))
    rng = np.random.default_rng(BENCHMARK_SEEDS[2])
    b = bounds(2)
    gases = load_envelope()["stage2"]["options"]["bubble_gas"]
    for _ in range(BENCHMARK_GOALS[2]):
        drawn = {k: float(rng.uniform(*b[k])) for k in ("power_w", "frequency_khz", "width_us", "o2_flow_sccm",
                                                         "water_temperature_c", "treatment_time_min", "water_volume_ml", "water_ph")}
        share = float(10 ** rng.uniform(np.log10(b["power_share"][0]), np.log10(b["power_share"][1])))
        gap = float(load_envelope()["stage2"]["options"]["electrode_gap_mm"][int(rng.integers(3))])
        gas = str(gases[int(rng.integers(len(gases)))])
        config = {**surrogate.training_defaults(2), **drawn, "power_share": share, "gap_mm": gap, "bubble_gas": gas}
        twin = surrogate.twin_outputs(2, config)
        goals.append((Goal("lr_least_energy", target=float(twin["log_reduction"])), config, set(WATER)))
    return goals


def run_benchmark(models: dict[int, tuple[surrogate.Surrogate, str]],
                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Every benchmark goal through the recommender; the success rate with and without the twin repair."""
    rows = []
    goals = benchmark_goals()
    for k, (goal, config, fixed) in enumerate(goals, start=1):
        if progress:
            progress(f"Benchmark goal {k} of {len(goals)}: {goal.describe()}")
        sur, model_id = models[goal.stage]
        found = recommend(goal, sur, config, fixed, model_id)
        best = found.best
        rows.append({"goal": k, "stage": goal.stage, "objective": goal.objective, "target": goal.target,
                     "met": found.reachable, "met_without_repair": found.reachable_without_repair,
                     "twin_value": best.value if best else None, "cost": best.cost if best else None,
                     "repair_runs": best.repair_runs if best else 0, "seconds": found.seconds,
                     "candidates": len(found.candidates), "dropped": len(found.dropped),
                     "drawn_cost": cost_of(goal.stage, config),
                     "cost_not_above_drawn": bool(best is not None and best.met and best.cost <= cost_of(goal.stage, config) * (1 + 1e-9))})
    summary: dict[str, Any] = {"goals": len(rows), "met": sum(r["met"] for r in rows),
                               "met_without_repair": sum(r["met_without_repair"] for r in rows),
                               "longest_seconds": max(r["seconds"] for r in rows),
                               "models": {str(s): m[1] for s, m in models.items()}}
    summary["success_rate"] = summary["met"] / summary["goals"]
    summary["success_rate_without_repair"] = summary["met_without_repair"] / summary["goals"]
    stage2 = [r for r in rows if r["stage"] == 2]
    summary["stage2_energy_not_above_drawn"] = f"{sum(r['cost_not_above_drawn'] for r in stage2)}/{len(stage2)}"
    for objective in sorted({r["objective"] for r in rows}):
        part = [r for r in rows if r["objective"] == objective]
        summary[f"{objective}_met"] = f"{sum(r['met'] for r in part)}/{len(part)}"
        summary[f"{objective}_met_without_repair"] = f"{sum(r['met_without_repair'] for r in part)}/{len(part)}"
    return {"summary": summary, "rows": rows}


def save_benchmark(result: dict[str, Any]) -> None:
    path = datasets.data_dir() / BENCHMARK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")


def load_benchmark() -> dict[str, Any] | None:
    path = datasets.data_dir() / BENCHMARK_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_surrogate(stage: int) -> tuple[surrogate.Surrogate, str]:
    """The current XGBoost surrogate of a stage (the Phase 11 default), or ValueError when there is none."""
    from plasma_twin.ai.registry import Registry
    cards = surrogate.current_models(stage)
    if not cards:
        raise ValueError(f"no current Stage {stage} surrogate: train one on the AI training screen")
    model, _ = Registry().load(cards[0].model_id)
    return model, cards[0].model_id
