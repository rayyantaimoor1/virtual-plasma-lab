"""Water side of Stage 2 (Phase 7, FR9.2, FR9.5)."""
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_itikawa_h2o")),
                                reason="the LXCat files have not been downloaded here")


@pytest.fixture(scope="module")
def run():
    from plasma_twin.services import stage2
    config = {**stage2.default_config(), "treatment_time_min": 30.0}
    return stage2.run(config), config


@needs_data
def test_temperature_rise_is_energy_over_mass_times_heat_capacity(run) -> None:
    from plasma_twin.reference.loaders import load_stage2_constants
    result, config = run
    c = load_stage2_constants()
    mass = c["water_density_298"] * config["water_volume_ml"] * 1e-6
    heat = c["water_cp_molar"] / (c["water_molar_mass"] / 1000)
    expected = config["power_w"] * config["treatment_time_min"] * 60 / (mass * heat)
    assert result.liquid.temperature_after_c - result.liquid.temperature_before_c == pytest.approx(expected)


@needs_data
def test_dissolved_ozone_approaches_its_steady_state(run) -> None:
    w = run[0].liquid
    steady = w.kla_per_s * w.ozone_saturation_mg_l / (w.kla_per_s + w.decay_per_s)
    assert w.ozone_mg_l[-1] == pytest.approx(steady, rel=0.01)  # 30 min is far longer than 1 / k_La (6 min)
    assert w.ozone_mg_l[-1] < w.ozone_saturation_mg_l


@needs_data
def test_h2o2_grows_linearly_and_ph_is_unchanged(run) -> None:
    w = run[0].liquid
    assert w.h2o2_mmol_l[120] == pytest.approx(w.h2o2_mmol_l[-1] / 2, rel=1e-9)
    assert w.ph_after == w.ph_before and w.conductivity_after_us_cm == w.conductivity_before_us_cm


def test_transfer_coefficient_interpolates_gao() -> None:
    from plasma_twin.stage2.liquid import transfer_coefficient
    assert transfer_coefficient(100.0) == pytest.approx(2.95e-3)
    assert transfer_coefficient(350.0) == pytest.approx((2.95e-3 + 7.47e-3) / 2)
