"""Tests for the N2 bands and the two gas-temperature methods (Phase 4e)."""
import numpy as np
import pytest

from plasma_twin.oes import n2_band as nb
from plasma_twin.reference.loaders import DataStatus, check_reference_data, load_atomic_lines

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")


# ---------------------------------------------------------------------- the band physics, against references
@pytest.mark.parametrize("j", [2, 5, 20, 50])
def test_honl_london_factors_obey_the_sum_rule(j: int) -> None:
    """For each lower level J'', the R, Q and P strengths add up to 2J'' + 1."""
    total = nb.honl_london("R", j) + nb.honl_london("Q", j) + nb.honl_london("P", j)
    assert total == pytest.approx(2 * j + 1)


@pytest.mark.parametrize(("state", "nist"), [("B", 5.9e-6), ("X", 5.76e-6)])
def test_kratzer_relation_reproduces_the_nist_distortion_constants(state: str, nist: float) -> None:
    assert nb.kratzer_d(state) == pytest.approx(nist, rel=0.02)


@pytest.mark.parametrize(("vu", "vl", "gilmore"), [(0, 0, 0.454), (0, 1, 0.327), (1, 0, 0.392)])
def test_morse_franck_condon_factors_reproduce_gilmore(vu: int, vl: int, gilmore: float) -> None:
    """The rule for trusting the computed X -> C split (BUILD_STEPS.md, 4e): within 5 %."""
    assert nb.franck_condon("C", vu, "B", vl) == pytest.approx(gilmore, rel=0.05)


def test_excitation_from_ground_n2_favours_the_lowest_c_levels() -> None:
    shares = nb.excitation_shares()
    assert shares[0] > shares[1] > 0
    assert shares[0] + shares[1] < 1  # higher C levels take the rest and are not drawn


@needs_data
def test_vacuum_to_air_conversion_matches_nist() -> None:
    lines = load_atomic_lines("Ar I")
    strong = np.argsort(lines.a_ki_per_s)[-20:]
    wavenumber = (lines.upper_energy_ev[strong] - lines.lower_energy_ev[strong]) / 1.239841984e-4
    assert np.max(np.abs(nb.vacuum_to_air_nm(wavenumber) - lines.wavelength_nm[strong])) < 2e-4


def test_one_zero_band_head_sits_at_315_9_nm() -> None:
    lines = nb.band_lines(1, 0, 300.0)
    assert max(lines) == pytest.approx(315.9, abs=0.05)
    assert sum(lines.values()) == pytest.approx(1.0)


def test_hotter_gas_spreads_the_band_to_shorter_wavelengths() -> None:
    def mean_wavelength(t: float) -> float:
        lines = nb.band_lines(1, 0, t)
        return sum(w * s for w, s in lines.items())
    assert mean_wavelength(1000.0) < mean_wavelength(300.0)


# ---------------------------------------------------------------------- the two temperature methods on model spectra
@pytest.fixture(scope="module")
def nitrogen_plasma():
    from plasma_twin.stage1.global_model import default_inputs, solve
    return solve(default_inputs(n2_percent_of_ar=5))


@needs_data
def test_doppler_is_disabled_at_the_default_resolution(nitrogen_plasma) -> None:
    from plasma_twin.oes.gas_temp import doppler_temperature
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    result = doppler_temperature(spectrum_for(nitrogen_plasma, SpectrometerSettings.defaults(noise_percent=0.0)))
    assert not result.enabled and "E8" in result.reason


@needs_data
def test_doppler_recovers_the_gas_temperature_when_the_instrument_is_sharp(nitrogen_plasma) -> None:
    from plasma_twin.oes.gas_temp import doppler_temperature
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    spectrum = spectrum_for(nitrogen_plasma, SpectrometerSettings.defaults(noise_percent=0.0, fwhm_nm=0.001,
                                                                           start_nm=740, end_nm=760))
    result = doppler_temperature(spectrum)
    assert result.enabled
    assert result.gas_temperature_k == pytest.approx(nitrogen_plasma.inputs.gas_temperature_k, rel=0.10)


@needs_data
def test_rotational_temperature_from_a_noise_free_band(nitrogen_plasma) -> None:
    from plasma_twin.oes.gas_temp import n2_rotational_temperature
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    result = n2_rotational_temperature(spectrum_for(nitrogen_plasma, SpectrometerSettings.defaults(noise_percent=0.0)))
    assert result.rotational_temperature_k == pytest.approx(nitrogen_plasma.inputs.gas_temperature_k, rel=0.01)
    assert not result.nh_overlap_flagged  # no hydrogen in the model, so no false alarm


@needs_data
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_rotational_temperature_with_one_percent_noise_in_a_uv_acquisition(nitrogen_plasma, seed: int) -> None:
    """Noise is a percentage of the spectrum's own peak, so the N2 band needs its own UV acquisition;
    on a 300-900 nm acquisition the 811 nm argon line sets the noise and the fit misses by 16-29 %
    (recorded in BUILD_STEPS.md, 4e)."""
    from plasma_twin.oes.gas_temp import n2_rotational_temperature
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    spectrum = spectrum_for(nitrogen_plasma, SpectrometerSettings.defaults(noise_percent=1.0, seed=seed,
                                                                           start_nm=305, end_nm=340))
    result = n2_rotational_temperature(spectrum)
    assert result.rotational_temperature_k == pytest.approx(nitrogen_plasma.inputs.gas_temperature_k, rel=0.10)


@needs_data
def test_n2_bands_appear_only_with_nitrogen(nitrogen_plasma) -> None:
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.stage1.global_model import default_inputs, solve
    window = SpectrometerSettings.defaults(noise_percent=0.0, start_nm=312, end_nm=338)
    assert spectrum_for(solve(default_inputs()), window).intensity.max() == 0.0
    assert spectrum_for(nitrogen_plasma, window).intensity.max() > 0.0
