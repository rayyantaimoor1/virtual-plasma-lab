"""Tests for the gas temperature heat balance (Phase 3b)."""
import numpy as np
import pytest

from plasma_twin.config.loader import load_envelope
from plasma_twin.reference.loaders import DataStatus, check_reference_data, load_thermal_conductivity
from plasma_twin.stage1 import argon_kinetics as kin
from plasma_twin.stage1.gas_temperature import conduction_factor_m2, kirchhoff_potential, mean_gas_temperature
from plasma_twin.stage1.global_model import default_inputs, gas_heating_power, solve

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")
GAP, RADIUS = 0.045, 0.07


def test_wide_cylinder_gives_the_exact_slab_result() -> None:
    """Uniform heating between two plates: mean temperature rise = q l^2 / (12 kappa), exactly."""
    assert conduction_factor_m2(1000 * GAP, GAP) == pytest.approx(GAP**2 / 12, rel=2e-3)


def test_series_has_converged_for_the_real_cylinder() -> None:
    assert conduction_factor_m2(RADIUS, GAP, 200) == pytest.approx(conduction_factor_m2(RADIUS, GAP, 400), rel=1e-6)


def test_side_walls_cool_the_gas_further() -> None:
    assert conduction_factor_m2(RADIUS, GAP) < GAP**2 / 12


def test_small_heating_matches_constant_conductivity() -> None:
    """For a tiny rise, kappa barely changes, so T = T_wall + q * factor / kappa(300 K)."""
    heating = 0.01
    q = heating / (np.pi * RADIUS**2 * GAP)
    kappa_300 = load_thermal_conductivity()[1][0]
    expected = 300 + q * conduction_factor_m2(RADIUS, GAP) / kappa_300
    assert mean_gas_temperature(heating, RADIUS, GAP, 300.0) == pytest.approx(expected, abs=1e-3)
    assert kirchhoff_potential(300.0) == 0.0


def test_more_heat_means_hotter_gas() -> None:
    temperatures = [mean_gas_temperature(w, RADIUS, GAP, 300.0) for w in (0.0, 1.0, 5.0, 20.0)]
    assert temperatures[0] == pytest.approx(300.0)
    assert np.all(np.diff(temperatures) > 0)


@needs_lxcat
def test_gas_temperature_rises_with_power_and_stays_above_the_wall() -> None:
    wall = load_envelope()["stage1"]["fixed"]["wall_temperature_k"]
    temperatures = [solve(default_inputs(rf_power_w=p)).inputs.gas_temperature_k for p in (10, 50, 100)]
    assert all(t > wall for t in temperatures)
    assert np.all(np.diff(temperatures) > 0)


@needs_lxcat
def test_heat_balance_closes_and_the_heat_is_accounted_for() -> None:
    result = solve(default_inputs())
    assert all(r < 1e-8 for r in result.residuals.values()), result.residuals
    assert result.residuals["gas_temperature"] < 1e-9
    bulk = np.pi * RADIUS**2 * (GAP - 2 * result.sheath_width_m)
    quench = kin.K_GROUND_QUENCH_M * result.gas_density_m3 * result.metastable_density_m3 * kin.E_METASTABLE * 1.602176634e-19 * bulk
    assert result.gas_heating_w == pytest.approx(result.losses_w["elastic"] + quench, rel=1e-12)
    assert result.gas_heating_w == pytest.approx(gas_heating_power(result), rel=1e-12)
    # T_gas sets the gas density: p = n_g k T_gas
    assert result.gas_density_m3 * 1.380649e-23 * result.inputs.gas_temperature_k == pytest.approx(30.0, rel=1e-12)


@needs_lxcat
def test_gas_heating_off_reproduces_phase_2() -> None:
    result = solve(default_inputs(gas_heating=False, ar_flow_sccm=0.0))
    assert result.inputs.gas_temperature_k == 300
    assert result.te_ev == pytest.approx(3.0600171376131438, rel=1e-12)  # Phase 2d value at the defaults
