"""Spectrum -> T_e, n_e, T_gas with conformal intervals (Phase 10, Core Module 2.1, AIQ-1, AIQ-3).

The pass marks were fixed in BUILD_STEPS.md (Phase 10 rules) before any model was trained. Two of them
were NOT met on the locked dataset; those tests are marked xfail(strict=True) with the measured value,
so they stay visible in every run, and they would fail loudly if the result ever changed.
"""
import time

import numpy as np
import pytest

from plasma_twin.ai import datasets, inference
from plasma_twin.reference.loaders import DataStatus, check_reference_data

needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in check_reference_data().values()),
                                reason="the LXCat and NIST files have not been downloaded here")
LOCKED = datasets.dataset_id(1)
needs_dataset = pytest.mark.skipif(not (datasets.DATA_DIR / f"{LOCKED}.parquet").exists(),
                                   reason="the locked Stage 1 dataset has not been built here (scripts/build_ai_datasets.py)")


# ------------------------------------------------------------------------------------ no reference data needed
def test_calibration_split_is_seeded_and_75_25() -> None:
    fit, calibration = inference.calibration_split(400)
    again = inference.calibration_split(400)
    assert len(fit) == 300 and len(calibration) == 100 and not set(fit) & set(calibration)
    assert np.array_equal(fit, again[0]) and np.array_equal(calibration, again[1])


def test_conformal_intervals_cover_about_90_percent_on_exchangeable_data() -> None:
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, (1200, 3))
    y = np.column_stack([x @ [1.0, -0.5, 0.2] + rng.normal(0, 0.1, 1200)] * 3)
    model = inference.fit_conformal("xgboost", x[:800], y[:800], [700.0, 750.0, 800.0])
    _, low, high = model.predict(x[800:])
    coverage = np.mean((y[800:] >= low) & (y[800:] <= high), axis=0)
    assert np.all((coverage >= 0.85) & (coverage <= 0.96)), coverage


def test_range_check_allows_the_margin_and_withholds_beyond_it() -> None:
    model = inference.ConformalModel("xgboost", [], np.array([0.0, -1.0]), np.array([1.0, 0.0]), [700.0, 750.0])
    inside = np.array([[1.09, -1.09], [0.5, -0.5]])
    outside = np.array([[1.11, -0.5], [0.5, 0.2]])
    assert not model.out_of_range(inside).any() and model.out_of_range(outside).all()


def test_scipy_bootstrap_interval_is_below_zero_for_a_better_model() -> None:
    rng = np.random.default_rng(0)
    baseline = np.abs(rng.normal(0, 1.0, 200))
    low, high = inference.bootstrap_interval(0.5 * baseline, baseline)
    assert low < high < 0
    low, high = inference.bootstrap_interval(baseline, baseline)
    assert low <= 0 <= high


# ------------------------------------------------------------------------------------ the locked dataset
@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """Both Phase 10 models trained on the locked dataset into a temporary registry (physics fits from the cache)."""
    from plasma_twin.ai.registry import Registry
    folder = tmp_path_factory.mktemp("phase10")
    registry = Registry(folder / "models", folder / "mlruns")
    frame, card = datasets.load(LOCKED)
    cards = {a: inference.train(a, frame, card, registry) for a in inference.ALGORITHMS}
    return registry, cards


@needs_data
@needs_dataset
@pytest.mark.parametrize("algorithm", inference.ALGORITHMS)
def test_ne_interval_coverage_is_at_least_85_percent_on_the_random_split(trained, algorithm) -> None:
    assert trained[1][algorithm].metrics["random"]["model"]["ne_coverage"] >= 0.85


@needs_data
@needs_dataset
@pytest.mark.xfail(strict=True, reason="measured 5 Nov 2026: T_e coverage 84 % (Random Forest) and 80 % (XGBoost) on the "
                                       "locked random split; 30 other splits average 90 % (journey, Phase 10)")
@pytest.mark.parametrize("algorithm", inference.ALGORITHMS)
def test_te_interval_coverage_is_at_least_85_percent_on_the_random_split(trained, algorithm) -> None:
    assert trained[1][algorithm].metrics["random"]["model"]["te_coverage"] >= 0.85


@needs_data
@needs_dataset
@pytest.mark.xfail(strict=True, reason="measured 5 Nov 2026: p = 0.49 (Random Forest) and 0.51 (XGBoost) for T_e against "
                                       "the ridge; the trees are no better than the ridge on these features")
