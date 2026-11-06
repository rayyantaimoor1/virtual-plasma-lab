"""Physics-relationship anomaly detection (Phase 12, Core Module 2.2, AIQ-2, FR13, E24).

The pass marks were fixed in BUILD_STEPS.md (Phase 12 rules, amended before any detector was trained).
"""
import numpy as np
import pytest

from plasma_twin.ai import anomaly, datasets
from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.storage.anomaly_log import AnomalyLog

needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in check_reference_data().values()),
                                reason="the LXCat and NIST files have not been downloaded here")
needs_dataset = pytest.mark.skipif(not (datasets.DATA_DIR / f"{datasets.dataset_id(1)}.parquet").exists(),
                                   reason="the locked Stage 1 dataset has not been built here")


# ------------------------------------------------------------------------------------ no reference data needed
def test_severity_uses_the_versioned_thresholds() -> None:
    assert anomaly.thresholds() == (0.60, 0.75)
    assert [anomaly.severity(s) for s in (0.59, 0.60, 0.74, 0.75)] == ["Normal", "Warning", "Warning", "Critical"]


def test_oes_residuals_are_zero_for_a_matching_spectrum_and_see_a_tilt_and_a_brightness_change() -> None:
    wavelengths = np.linspace(700, 850, 12)
    expected = np.linspace(1.0, 0.2, 12)
    assert np.allclose(anomaly.oes_residuals(expected, expected, wavelengths)[0], 0, atol=1e-12)
    low, high, _ = anomaly._window()
    x = (wavelengths - (low + high) / 2) / ((high - low) / 2)
    tilted = 2.0 * expected * 10 ** (0.05 * x)
    intensity, tilt, pattern = anomaly.oes_residuals(tilted, expected, wavelengths)[0]
    assert intensity > 0.29 and tilt == pytest.approx(0.05, abs=1e-9) and pattern == pytest.approx(0, abs=1e-9)


def test_pattern_ignores_lines_weaker_than_5_percent_of_the_expected_strongest() -> None:
    wavelengths = np.linspace(700, 850, 6)
    expected = np.array([1.0, 0.5, 0.3, 0.2, 0.01, 0.01])
    noisy = expected.copy()
    noisy[4:] = [0.05, 0.0]  # weak lines swamped by noise
    assert anomaly.oes_residuals(noisy, expected, wavelengths)[0][2] == pytest.approx(0, abs=1e-12)


def test_probe_residuals_see_a_shifted_knee_and_a_lower_saturation() -> None:
    v = np.linspace(-20, 40, 241)
    expected = 0.02 / (1 + np.exp(-(v - 10) / 2)) - 0.0002
    assert np.allclose(anomaly.probe_residuals(v, expected, expected, np.array([12.0]))[0], 0, atol=1e-12)
    shifted = 0.018 / (1 + np.exp(-(v - 13) / 2)) - 0.0002
    amplitude, position, knee, rms = anomaly.probe_residuals(v, shifted, expected, np.array([12.0]))[0]
    assert amplitude < -0.04 and position > 2.5 and knee < 0 and rms > 0.05


def test_mcnemar_needs_runs_only_the_detector_catches() -> None:
    detector = np.array([True] * 30 + [False] * 2)
    baseline = np.array([False] * 20 + [True] * 12)
    assert anomaly.mcnemar_p(detector, baseline) < 0.001
    assert anomaly.mcnemar_p(baseline, baseline) == 1.0


def test_score_scaling_puts_a_typical_clean_run_at_one_half_and_the_95th_percentile_at_the_warning() -> None:
    rng = np.random.default_rng(3)
    clean = rng.normal(size=(800, 3))
    detector = anomaly.fit_detector(clean, ("a", "b", "c"))
    raw = detector.raw(clean[:5])
    assert np.allclose(detector.score(clean[:5]), np.clip(0.5 + 0.1 * (raw - detector.median) / (detector.q95 - detector.median), 0, 1))
    far = detector.score(np.array([[6.0, 6.0, 6.0]]))[0]
    assert far >= 0.75 and anomaly.severity(far) == "Critical"
    contributions = detector.contributions(np.array([[0.0, 0.0, 8.0]]))[0]
    assert np.argmax(contributions) == 2


