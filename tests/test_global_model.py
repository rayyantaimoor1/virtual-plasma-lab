"""Tests for the argon global model (Phase 2c). Comparison with published measurements is in
test_stage1_benchmarks.py, written only after this model was committed (ACC-4)."""
import time

import numpy as np
import pytest

from plasma_twin.config.loader import load_envelope
from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.global_model import (
    InputOutOfRange,
    bulk_ohmic_power,
    collisional_child_width,
    default_inputs,
    sheath_heating_power,
    solve,
)

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")
ENV = load_envelope()


def phase2_inputs(**overrides):
    """The Phase 2 model: no gas flow and a fixed gas temperature (Phase 3 effects switched off)."""
    return default_inputs(**{"ar_flow_sccm": 0.0, "gas_heating": False, **overrides})


# ------------------------------------------------------------------ formulas against Lieberman's own example
def test_heating_and_sheath_formulas_reproduce_the_published_example() -> None:
    """M. A. Lieberman, UC Berkeley short course 2015, slides 284-285: 1 Torr argon, gap 2 cm,
    A = 1000 cm^2, 13.56 MHz, V~_s = 150 V. The slides give P_ohm = 1.2 W, P_sh = 6.3 W per sheath
    and s_m = 0.33 cm. Their inputs are read from graphs, so the slides round to 2 figures."""
    omega = 2 * np.pi * 13.56e6
    p_ohm = bulk_ohmic_power(te=1.7, v_rf_sheath=150, nu_m=1.23e9, h_l=0.1, gap=0.02, sheath=0.005, area=0.1,
                             omega=omega)
    ohmic, stochastic = sheath_heating_power(nu_m=1.23e9, sheath=0.005, mean_speed=8.8e5, v_rf_sheath=150,
                                             area=0.1, omega=omega)
    width = collisional_child_width(v_dc=117, lambda_i=3e-5, ion_flux=1.1e15 * 2.0e3)
    assert p_ohm == pytest.approx(1.2, rel=0.05)
    assert ohmic + stochastic == pytest.approx(6.3, rel=0.05)
    assert width == pytest.approx(0.0033, rel=0.05)


# ------------------------------------------------------------------ input checks (E3)
@pytest.mark.parametrize("override", [
    {"rf_power_w": 5}, {"rf_power_w": 150}, {"pressure_mbar": 0.05}, {"pressure_mbar": 0.6},
    {"electrode_radius_m": 0.25}, {"electrode_gap_m": 0.5}, {"electrode_gap_m": 0.0}, {"eedf": "Boltzmann"},
    {"edge_length": "middle"},
])
def test_out_of_range_inputs_are_refused(override: dict) -> None:
    with pytest.raises(InputOutOfRange):
        solve(phase2_inputs(**override))


# ------------------------------------------------------------------ the solution itself
@needs_lxcat
@pytest.mark.parametrize("eedf", ["Druyvesteyn", "Maxwellian"])
def test_balances_close_and_power_shares_add_up(eedf: str) -> None:
    result = solve(phase2_inputs(eedf=eedf))
    limit = ENV["solver"]["residual_limit"]
    assert all(r < limit for r in result.residuals.values()), result.residuals
    tolerance = ENV["solver"]["power_share_tolerance_percent"]
    for which in ("heating", "losses"):
        shares = result.shares_percent(which)
        assert sum(shares.values()) == pytest.approx(100.0, abs=tolerance)
        # Only energy handed back by excited atoms (superelastic collisions) may be negative.
        assert all(v >= 0 for k, v in shares.items() if k != "superelastic_return")


@needs_lxcat
def test_outputs_are_derived_from_te_and_ne() -> None:
    r = solve(phase2_inputs())
    assert r.ne_sheath_edge_m3 == pytest.approx(r.h_axial * r.ne_center_m3, rel=1e-12)
    assert r.ion_flux_electrode_m2_s == pytest.approx(r.ne_sheath_edge_m3 * r.bohm_speed_m_s, rel=1e-12)
    assert r.ion_flux_radial_m2_s == pytest.approx(r.h_radial * r.ne_center_m3 * r.bohm_speed_m_s, rel=1e-12)
    assert r.dc_sheath_voltage_v == pytest.approx(0.78 * r.rf_voltage_amplitude_v / 2, rel=1e-12)


@needs_lxcat
@pytest.mark.parametrize("eedf", ["Druyvesteyn", "Maxwellian"])
def test_ground_state_only_te_barely_depends_on_power(eedf: str) -> None:
    """Without excited atoms, T_e is fixed by the particle balance. Power enters only through the
    sheath width, which takes a few mm from a 45 mm gap, so T_e may move by much less than 2 %."""
    te = [solve(phase2_inputs(rf_power_w=p, eedf=eedf, excited_states=False)).te_ev for p in (10, 40, 70, 100)]
    assert (max(te) - min(te)) / min(te) < 0.02


