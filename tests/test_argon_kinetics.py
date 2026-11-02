"""Tests for excited argon atoms and two-step ionization (Phase 2d)."""
import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1 import argon_kinetics as kin
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE
from plasma_twin.stage1.rates import rate_table

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")
GAP, RADIUS, T_GAS = 0.045, 0.07, 300.0


def gas_density(mbar: float) -> float:
    return mbar * 100 / (1.380649e-23 * T_GAS)


def test_level_energies_match_the_published_thresholds() -> None:
    """Rows 8 and 15 of the reaction table: 4.20 eV from 4s_m, 2.61 eV from 4p."""
    assert kin.E_IONIZATION - kin.E_METASTABLE == pytest.approx(4.20)
    assert kin.E_IONIZATION - kin.E_4P == pytest.approx(2.61)
    assert kin.E_METASTABLE < kin.E_RESONANT < kin.E_4P < kin.E_IONIZATION


def test_wall_loss_is_diffusion_limited_and_falls_with_pressure() -> None:
    """At these pressures diffusion is slow compared with absorption at the wall, so k ~ D / Lambda^2,
    and D ~ 1/p makes the loss rate fall in proportion to pressure."""
    low, high = kin.wall_loss_rate(GAP, RADIUS, gas_density(0.1), T_GAS), kin.wall_loss_rate(GAP, RADIUS, gas_density(0.5), T_GAS)
    assert high < low
    assert low / high == pytest.approx(5.0, rel=0.05)
    pressure_pa = 0.3 * 100
    diffusion = kin.D0_M2_S * (kin.D0_PRESSURE_PA / pressure_pa) * (T_GAS / kin.D0_TEMPERATURE_K) ** kin.D_TEMPERATURE_EXPONENT
    diffusion_only = diffusion * ((np.pi / GAP) ** 2 + (2.404825557695773 / RADIUS) ** 2)
    assert kin.wall_loss_rate(GAP, RADIUS, gas_density(0.3), T_GAS) == pytest.approx(diffusion_only, rel=0.05)


def test_superelastic_collisions_give_energy_back() -> None:
    power = kin.excited_electron_power(2.0, 1e16, kin.ExcitedDensities(1e16, 1e15, 1e12))
    assert power["two_step_ionization"] > 0
    assert power["excitation_between_levels"] > 0
    assert power["superelastic_return"] < 0


@needs_lxcat
@pytest.mark.parametrize(("te", "ne"), [(1.5, 1e15), (3.0, 3e16), (5.0, 1e17)])
def test_solved_densities_satisfy_all_three_balances(te: float, ne: float) -> None:
    table = rate_table(DRUYVESTEYN_SHAPE)
    ng = gas_density(0.3)
    k_wall = kin.wall_loss_rate(GAP, RADIUS, ng, T_GAS)
    densities = kin.solve_densities(te, ne, ng, table, k_wall)
    for level, (gain, loss) in kin.balances(te, ne, ng, densities, table, k_wall).items():
        assert gain == pytest.approx(loss, rel=1e-10), level


@needs_lxcat
def test_without_excited_atoms_only_ground_ionization_remains() -> None:
    table = rate_table(DRUYVESTEYN_SHAPE)
    routes = kin.ionization_rate(3.0, 1e16, gas_density(0.3), kin.ExcitedDensities(0.0, 0.0, 0.0), table)
    assert routes["from_ground"] > 0
    assert routes["from_metastable"] == routes["from_4p"] == routes["pooling"] == 0.0
