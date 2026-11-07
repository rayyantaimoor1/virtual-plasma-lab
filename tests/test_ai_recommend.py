"""Counterfactual recommendations verified by the twin (Phase 13, Core Module 2.4, AIQ-4, PER-10, FR14, E25, E26).

The pass marks were fixed in BUILD_STEPS.md (Phase 13 rules) before any recommendation was made.
"""
import json
import time

import numpy as np
import pytest

from plasma_twin.ai import datasets
from plasma_twin.ai import recommend as rc
from plasma_twin.ai import surrogate as sg
from plasma_twin.reference.loaders import DataStatus, check_reference_data

needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in check_reference_data().values()),
                                reason="the LXCat and NIST files have not been downloaded here")
needs_tables = pytest.mark.skipif(not ((datasets.DATA_DIR / f"{datasets.dataset_id(1)}-twin.parquet").exists()
                                       and (datasets.DATA_DIR / f"{datasets.dataset_id(2)}.parquet").exists()),
                                  reason="the surrogate training tables have not been built here (scripts/train_surrogates.py)")


class LinearSurrogate:
    """A stand-in surrogate for Stage 2: log reduction = treatment time (min), every other output 1."""
    stage = 2
    outputs = sg.OUTPUTS[2]

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(x)
        out = np.ones((len(x), len(self.outputs)))
        out[:, [o.name for o in self.outputs].index("log_reduction")] = x[:, sg.STAGE2_INPUTS.index("treatment_time_min")]
        return out


def linear_twin(offset: float = 0.0):
    """A stand-in twin that agrees with LinearSurrogate, shifted by `offset` log."""
    def twin(stage, config):
        return {**{o.name: 1.0 for o in sg.OUTPUTS[2]}, "log_reduction": config["treatment_time_min"] + offset,
                "cost": rc.cost_of(2, config)}
    return twin


def default2():
    from plasma_twin.services import stage2
    return stage2.default_config()


# ------------------------------------------------------------------------------------ no reference data needed
def test_energy_per_litre_is_power_times_time_over_volume() -> None:
    assert rc.energy_kj_per_l({"power_w": 100.0, "treatment_time_min": 1.0, "water_volume_ml": 500.0}) == pytest.approx(12.0)


def test_goals_are_checked_before_any_search() -> None:
    for bad in (rc.Goal("ne_target"), rc.Goal("ne_target", -1.0), rc.Goal("line_max", line="line_1.000"),
                rc.Goal("lr_budget", budget_kj_l=0.0), rc.Goal("nonsense", 1.0)):
        with pytest.raises(ValueError):
            bad.check()


def test_the_search_bounds_stay_inside_the_envelope_and_the_training_range() -> None:
    b2 = rc.bounds(2)
    assert b2["width_us"] == (2.0, 40.0) and b2["power_share"] == (0.01, 0.10) and b2["gap_mm"] == (1, 3)
    assert 40e-6 * 10e3 < 0.5  # the widest pulse at the highest frequency is never blocked or warned (E5)
    assert "power_share" not in rc.searchable(2, default2())  # always fixed: the model's uncertainty, not a knob
    from plasma_twin.services import stage1
    assert rc.searchable(1, {**stage1.default_config(), "mixture": "Ar+O2"})[-1] == "o2_percent"
    assert "n2_percent" not in rc.searchable(1, {**stage1.default_config(), "mixture": "Ar+O2"})


def test_meeting_the_aim_always_beats_missing_it() -> None:
    goal = rc.Goal("lr_least_energy", 3.0)
    scores = rc._search_scores(goal, np.array([3.2, 3.05, 2.0]), np.array([1000.0, 0.1, 0.1]), (0.0, 1000.0))
    assert scores[0] <= 1.0 < scores[1] < scores[2]  # costly but meets 3 + 0.1 < cheap but short


def test_the_aim_never_asks_for_more_than_the_one_cell_cap() -> None:
    """Amendment: at a target on the cap, a point the surrogate puts just below the cap still meets the aim."""
    goal = rc.Goal("lr_least_energy", 7.875)
    cap = rc.one_cell_cap(150000.0, np.array([500.0, 500.0]))
    assert cap[0] == pytest.approx(7.8751, abs=1e-4)
    scores = rc._search_scores(goal, np.array([7.87, 7.80]), np.array([0.12, 0.12]), (0.0, 1000.0), cap)
    assert scores[0] <= 1.0 < scores[1]  # 7.87 >= cap - 0.05; 7.80 is not


def test_the_three_candidates_are_distinct() -> None:
    unit = np.array([[0.0, 0.0], [0.01, 0.0], [0.5, 0.5], [0.52, 0.5], [1.0, 1.0]])
    assert rc._distinct(np.arange(5), unit) == [0, 2, 4]


def test_every_shown_candidate_carries_its_twin_outcome() -> None:
    found = rc.recommend(rc.Goal("lr_least_energy", 3.0), LinearSurrogate(), default2(), twin=linear_twin())
    assert found.candidates and found.reachable
    for c in found.candidates:
        assert c.twin and c.value == c.twin["log_reduction"] and c.met == (c.value >= 3.0 - 0.01)
    best = found.best
    assert best.config["treatment_time_min"] == pytest.approx(3.1, abs=0.05) and best.config["power_w"] == pytest.approx(10.0, abs=0.1)
    assert json.loads(found.to_json())["candidates"][0]["twin"]["log_reduction"] == best.value


