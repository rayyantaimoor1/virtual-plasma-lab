"""Tests for the Druyvesteyn EEPF (Phase 5)."""
import numpy as np
import pytest

from plasma_twin.probe.analysis import analyse_curve
from plasma_twin.probe.eepf import second_derivative_noise_gain
from plasma_twin.probe.iv_model import ProbePlasma, ProbeSettings, generate
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE, MAXWELLIAN_SHAPE, EEDF
from plasma_twin.stage1.rates import ARGON_MASS_KG


def recovered(shape: float):
    plasma = ProbePlasma(3e16, 3.0, shape, {"Ar+": 3e16}, {"Ar+": ARGON_MASS_KG}, 12.0)
    return analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0, sweep_step_v=0.1))).eepf


@pytest.mark.parametrize("shape", [MAXWELLIAN_SHAPE, DRUYVESTEYN_SHAPE])
def test_druyvesteyn_formula_returns_the_true_eedf(shape: float) -> None:
    """The formula itself, given the true V_p: within 3 % from 1 to 12 eV."""
    from plasma_twin.probe.eepf import derivatives, druyvesteyn
    plasma = ProbePlasma(3e16, 3.0, shape, {"Ar+": 3e16}, {"Ar+": ARGON_MASS_KG}, 12.0)
    settings = ProbeSettings.defaults(noise_percent=0.0, sweep_step_v=0.1)
    curve = generate(plasma, settings)
    _, second = derivatives(curve.voltage_v, curve.parts["electron"])
    eepf = druyvesteyn(curve.voltage_v, second, 12.0, settings.area_m2)
    window = (eepf.energy_ev > 1.0) & (eepf.energy_ev < 12.0)
    truth = 3e16 * EEDF(3.0, shape)(eepf.energy_ev[window])
    assert np.allclose(eepf.eedf_m3_per_ev[window], truth, rtol=0.03)


@pytest.mark.parametrize("shape", [MAXWELLIAN_SHAPE, DRUYVESTEYN_SHAPE])
def test_full_analysis_eedf_differs_only_by_the_vp_offset(shape: float) -> None:
    """With V_p found from the data (a little low, see BUILD_STEPS.md), every energy is read short by the
    same offset d. The formula multiplies by sqrt of the energy it is given, so exactly
    recovered(e) = sqrt(e / (e + d)) * true(e + d). That must hold within 3 %: then the offset is the only error."""
    plasma = ProbePlasma(3e16, 3.0, shape, {"Ar+": 3e16}, {"Ar+": ARGON_MASS_KG}, 12.0)
    result = analyse_curve(generate(plasma, ProbeSettings.defaults(noise_percent=0.0, sweep_step_v=0.1)))
    offset = 12.0 - result.plasma_potential_v
    assert 0 < offset < 0.3
    eepf = result.eepf
    window = (eepf.energy_ev > 1.0) & (eepf.energy_ev < 12.0)
    energy = eepf.energy_ev[window]
    truth = np.sqrt(energy / (energy + offset)) * 3e16 * EEDF(3.0, shape)(energy + offset)
    assert np.allclose(eepf.eedf_m3_per_ev[window], truth, rtol=0.03)


def test_druyvesteyn_eepf_is_druyvesteyn_shaped() -> None:
    """ln EEPF is a straight line in energy for a Maxwellian and in energy squared for Druyvesteyn."""
    for shape, power in ((MAXWELLIAN_SHAPE, 1), (DRUYVESTEYN_SHAPE, 2)):
        eepf = recovered(shape)
        window = (eepf.energy_ev > 1.0) & (eepf.energy_ev < 10.0)
        y = np.log(eepf.eepf[window])
        r2 = {}
        for p in (1, 2):
            x = eepf.energy_ev[window] ** p
            fit = np.polyval(np.polyfit(x, y, 1), x)
            r2[p] = 1 - np.sum((y - fit) ** 2) / np.sum((y - y.mean()) ** 2)
        assert r2[power] > r2[3 - power], (shape, r2)


def test_noise_gain_of_the_smoothing_filter() -> None:
    """Savitzky-Golay 5-point cubic second derivative: weights (2, -1, -2, -1, 2) / (7 h^2)."""
    assert second_derivative_noise_gain(0.5) == pytest.approx(np.sqrt(14) / 7 / 0.25, rel=1e-10)
