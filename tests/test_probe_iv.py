"""Tests for the synthetic Langmuir probe curve (Phase 5)."""
import numpy as np
import pytest
from scipy import constants as codata

from plasma_twin.probe.iv_model import ProbePlasma, ProbeSettings, ProbeSettingsOutOfRange, generate
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE, MAXWELLIAN_SHAPE
from plasma_twin.stage1.rates import ARGON_MASS_KG

ARGON = {"Ar+": 3e16}
MASS = {"Ar+": ARGON_MASS_KG}


def plasma(shape: float = MAXWELLIAN_SHAPE, te: float = 2.0, vp: float = 10.0) -> ProbePlasma:
    return ProbePlasma(3e16, te, shape, ARGON, MASS, vp)


def test_maxwellian_retarding_current_is_an_exact_exponential() -> None:
    """Below V_p a Maxwellian gives I_e = I_e(V_p) exp(-(V_p - V)/T_e)."""
    curve = generate(plasma(), ProbeSettings.defaults(noise_percent=0.0))
    below = curve.voltage_v < 10.0
    expected = curve.electron_current_at_vp_a * np.exp(-(10.0 - curve.voltage_v[below]) / 2.0)
    assert np.allclose(curve.parts["electron"][below], expected, rtol=1e-4)


def test_current_at_vp_is_the_random_flux() -> None:
    """I_e(V_p) = A e n v_mean / 4 with v_mean = sqrt(8 e T / (pi m)) for a Maxwellian."""
    settings = ProbeSettings.defaults(noise_percent=0.0)
    curve = generate(plasma(), settings)
    v_mean = np.sqrt(8 * codata.e * 2.0 / (np.pi * codata.m_e))
    assert curve.electron_current_at_vp_a == pytest.approx(settings.area_m2 * codata.e * 3e16 * v_mean / 4, rel=1e-4)


def test_ion_current_follows_chen_oml_equation_22() -> None:
    settings = ProbeSettings.defaults(noise_percent=0.0)
    curve = generate(plasma(), settings)
    v = curve.voltage_v[0]
    expected = -settings.area_m2 * 3e16 * codata.e * (np.sqrt(2) / np.pi) * np.sqrt(codata.e * (10.0 - v) / ARGON_MASS_KG)
    assert curve.parts["ion"][0] == pytest.approx(expected, rel=1e-10)
    assert curve.parts["ion"][-1] == 0.0


def test_curve_rises_steadily_through_vp() -> None:
    curve = generate(plasma(DRUYVESTEYN_SHAPE), ProbeSettings.defaults(noise_percent=0.0, sweep_step_v=0.1))
    assert np.all(np.diff(curve.current_a) > 0)


def test_rf_distortion_makes_the_curve_look_hotter() -> None:
    """An oscillating plasma potential smears the knee, so the apparent slope temperature rises (FR6.3)."""
    from plasma_twin.probe.analysis import analyse_curve
    still = analyse_curve(generate(plasma(), ProbeSettings.defaults(noise_percent=0.0)))
    shaken = analyse_curve(generate(plasma(), ProbeSettings.defaults(noise_percent=0.0, rf_amplitude_v=5.0)))
    assert shaken.slope_temperature_ev > 1.2 * still.slope_temperature_ev
    assert shaken.floating_potential_v < still.floating_potential_v


def test_same_seed_same_curve() -> None:
    a = generate(plasma(), ProbeSettings.defaults(noise_percent=2.0, seed=4))
    b = generate(plasma(), ProbeSettings.defaults(noise_percent=2.0, seed=4))
    assert np.array_equal(a.current_a, b.current_a)


@pytest.mark.parametrize("override", [{"tip_radius_mm": 2.0}, {"noise_percent": 20.0}, {"rf_amplitude_v": 80.0},
                                      {"sweep_step_v": 0.01}, {"sweep_start_v": 50.0, "sweep_end_v": 10.0}])
def test_settings_outside_the_envelope_are_refused(override: dict) -> None:
    with pytest.raises(ProbeSettingsOutOfRange):
        generate(plasma(), ProbeSettings.defaults(**override))