def test_a_candidate_whose_twin_run_fails_is_dropped_never_shown() -> None:
    def broken(stage, config):
        raise RuntimeError("solver did not converge")
    found = rc.recommend(rc.Goal("lr_least_energy", 3.0), LinearSurrogate(), default2(), twin=broken)
    assert found.candidates == [] and len(found.dropped) == 3 and not found.reachable and found.best is None
    assert "solver did not converge" in found.dropped[0]["reason"]


def test_the_twin_repair_adjusts_the_treatment_time_until_the_twin_agrees() -> None:
    found = rc.recommend(rc.Goal("lr_least_energy", 3.0), LinearSurrogate(), default2(), twin=linear_twin(offset=-1.0))
    best = found.best
    assert found.reachable and not found.reachable_without_repair
    assert 0 < best.repair_runs <= rc.REPAIR_RUNS and best.value >= 2.99 and best.config["treatment_time_min"] > 3.9


def test_no_repair_when_the_setting_is_fixed_so_the_goal_is_unreachable() -> None:
    fixed = rc.default_fixed(2) | {"treatment_time_min"}
    found = rc.recommend(rc.Goal("lr_least_energy", 3.0), LinearSurrogate(), default2(), fixed, twin=linear_twin(offset=-1.0))
    assert not found.reachable and all(c.repair_runs == 0 for c in found.candidates)


def test_a_species_without_kinetics_cannot_be_recommended_for() -> None:
    with pytest.raises(ValueError):
        rc.recommend(rc.Goal("lr_least_energy", 3.0), LinearSurrogate(), {**default2(), "organism": "S. aureus"})


# ------------------------------------------------------------------------------------ the real surrogates and twin
@pytest.fixture(scope="module")
def surrogates():
    """XGBoost surrogates fitted on the full training tables, as the registry's final models are."""
    found = {}
    for stage in (1, 2):
        table = sg.training_table(stage, workers=1)
        x, y = sg.features(stage, table.to_dict("records")), sg.learned_targets(stage, table)
        found[stage] = sg.fit(stage, "xgboost", x, y)
    return found


def defaults(stage):
    from plasma_twin.services import stage1, stage2
    return stage1.default_config() if stage == 1 else stage2.default_config()


@needs_data
@needs_tables
def test_the_benchmark_goals_are_met_for_at_least_90_percent(surrogates) -> None:
    result = rc.run_benchmark({1: (surrogates[1], "test"), 2: (surrogates[2], "test")})
    summary = result["summary"]
    assert summary["goals"] == 30 and summary["success_rate"] >= 0.90, summary
    assert {"success_rate_without_repair", "ne_target_met", "tgas_target_met", "lr_least_energy_met"} <= set(summary)


@needs_data
@needs_tables
@pytest.mark.parametrize("goal", [rc.Goal("ne_target", 1e18), rc.Goal("lr_least_energy", 9.0)], ids=["ne_1e18", "9_log_in_500_ml"])
def test_an_impossible_goal_is_reported_as_unreachable_with_the_closest_option(surrogates, goal) -> None:
    found = rc.recommend(goal, surrogates[goal.stage], defaults(goal.stage))
    assert not found.reachable and found.best is not None and found.best.twin


@needs_data
@needs_tables
@pytest.mark.parametrize("goal", [rc.Goal("ne_target", 2e16), rc.Goal("tgas_target", 303.5), rc.Goal("line_max", line="line_750.387"),
                                  rc.Goal("lr_least_energy", 3.0), rc.Goal("lr_budget", budget_kj_l=1.0)],
                         ids=lambda g: g.objective)
def test_one_recommendation_with_its_twin_runs_takes_at_most_60_seconds(surrogates, goal) -> None:
    started = time.perf_counter()
    found = rc.recommend(goal, surrogates[goal.stage], defaults(goal.stage))
    assert time.perf_counter() - started <= 60.0
    assert found.candidates and all(c.twin and c.value == c.twin[goal.output] for c in found.candidates)


@needs_data
@needs_tables
def test_three_log_e_coli_with_the_least_energy_is_confirmed_by_the_twin(surrogates) -> None:
    found = rc.recommend(rc.Goal("lr_least_energy", 3.0), surrogates[2], defaults(2))
    assert found.reachable and found.best.met and found.best.value >= 2.99
    assert found.best.cost < rc.energy_kj_per_l(defaults(2))  # cheaper than the default run (12 kJ/L)


@needs_data
def test_what_if_reports_the_twin_before_and_after() -> None:
    rows = rc.what_if(1, defaults(1), "rf_power_w", 80.0)
    ne = next(r for r in rows if r["output"].startswith("Electron density"))
    assert ne["changed"] > ne["current"]  # more power, more ionization (the global model's power balance)
    with pytest.raises(ValueError):
        rc.what_if(1, defaults(1), "rf_power_w", 500.0)  # outside the envelope
