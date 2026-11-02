"""Tests for the line-ratio T_e and n_e fit (Phase 4d)."""
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")


@pytest.fixture(scope="module")
def plasma():
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.stage1.global_model import default_inputs, solve
    result = solve(default_inputs())
    return result, solve_cr_for(result)


def measured_points(plasma, noise: float, seed: int):
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.spectrum import SpectrometerSettings, build_spectrum
    result, cr = plasma
    spectrum = build_spectrum(cr.line_emission_w_m3, result.inputs.gas_temperature_k,
                              SpectrometerSettings.defaults(noise_percent=noise, seed=seed, start_nm=650, end_nm=1000))
    return [p for p in integrated_intensities(spectrum, cr.lines) if p.intensity > 0]


@needs_data
def test_noise_free_spectrum_gives_back_the_model_te_and_ne(plasma) -> None:
    """ACC-2 asks for +/-30 %; the inversion of the same model should in fact be almost exact."""
    from plasma_twin.oes.line_ratio import fit_spectrum_points
    result, _ = plasma
    fit = fit_spectrum_points(measured_points(plasma, 0.0, 0), result)
    assert fit.te_ev == pytest.approx(result.te_ev, rel=0.30)  # ACC-2
    assert fit.te_ev == pytest.approx(result.te_ev, rel=1e-3)
    assert fit.ne_m3 == pytest.approx(result.ne_center_m3, rel=1e-3)


@needs_data
@pytest.mark.parametrize("seed", [1, 2])
def test_one_percent_noise_stays_within_tolerance(plasma, seed: int) -> None:
    from plasma_twin.oes.line_ratio import fit_spectrum_points
    result, _ = plasma
    fit = fit_spectrum_points(measured_points(plasma, 1.0, seed), result)
    assert fit.te_ev == pytest.approx(result.te_ev, rel=0.30)


def test_needs_at_least_three_lines() -> None:
    from plasma_twin.oes.line_ratio import fit_te_ne
    with pytest.raises(ValueError):
        fit_te_ne({750.387: 1.0, 811.531: 2.0}, 7e21, 2.0, 300.0, 0.045, 0.07)
