"""Tests for gas flow and residence time (Phase 3a)."""
import math

import pytest
from scipy.constants import physical_constants

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1 import gas_flow
from plasma_twin.stage1.global_model import InputOutOfRange, default_inputs, solve

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


def test_one_sccm_is_the_standard_number_of_atoms_per_second() -> None:
    """1 sccm = 1 cm^3 per minute at 0 °C and 1 atm: the CODATA Loschmidt constant x 1e-6 m^3 / 60 s,
    about 4.48e17 atoms/s."""
    loschmidt = physical_constants["Loschmidt constant (273.15 K, 101.325 kPa)"][0]
    assert gas_flow.ATOMS_PER_S_PER_SCCM == pytest.approx(loschmidt * 1e-6 / 60, rel=1e-9)


def test_residence_time_scales_as_pressure_over_flow() -> None:
    volume = gas_flow.chamber_volume_m3(0.40, 0.40)
    base = gas_flow.residence_time_s(7e21, volume, 300)
    assert gas_flow.residence_time_s(14e21, volume, 300) == pytest.approx(2 * base)
    assert gas_flow.residence_time_s(7e21, volume, 150) == pytest.approx(2 * base)
    assert gas_flow.residence_time_s(7e21, volume, 0) == math.inf
    assert gas_flow.pumping_rate_per_s(7e21, volume, 0) == 0.0


def test_chamber_volume_of_the_40_by_40_cm_cylinder() -> None:
    assert gas_flow.chamber_volume_m3(0.40, 0.40) == pytest.approx(math.pi * 0.2**2 * 0.4)


def test_flow_outside_the_envelope_is_refused() -> None:
    with pytest.raises(InputOutOfRange):
        solve(default_inputs(ar_flow_sccm=50))
    with pytest.raises(InputOutOfRange):
        solve(default_inputs(ar_flow_sccm=600))


@needs_lxcat
def test_no_flow_reproduces_the_phase_2_model_exactly() -> None:
    with_flow_off = solve(default_inputs(ar_flow_sccm=0.0))
    phase2 = solve(default_inputs(ar_flow_sccm=0.0, eedf="Druyvesteyn"))
    assert with_flow_off.as_dict() == phase2.as_dict()
    assert with_flow_off.te_ev == pytest.approx(3.060017, abs=1e-6)  # Phase 2d value at the defaults


@needs_lxcat
def test_flow_effect_on_pure_argon_is_small() -> None:
    """Pumping takes seconds; diffusion to the walls takes milliseconds. Stated before building."""
    still, flowing = solve(default_inputs(ar_flow_sccm=0.0)), solve(default_inputs(ar_flow_sccm=500))
    assert flowing.metastable_density_m3 < still.metastable_density_m3  # more loss, fewer metastables
    assert flowing.metastable_density_m3 == pytest.approx(still.metastable_density_m3, rel=0.01)
    assert flowing.ne_center_m3 == pytest.approx(still.ne_center_m3, rel=0.01)
