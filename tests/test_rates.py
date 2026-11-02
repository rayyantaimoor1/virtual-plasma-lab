"""Tests for the rate coefficients (Phase 2b).

The first tests use made-up cross-sections whose rates are known exactly, so they check the
integration itself and run everywhere. The rest need the LXCat file, which is not in the public
repository, and are skipped where it is absent.
"""
import numpy as np
import pytest
from scipy import constants as codata

from plasma_twin.config.loader import load_envelope
from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE, EEDF, MAXWELLIAN_SHAPE
from plasma_twin.stage1.rates import (
    ARGON_MASS_KG,
    ENERGY_GRID_EV,
    TABLE_TE_EV,
    argon_cross_sections,
    rate_coefficient,
    rate_table,
    wall_constants,
)

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")
TOLERANCE = load_envelope()["validation"]["agreement_tolerance_fraction"]


def mean_speed(te: float) -> float:
    """Mean speed of a Maxwellian: sqrt(8 e T_e / (pi m))."""
    return float(np.sqrt(8 * codata.e * te / (np.pi * codata.m_e)))


# ------------------------------------------------------------------ the integration, against exact answers
@pytest.mark.parametrize("te", [1.0, 3.0, 8.0])
def test_constant_cross_section_gives_sigma_times_mean_speed(te: float) -> None:
    sigma = np.full_like(ENERGY_GRID_EV, 1e-20)
    assert rate_coefficient(sigma, EEDF(te, MAXWELLIAN_SHAPE)) == pytest.approx(1e-20 * mean_speed(te), rel=1e-5)


@pytest.mark.parametrize("te", [1.0, 3.0, 8.0])
def test_step_at_threshold_matches_the_exact_formula(te: float) -> None:
    """sigma = s0 above E: for a Maxwellian, K = s0 <v> (1 + E/T) exp(-E/T), exactly."""
    threshold = 15.76
    sigma = np.where(ENERGY_GRID_EV >= threshold, 1e-20, 0.0)
    exact = 1e-20 * mean_speed(te) * (1 + threshold / te) * np.exp(-threshold / te)
    assert rate_coefficient(sigma, EEDF(te, MAXWELLIAN_SHAPE)) == pytest.approx(exact, rel=2e-3)


def test_maxwellian_wall_constants_are_the_textbook_values() -> None:
    w = wall_constants(MAXWELLIAN_SHAPE)
    assert w.screening_ratio == pytest.approx(1.0, rel=1e-12)
    assert w.escape_energy_ratio == pytest.approx(2.0, rel=1e-5)  # E_e = 2 T_e
    assert w.floating_ratio == pytest.approx(np.log(np.sqrt(ARGON_MASS_KG / (2 * np.pi * codata.m_e))), rel=1e-6)
    assert w.mean_speed_ratio == pytest.approx(np.sqrt(8 / np.pi), rel=1e-6)


def test_druyvesteyn_holds_electrons_back_with_a_smaller_wall_potential() -> None:
    maxwellian, druyvesteyn = wall_constants(MAXWELLIAN_SHAPE), wall_constants(DRUYVESTEYN_SHAPE)
    assert druyvesteyn.floating_ratio < maxwellian.floating_ratio
    assert druyvesteyn.escape_energy_ratio < maxwellian.escape_energy_ratio


# ------------------------------------------------------------------ argon, from the Biagi data
@needs_lxcat
@pytest.mark.parametrize("shape", [MAXWELLIAN_SHAPE, DRUYVESTEYN_SHAPE])
@pytest.mark.parametrize("te", [1.0, 2.7, 6.3])
def test_table_matches_direct_integration(shape: float, te: float) -> None:
    cs, table, eedf = argon_cross_sections(), rate_table(shape), EEDF(te, shape)
    assert table.ionization(te) == pytest.approx(rate_coefficient(cs.ionization, eedf), rel=1e-4)
    assert table.momentum_transfer(te) == pytest.approx(rate_coefficient(cs.momentum_transfer, eedf), rel=1e-4)
    assert table.excitation(te) == pytest.approx(rate_coefficient(cs.excitation_total, eedf), rel=1e-4)


@needs_lxcat
@pytest.mark.parametrize("shape", [MAXWELLIAN_SHAPE, DRUYVESTEYN_SHAPE])
def test_ionization_rises_steeply_with_te(shape: float) -> None:
    table = rate_table(shape)
    k = [table.ionization(te) for te in np.linspace(1.0, 10.0, 40)]
    assert np.all(np.diff(k) > 0)
    assert table.ionization(4.0) / table.ionization(2.0) > 50  # threshold far above T_e


@needs_lxcat
@pytest.mark.parametrize("te", [2.0, 3.0, 5.0])
def test_druyvesteyn_ionization_is_below_maxwellian(te: float) -> None:
    assert rate_table(DRUYVESTEYN_SHAPE).ionization(te) < rate_table(MAXWELLIAN_SHAPE).ionization(te)


def published_ionization_fit(te: float) -> float:
    """K_iz = 2.3e-14 T_e^0.59 exp(-17.44/T_e) m^3/s: Kemaneci et al., arXiv:1612.07268 (2016),
    Table III, reaction 1, a Maxwellian average of the Straub et al. (1995) cross-section."""
    return 2.3e-14 * te**0.59 * np.exp(-17.44 / te)


@needs_lxcat
@pytest.mark.parametrize("te", [5.0, 7.0, 10.0])
def test_maxwellian_ionization_agrees_with_the_published_fit(te: float) -> None:
    assert rate_table(MAXWELLIAN_SHAPE).ionization(te) == pytest.approx(published_ionization_fit(te), rel=TOLERANCE)


@needs_lxcat
def test_known_low_te_difference_from_the_fit() -> None:
    """Recorded deviation, not a pass mark chosen afterwards.

    The plan asked for agreement at 3 eV within the ±30 % band. It is 40 % above the fit. Two
    independent integrations of the Biagi table give the same value (1.845e-16 m^3/s), so the
    integration is not the cause. The fit uses exp(-17.44/T_e), but argon ionizes from 15.76 eV,
    so the fit cannot follow the steep rise just above threshold, which dominates at low T_e.
    The evidence: the gap shrinks steadily as T_e rises (77 % at 2 eV, 40 % at 3 eV, 1 % at
    10 eV). This test pins those facts, so a change in the data or the integration is noticed.
    """
    table = rate_table(MAXWELLIAN_SHAPE)
    ratios = [table.ionization(te) / published_ionization_fit(te) for te in (2, 3, 4, 5, 7, 10)]
    assert np.all(np.diff(ratios) < 0)
    assert ratios[1] == pytest.approx(1.40, abs=0.02)
    assert ratios[-1] == pytest.approx(1.0, abs=0.05)


@needs_lxcat
def test_collisional_energy_loss_rises_as_te_falls() -> None:
    table = rate_table(MAXWELLIAN_SHAPE)
    e_c = [table.collisional_energy_loss_ev(te) for te in (1.5, 2.0, 3.0, 5.0)]
    assert np.all(np.diff(e_c) < 0)
    assert e_c[-1] > argon_cross_sections().ionization_threshold_ev  # never below the cost of one ion


@needs_lxcat
def test_table_refuses_te_outside_its_range() -> None:
    with pytest.raises(ValueError):
        rate_table(MAXWELLIAN_SHAPE).ionization(TABLE_TE_EV[-1] * 1.1)