@pytest.mark.parametrize("algorithm", inference.ALGORITHMS)
def test_tree_ensemble_beats_the_ridge_baseline_significantly(trained, algorithm) -> None:
    assert trained[1][algorithm].metrics["random"]["p_value_te_vs_ridge"] < 0.05


@needs_data
@needs_dataset
@pytest.mark.parametrize("algorithm", inference.ALGORITHMS)
def test_results_are_reported_for_both_splits_against_ridge_and_physics(trained, algorithm) -> None:
    metrics = trained[1][algorithm].metrics
    for split in ("random", "region"):
        result = metrics[split]
        assert {"te_mae", "ne_median_relative_error", "te_coverage", "ne_coverage", "withheld_share"} <= set(result["model"])
        assert result["baseline"] and result["physics"]["rows"] == result["test_rows"]
        for name in ("te_vs_ridge", "ne_vs_ridge", "te_vs_physics", "ne_vs_physics", "tgas_vs_mean"):
            assert 0 < result[f"p_value_{name}"] <= 1 and result[f"ci_{name}_low"] <= result[f"ci_{name}_high"]
    runs = trained[0].runs()
    assert "metrics.random.model.te_coverage" in runs.columns and "metrics.region.p_value_te_vs_physics" in runs.columns


@needs_data
@needs_dataset
def test_ai_is_significantly_better_than_the_physics_line_ratio_fit(trained) -> None:
    """Recorded, not a plan requirement: the two-parameter physics fit runs away at low pressure."""
    for card in trained[1].values():
        assert card.metrics["random"]["p_value_te_vs_physics"] < 0.05


def _open_plasma_spectrum(**settings):
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.services import stage1
    from plasma_twin.stage1.global_model import solve
    result = solve(stage1.to_inputs({**stage1.default_config(), "eedf": "Druyvesteyn"}))
    values = {"fwhm_nm": 0.005, "start_nm": 694.0, "end_nm": 855.0, "noise_percent": 1.0, **settings}
    return result, spectrum_for(result, SpectrometerSettings(**values))


@needs_data
@needs_dataset
def test_estimate_on_a_twin_spectrum_has_intervals_and_takes_under_a_second(trained) -> None:
    registry, cards = trained
    model, _ = registry.load(cards["xgboost"].model_id)
    result, spectrum = _open_plasma_spectrum()
    model.predict(np.zeros((1, len(model.wavelengths_nm))))  # first call loads the libraries
    started = time.perf_counter()
    found = inference.estimate(spectrum, model)
    assert time.perf_counter() - started <= 1.0
    assert not found.withheld, found.reasons
    assert found.te_interval_ev[0] <= found.te_ev <= found.te_interval_ev[1]
    assert found.ne_interval_m3[0] <= found.ne_m3 <= found.ne_interval_m3[1]
    assert abs(found.te_ev - result.te_ev) < 0.5 and 0.5 < found.ne_m3 / result.ne_center_m3 < 2


@needs_data
@needs_dataset
def test_out_of_range_input_is_withheld(trained) -> None:
    registry, cards = trained
    model, _ = registry.load(cards["random_forest"].model_id)
    _, short = _open_plasma_spectrum(start_nm=740.0, end_nm=855.0)
    found = inference.estimate(short, model)
    assert found.withheld and any("outside the spectrum's wavelength range" in r for r in found.reasons)
    _, spectrum = _open_plasma_spectrum()
    strong = spectrum.intensity.copy()
    strong[np.abs(spectrum.wavelength_nm - 750.387) < 0.05] *= 50  # one line far brighter than any run in the envelope
    from plasma_twin.oes.spectrum import Spectrum
    odd = Spectrum(spectrum.wavelength_nm, strong, {}, spectrum.settings, spectrum.gas_temperature_k)
    found = inference.estimate(odd, model)
    assert found.withheld and "outside the training range" in found.reasons[0] and np.isnan(found.te_ev)


def test_settings_held_fixed_in_training_are_named_when_they_differ() -> None:
    from plasma_twin.services import stage1
    assert inference.untrained_settings({**stage1.default_config(), "eedf": "Druyvesteyn"}) == []
    assert inference.untrained_settings({**stage1.default_config(), "eedf": "Maxwellian", "electrode_gap_cm": 3.0}) == [
        "eedf = Druyvesteyn", f"electrode_gap_cm = {stage1.default_config()['electrode_gap_cm']}"]