@needs_lxcat
@pytest.mark.parametrize("eedf", ["Druyvesteyn", "Maxwellian"])
def test_with_excited_atoms_te_falls_as_power_rises(eedf: str) -> None:
    """More power -> more electrons -> more excited atoms -> more two-step ionization, so the
    plasma needs a slightly lower T_e."""
    te = [solve(phase2_inputs(rf_power_w=p, eedf=eedf)).te_ev for p in (10, 40, 70, 100)]
    assert np.all(np.diff(te) < 0)


@needs_lxcat
@pytest.mark.parametrize("eedf", ["Druyvesteyn", "Maxwellian"])
def test_density_rises_with_power_but_less_than_proportionally(eedf: str) -> None:
    """In this CCP model the share of power spent accelerating ions in the sheaths grows with the
    RF voltage, so n_e grows more slowly than P (the simple low-voltage model gives exactly P^1)."""
    powers = np.array([10, 25, 50, 75, 100])
    ne = np.array([solve(phase2_inputs(rf_power_w=p, eedf=eedf, excited_states=False)).ne_center_m3
                   for p in powers])
    assert np.all(np.diff(ne) > 0)
    slope = np.polyfit(np.log(powers), np.log(ne), 1)[0]
    assert 0.5 < slope < 1.0


@needs_lxcat
def test_te_falls_and_density_rises_with_pressure() -> None:
    results = [solve(phase2_inputs(pressure_mbar=p)) for p in (0.1, 0.2, 0.3, 0.4, 0.5)]
    assert np.all(np.diff([r.te_ev for r in results]) < 0)
    assert np.all(np.diff([r.ne_center_m3 for r in results]) > 0)


@needs_lxcat
def test_druyvesteyn_needs_a_higher_te_than_maxwellian() -> None:
    """With fewer fast electrons, a Druyvesteyn plasma must be hotter on average to ionize enough
    (the effect studied by Gudmundsson, Plasma Sources Sci. Technol. 10, 76, 2001)."""
    assert solve(phase2_inputs(eedf="Druyvesteyn")).te_ev > solve(phase2_inputs(eedf="Maxwellian")).te_ev


@needs_lxcat
@pytest.mark.parametrize(("eedf", "te", "ne"), [
    ("Druyvesteyn", 3.076930103304118, 3.2193388222688204e16),  # recorded from commit 0b15c93
    ("Maxwellian", 1.6657347668344424, 6.40467331691257e16),
])
def test_switching_excited_states_off_reproduces_phase_2c(eedf: str, te: float, ne: float) -> None:
    result = solve(phase2_inputs(eedf=eedf, excited_states=False))
    assert result.te_ev == pytest.approx(te, rel=1e-12)
    assert result.ne_center_m3 == pytest.approx(ne, rel=1e-12)


@needs_lxcat
@pytest.mark.parametrize("eedf", ["Druyvesteyn", "Maxwellian"])
def test_excited_atoms_lower_te_and_add_ionization_routes(eedf: str) -> None:
    ground = solve(phase2_inputs(eedf=eedf, excited_states=False))
    full = solve(phase2_inputs(eedf=eedf))
    assert full.te_ev < ground.te_ev
    assert sum(full.ionization_routes.values()) == pytest.approx(1.0, rel=1e-12)
    assert full.ionization_routes["from_ground"] < 1.0
    for density in (full.metastable_density_m3, full.resonant_density_m3, full.p4_density_m3):
        assert 0 < density < 1e-3 * full.gas_density_m3  # excited atoms stay a small minority
    assert full.p4_density_m3 < full.metastable_density_m3  # 4p atoms radiate within ~30 ns


@needs_lxcat
def test_same_inputs_give_identical_outputs() -> None:
    assert solve(phase2_inputs()).as_dict() == solve(phase2_inputs()).as_dict()  # REL-4


@needs_lxcat
def test_one_run_takes_at_most_two_seconds() -> None:
    start = time.perf_counter()
    solve(phase2_inputs(rf_power_w=73, pressure_mbar=0.37))
    assert time.perf_counter() - start <= 2.0  # PER-1


@needs_lxcat
def test_solver_converges_across_the_whole_envelope() -> None:
    """REL-1: at least 500 configurations, edges included, both EEDFs."""
    limit = ENV["solver"]["residual_limit"]
    count = 0
    for eedf in ("Druyvesteyn", "Maxwellian"):
        for power in np.linspace(10, 100, 10):
            for pressure in np.linspace(0.1, 0.5, 25):
                result = solve(phase2_inputs(rf_power_w=power, pressure_mbar=pressure, eedf=eedf))
                assert max(result.residuals.values()) < limit, (eedf, power, pressure)
                count += 1
    assert count >= 500