def test_anomaly_log_records_reviews_and_exports(tmp_path) -> None:
    log = AnomalyLog(tmp_path / "log.db")
    first = log.add("S-0001", "full", "m-1", 0.81, "Critical", "probe knee shape", "passed")
    log.add("open plasma", "full", "m-1", 0.42, "Normal", "none", "passed")
    log.mark_reviewed(first)
    entries = log.list()
    assert [e.source for e in entries] == ["S-0001", "open plasma"] and entries[0].reviewed and entries[0].reviewed_at
    assert log.to_csv().splitlines()[0].startswith("id,checked_at,source") and "S-0001" in log.to_csv()
    with pytest.raises(ValueError):
        log.mark_reviewed(99)
    note = "'); DROP TABLE anomaly_log; --"
    log.add(note, "full", "m-1", 0.5, "Normal", note, "passed")  # stored as text (SEC-4)
    assert log.list()[-1].source == note


# ------------------------------------------------------------------------------------ the locked dataset
@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """The detector trained on the locked dataset into a temporary registry (the twin's expectation from the cache)."""
    from plasma_twin.ai.registry import Registry
    folder = tmp_path_factory.mktemp("phase12")
    registry = Registry(folder / "models", folder / "mlruns")
    frame, card = datasets.load(datasets.dataset_id(1))
    model_card = anomaly.train(frame, card, registry)
    model, _ = registry.load(model_card.model_id)
    return model_card, model


@needs_data
@needs_dataset
def test_recall_is_at_least_90_percent_at_no_more_than_5_percent_false_alarms(trained) -> None:
    result = trained[0].metrics["random"]["model"]
    assert result["recall"] >= 0.90 and result["false_alarm_rate"] <= 0.05, result


@needs_data
@needs_dataset
def test_recall_is_significantly_above_the_range_check(trained) -> None:
    result = trained[0].metrics["random"]
    assert result["model"]["recall"] > result["baseline"]["recall"] and result["p_value_vs_range_check"] < 0.05


@needs_data
@needs_dataset
def test_every_fault_type_and_both_splits_are_recorded(trained) -> None:
    for split in ("random", "region"):
        result = trained[0].metrics[split]
        for who in ("model", "baseline", "oes_only", "probe_only"):
            assert {f"recall_{f}" for f in datasets.FAULT_TYPES} <= set(result[who])


@needs_data
@needs_dataset
def test_a_run_with_all_values_in_range_but_the_physics_broken_is_caught(trained) -> None:
    """+30 % power while the nominal power is recorded: a normal-looking run that the twin does not expect."""
    import pandas as pd
    from plasma_twin.ai.training import anomaly_features
    settings = datasets.load_settings()
    row = next(r for r in datasets.stage1_plan(settings, 1200)
               if r["fault"] == "none" and 40 <= r["rf_power_w"] <= 60 and 0.2 <= r["pressure_mbar"] <= 0.35)
    frame = pd.DataFrame([datasets.stage1_row({**row, "fault": "power_error", "fault_magnitude": 30.0}, settings)])
    model = trained[1]
    assert not model.range_check.flag(anomaly_features(frame))[0]  # the range check sees nothing wrong
    expected = anomaly.expected_table(frame, datasets.load(datasets.dataset_id(1))[1], workers=1, cache=False)
    score = model.detectors["full"].score(anomaly.dataset_residuals(frame, expected).to_numpy())[0]
    assert anomaly.severity(score) != "Normal"


@needs_data
@needs_dataset
def test_the_default_plasma_with_default_instruments_is_rated_normal(trained) -> None:
    from plasma_twin.services import stage1
    found = anomaly.assess_stage1_config(trained[1], stage1.default_config())
    assert found.severity == "Normal" and found.range_check == "passed", found


@needs_data
@needs_dataset
def test_rf_left_on_the_probe_is_flagged_with_a_probe_cause(trained) -> None:
    from plasma_twin.probe.iv_model import ProbeSettings
    from plasma_twin.services import stage1
    found = anomaly.assess_stage1_config(trained[1], stage1.default_config(), probe=ProbeSettings.defaults(rf_amplitude_v=20.0))
    assert found.severity != "Normal" and found.likely_residual.startswith("iv_"), found
