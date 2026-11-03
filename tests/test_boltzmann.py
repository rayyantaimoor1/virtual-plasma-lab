"""Tests for the Boltzmann plot (Phase 4c)."""
from dataclasses import fields

import numpy as np
import pytest

from plasma_twin.oes.boltzmann import BoltzmannFit, LinePoint, fit, integrated_intensities
from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")


def boltzmann_points(temperature_ev: float, energies: list[float]) -> list[LinePoint]:
    """Lines whose upper levels are populated exactly as exp(-E/T)."""
    points = []
    for i, energy in enumerate(energies):
        g, a, wavelength = 3 + i % 4, 1e7 * (1 + i), 500.0 + 20 * i
        population = g * np.exp(-energy / temperature_ev)
        intensity = population * a / wavelength  # I = n A h c / lambda, constants dropped
        points.append(LinePoint(wavelength, intensity, g, a, energy))
    return points


@pytest.mark.parametrize("temperature", [0.3, 0.8, 2.0])
def test_perfect_boltzmann_population_gives_back_its_temperature(temperature: float) -> None:
    result = fit(boltzmann_points(temperature, [13.0, 13.4, 13.9, 14.5, 15.0]))
    assert result.excitation_temperature_ev == pytest.approx(temperature, rel=1e-10)
    assert result.r_squared == pytest.approx(1.0)
    assert result.reliable


def test_too_few_lines_or_too_narrow_a_span_is_flagged() -> None:
    narrow = fit(boltzmann_points(0.8, [12.9, 13.0, 13.2, 13.48]))  # like argon 2p alone: 0.58 eV
    assert not narrow.reliable and any("span" in r for r in narrow.reasons)
    few = fit(boltzmann_points(0.8, [13.0, 14.0, 15.0]))
    assert not few.reliable and any("lines" in r for r in few.reasons)


def test_noisy_points_give_a_standard_error_and_lower_r_squared() -> None:
    points = boltzmann_points(0.8, [13.0, 13.4, 13.9, 14.5, 15.0, 15.3])
    rng = np.random.default_rng(1)
    noisy = [LinePoint(p.wavelength_nm, p.intensity * np.exp(rng.normal(0, 0.2)), p.g_upper, p.a_per_s,
                       p.upper_energy_ev) for p in points]
    result = fit(noisy)
    assert 0 < result.excitation_temperature_uncertainty_ev < result.excitation_temperature_ev
    assert result.r_squared < 1.0


def test_result_is_never_labelled_as_electron_temperature() -> None:
    """Phase 4 exit gate: T_exc is never called T_e."""
    names = [f.name for f in fields(BoltzmannFit)]
    assert "excitation_temperature_ev" in names
    assert not any(name.startswith("te") or "electron" in name for name in names)


@needs_data
def test_argon_2p_plot_from_the_model_spectrum_is_flagged_and_far_below_te() -> None:
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.oes.spectrum import SpectrometerSettings, build_spectrum
    from plasma_twin.stage1.global_model import default_inputs, solve
    result = solve(default_inputs())
    cr = solve_cr_for(result)
    spectrum = build_spectrum(cr.line_emission_w_m3, result.inputs.gas_temperature_k,
                              SpectrometerSettings.defaults(noise_percent=0.0, start_nm=650, end_nm=1000))
    points = integrated_intensities(spectrum, cr.lines)
    assert len(points) >= 10
    # Measured areas equal the CR model's line powers.
    for p in points:
        assert p.intensity == pytest.approx(cr.line_emission_w_m3[p.wavelength_nm], rel=1e-3)
    boltzmann = fit(points)
    assert not boltzmann.reliable  # 2p levels span ~0.6 eV (E9)
    assert boltzmann.energy_span_ev < 1.0


class _FakeCR:
    def __init__(self, populations: dict[str, float]) -> None:
        self.populations_m3 = populations


@needs_data
def test_boltzmann_populations_are_recognised_and_the_model_plasma_is_not_in_equilibrium() -> None:
    """FR5.4: exact Boltzmann populations pass; the low-pressure model plasma is far from equilibrium."""
    from plasma_twin.oes.boltzmann import populations_vs_boltzmann
    from plasma_twin.oes.cr_model import level_data, solve_cr_for
    from plasma_twin.services import stage1 as svc
    data, ground, te = level_data(), 1e21, 2.0
    exact = {k: data.weight[k] * ground * np.exp(-data.energy_ev[k] / te) for k in data.energy_ev}
    assert populations_vs_boltzmann(_FakeCR(exact), ground, te)[1]
    result = svc.run(svc.default_config())
    rows, in_equilibrium = populations_vs_boltzmann(solve_cr_for(result), result.gas_density_m3, result.te_ev)
    assert not in_equilibrium
    assert all(r.ratio < 1 for r in rows if r.level.startswith("2p"))  # under-populated: corona-like
