"""Tests for the probe analysis (Phase 5): V_f, V_p, T_e, n_e, lambda_D, OML check, failure steps."""
import time

import numpy as np
import pytest

from plasma_twin.probe.analysis import ProbeAnalysisError, analyse, analyse_curve
from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
from plasma_twin.probe.retardation import probe_style_te
from plasma_twin.reference.loaders import DataStatus, check_reference_data

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


@pytest.fixture(scope="module", params=["Druyvesteyn", "Maxwellian"])
def model(request):
    from plasma_twin.stage1.global_model import default_inputs, solve
    result = solve(default_inputs(eedf=request.param))
    return result, plasma_from(result)


@needs_lxcat
def test_noise_free_fine_sweep_recovers_model_te_and_ne(model) -> None:
    """ACC-2: within +/-10 %. Uses a 0.1 V step (the next test covers the default 0.5 V step)."""
    result, plasma = model
    a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0, sweep_step_v=0.1)))
    assert a.eepf_reliable
    assert a.effective_temperature_ev == pytest.approx(result.te_ev, rel=0.10)
    assert a.electron_density_m3 == pytest.approx(result.ne_center_m3, rel=0.10)
    assert a.plasma_potential_v == pytest.approx(plasma.plasma_potential_v, abs=0.3)
    assert a.slope_temperature_ev == pytest.approx(probe_style_te(result.te_ev, plasma.shape), rel=0.05)


@needs_lxcat
def test_default_half_volt_step_underestimates_density(model) -> None:
    """Recorded finding, not a pass mark chosen afterwards: at 0.5 V the 5-point smoothing spans +/-1 V
    around the sharp knee at V_p, which pulls V_p down about 0.5 V and n_e(EEPF) 14 % low. T_eff stays
    within 10 %, and the saturation density (no second derivative) within 10 %."""
    result, plasma = model
    a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0)))
    assert a.electron_density_m3 / result.ne_center_m3 - 1 == pytest.approx(-0.14, abs=0.02)
    assert a.effective_temperature_ev == pytest.approx(result.te_ev, rel=0.10)
    assert a.saturation_density_m3 == pytest.approx(result.ne_center_m3, rel=0.10)


@needs_lxcat
def test_noisy_curve_flags_the_eepf_but_keeps_robust_values(model) -> None:
    result, plasma = model
    a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=1.0, seed=3)))
    assert not a.eepf_reliable
    assert any("EEPF unreliable" in w for w in a.warnings)
    assert a.saturation_density_m3 == pytest.approx(result.ne_center_m3, rel=0.20)
    assert a.plasma_potential_v == pytest.approx(plasma.plasma_potential_v, abs=1.0)


@needs_lxcat
def test_oml_check_reports_our_densities_as_outside_oml(model) -> None:
    """At ~3e16 m^-3 lambda_D ~ 0.07 mm < r_p = 0.195 mm, so OML is formally invalid (E12)."""
    _, plasma = model
    a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0)))
    assert a.radius_over_debye > 1 and not a.oml_valid
    assert any("E12" in w for w in a.warnings)


@needs_lxcat
def test_generation_and_analysis_take_at_most_two_seconds(model) -> None:
    _, plasma = model
    start = time.perf_counter()
    analyse_curve(generate(plasma, ProbeSettings.defaults()))
    assert time.perf_counter() - start <= 2.0  # PER-3


def test_failure_reports_the_step() -> None:
    """E11: a curve that never crosses zero fails at the first step, and says so."""
    v = np.linspace(-20, 50, 141)
    with pytest.raises(ProbeAnalysisError) as error:
        analyse(v, np.full_like(v, 1e-3), 0.195, 5)
    assert error.value.step == "floating potential"


def test_point_noise_sees_noise_but_not_smooth_misfit() -> None:
    from plasma_twin.probe.analysis import point_noise
    rng = np.random.default_rng(0)
    x = np.linspace(0, 1, 2000)
    assert point_noise(1e-3 * x**2 + 5e-4 * np.sin(3 * x)) < 1e-6
    assert point_noise(rng.normal(0, 2e-5, 2000)) == pytest.approx(2e-5, rel=0.05)


@needs_lxcat
def test_oml_ion_density_agrees_with_the_model_within_the_comparison_tolerance(model) -> None:
    """FR6.6: n_e from the OML ion current. Judged by the project's +/-30 % agreement rule (Phase 5)."""
    from plasma_twin.compare.diagnostics import within_tolerance
    result, plasma = model
    for noise in (0.0, ProbeSettings.defaults().noise_percent):
        a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=noise)))
        assert within_tolerance((a.ion_density_m3 - result.ne_center_m3) / result.ne_center_m3), noise


@needs_lxcat
def test_noise_free_oml_ion_density_inverts_the_ion_current(model) -> None:
    """Same 10 % bound as the other noise-free checks above; the mixture mass is the OML-equivalent one."""
    result, plasma = model
    a = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0)))
    assert a.ion_density_m3 == pytest.approx(result.ne_center_m3, rel=0.10)
