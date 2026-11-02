"""Tests for the synthetic spectrum (Phase 4b)."""
import time

import numpy as np
import pytest

from plasma_twin.oes.spectrum import (
    SpectrometerSettings,
    SpectrumSettingsOutOfRange,
    build_spectrum,
    doppler_fwhm_nm,
    spectrum_for,
)
from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")
LINES = {750.387: 2.0, 751.465: 1.0, 811.531: 5.0}


def quiet(**overrides) -> SpectrometerSettings:
    return SpectrometerSettings.defaults(noise_percent=0.0, start_nm=700, end_nm=850, **overrides)


def test_doppler_width_of_argon_at_room_temperature() -> None:
    """lambda * sqrt(8 k T ln2 / (M c^2)) = 1.47e-3 nm at 750 nm and 300 K: below the 0.005 nm instrument."""
    assert doppler_fwhm_nm(750.0, 300.0) == pytest.approx(1.47e-3, rel=0.01)
    assert doppler_fwhm_nm(750.0, 1200.0) == pytest.approx(2 * doppler_fwhm_nm(750.0, 300.0))


def test_peaks_sit_at_the_line_wavelengths() -> None:
    spectrum = build_spectrum(LINES, 300.0, quiet())
    step = spectrum.settings.fwhm_nm / 5
    for wavelength in LINES:
        window = np.abs(spectrum.wavelength_nm - wavelength) < 0.02
        peak = spectrum.wavelength_nm[window][np.argmax(spectrum.intensity[window])]
        assert abs(peak - wavelength) <= step


def test_area_under_each_line_is_its_power() -> None:
    spectrum = build_spectrum(LINES, 300.0, quiet())
    for wavelength, power in LINES.items():
        window = np.abs(spectrum.wavelength_nm - wavelength) < 0.05
        area = np.trapezoid(spectrum.intensity[window], spectrum.wavelength_nm[window])
        assert area == pytest.approx(power, rel=1e-3)


def test_line_width_combines_instrument_and_doppler() -> None:
    hot = build_spectrum({811.531: 1.0}, 3000.0, quiet(fwhm_nm=0.002))
    above = hot.wavelength_nm[hot.intensity >= hot.intensity.max() / 2]
    expected = np.hypot(0.002, doppler_fwhm_nm(811.531, 3000.0))
    assert above[-1] - above[0] == pytest.approx(expected, abs=0.002 / 5 * 2)


def test_same_seed_same_spectrum_and_noise_is_seeded() -> None:
    noisy = SpectrometerSettings.defaults(start_nm=700, end_nm=850, noise_percent=2.0, seed=7)
    a, b = build_spectrum(LINES, 300.0, noisy), build_spectrum(LINES, 300.0, noisy)
    assert np.array_equal(a.intensity, b.intensity)  # REL-4
    other = build_spectrum(LINES, 300.0, SpectrometerSettings.defaults(start_nm=700, end_nm=850, noise_percent=2.0, seed=8))
    assert not np.array_equal(a.intensity, other.intensity)


@pytest.mark.parametrize("override", [{"fwhm_nm": 5.0}, {"noise_percent": 50.0}, {"start_nm": 100.0},
                                      {"start_nm": 800.0, "end_nm": 700.0}])
def test_settings_outside_the_envelope_are_refused(override: dict) -> None:
    with pytest.raises(SpectrumSettingsOutOfRange):
        build_spectrum(LINES, 300.0, SpectrometerSettings.defaults(**override))


@needs_data
def test_full_spectrum_from_the_plasma_in_at_most_three_seconds() -> None:
    from plasma_twin.stage1.global_model import default_inputs, solve
    result = solve(default_inputs())
    start = time.perf_counter()
    spectrum = spectrum_for(result)  # CR model + 300-900 nm at 0.005 nm
    assert time.perf_counter() - start <= 3.0  # PER-2
    assert len(spectrum.wavelength_nm) > 500_000
    peak = spectrum.wavelength_nm[np.argmax(spectrum.intensity)]
    assert peak == pytest.approx(811.531, abs=0.005)
