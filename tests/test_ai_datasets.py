"""AI datasets from the twin (Phase 9, FR16.1, AIQ-5, CON-10)."""
import numpy as np
import pandas as pd
import pytest

from plasma_twin.ai import datasets
from plasma_twin.reference.loaders import DataStatus, check_reference_data

needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in check_reference_data().values()),
                                reason="the LXCat and NIST files have not been downloaded here")
SETTINGS = datasets.load_settings()


def test_settings_are_locked_with_a_date_and_seeds() -> None:
    assert SETTINGS["lock"]["date"] == "2026-11-04"
    assert all(isinstance(SETTINGS[k]["seed"], int) for k in ("stage1", "stage2", "faults", "splits"))
    assert datasets.dataset_id(1) != datasets.dataset_id(2)


def test_same_seed_gives_the_same_plan() -> None:
    assert datasets.stage1_plan(SETTINGS, 40) == datasets.stage1_plan(SETTINGS, 40)
    assert datasets.stage2_plan(SETTINGS, 40) == datasets.stage2_plan(SETTINGS, 40)


def test_every_row_is_inside_the_envelope() -> None:
    from plasma_twin.services import stage1, stage2
    for row in datasets.stage1_plan(SETTINGS, 200):
        config = {**stage1.default_config(), **{k: row[k] for k in ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture",
                                                                    "n2_percent", "o2_percent")}}
        assert stage1.validate_config(config) == {}, row
    for row in datasets.stage2_plan(SETTINGS, 200):
        problems, warnings = stage2.validate_config({**stage2.default_config(), **{k: v for k, v in row.items() if k != "index"}})
        assert problems == {} and warnings == [], row


def test_faults_are_half_the_runs_and_the_five_types_equally() -> None:
    plan = datasets.stage1_plan(SETTINGS, 1200)
    counts = pd.Series([r["fault"] for r in plan]).value_counts()
    assert counts["none"] == 600
    assert all(counts[f] == 120 for f in datasets.FAULT_TYPES)
    for r in plan:
        if r["fault"] == "power_error":
            assert 15 <= abs(r["fault_magnitude"]) <= 40


def test_region_split_really_excludes_the_held_out_corner() -> None:
    for stage, plan in ((1, datasets.stage1_plan(SETTINGS, 400)), (2, datasets.stage2_plan(SETTINGS, 400))):
        frame = pd.DataFrame(plan)
        train, test = datasets.split(frame, stage, "region")
        held = datasets.in_region(frame, stage)
        assert held[test].all() and not held[train].any() and len(test) > 0
        train, test = datasets.split(frame, stage, "random")
        assert len(set(train) & set(test)) == 0 and len(test) == 80


def test_contamination_flattens_the_probe_curve() -> None:
    """A series resistance makes the current rise more slowly with the applied voltage."""
    v = np.linspace(-20, 50, 141)
    i = 0.02 / (1 + np.exp(-(v - 10) / 2))
    contaminated = datasets._contaminated(v, i, 1000.0, v)
    assert np.all(contaminated <= i + 1e-15)
    assert np.max(np.gradient(contaminated, v)) < 0.5 * np.max(np.gradient(i, v))


@needs_data
def test_same_seed_gives_identical_rows() -> None:
    a, _ = datasets.build(1, runs=4)
    b, _ = datasets.build(1, runs=4, workers=2)  # the number of processes must not matter
    pd.testing.assert_frame_equal(a, b)


@needs_data
@pytest.mark.parametrize("fault", ["wavelength_shift", "air_leak", "power_error", "rf_failure", "probe_contamination"])
def test_each_fault_changes_the_data_as_intended(fault) -> None:
    clean = {**datasets.stage1_plan(SETTINGS, 1200)[2], "fault": "none", "fault_magnitude": 0.0}  # row 2 is fault-free
    magnitude = {"wavelength_shift": 0.15, "air_leak": 2.0, "power_error": 30.0, "rf_failure": 15.0, "probe_contamination": 1500.0}[fault]
    faulty = {**clean, "fault": fault, "fault_magnitude": magnitude}
    before, after = datasets.stage1_row(clean, SETTINGS), datasets.stage1_row(faulty, SETTINGS)
    lines = [k for k in before if k.startswith("line_")]
    iv = [k for k in before if k.startswith("iv_")]
    line_change = np.max(np.abs(np.array([after[k] for k in lines]) / np.array([before[k] for k in lines]) - 1))
    iv_change = np.max(np.abs(np.array([after[k] for k in iv]) - np.array([before[k] for k in iv])))
    if fault == "wavelength_shift":  # the lines move out of their integration windows; the plasma is untouched
        assert line_change > 0.5 and after["te_ev"] == before["te_ev"]
    elif fault == "power_error":  # more power, more plasma, but the record still says the nominal power
        assert after["ne_m3"] > 1.1 * before["ne_m3"] and after["rf_power_w"] == before["rf_power_w"]
    elif fault == "air_leak":  # the gas changes the plasma, but the record still says the leak-free mixture
        assert after["mixture"] == before["mixture"] and after["ne_m3"] != before["ne_m3"]
    else:  # probe faults change the I-V curve, not the plasma or the spectrum
        assert after["te_ev"] == before["te_ev"] and iv_change > 1e-4
