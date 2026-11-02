"""Gas temperature from a spectrum: Doppler width and N2 rotational temperature (Phase 4e).

Two independent routes, chosen by the supervisor (B6, Q5):
- DOPPLER: a hotter gas moves faster, so each line is wider. Usable only if the spectrometer is
  sharper than the Doppler width (E8): about 0.0015 nm for argon at 300 K, below the default
  0.005 nm instrument, so it is disabled by default.
- N2 ROTATIONAL TEMPERATURE: the rotational lines of the N2 (1,0) band at 315.9 nm are populated
  according to the gas temperature, so the band's shape gives it. Rules: BUILD_STEPS.md, 4e.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import constants as codata
from scipy.optimize import curve_fit, least_squares

from plasma_twin.oes.n2_band import N2_MASS_KG, band_lines
from plasma_twin.oes.spectrum import FWHM_TO_SIGMA, Spectrum, doppler_fwhm_nm
from plasma_twin.stage1.rates import ARGON_MASS_KG

DOPPLER_LINE_NM = 750.387  # 2p1 -> 1s2 (BUILD_STEPS.md, 4e)
ROTATIONAL_WINDOW_NM = (312.0, 316.2)
NH_WINDOW_NM = (335.8, 336.2)
N2_00_HEAD_WINDOW_NM = (336.9, 337.2)
NH_FLAG_FRACTION = 0.05


@dataclass(frozen=True)
class DopplerResult:
    enabled: bool
    reason: str
    gas_temperature_k: float | None = None
    fitted_fwhm_nm: float | None = None


def doppler_temperature(spectrum: Spectrum, expected_temperature_k: float | None = None,
                        line_nm: float = DOPPLER_LINE_NM, mass_kg: float = ARGON_MASS_KG) -> DopplerResult:
    """Gas temperature from the width of one argon line, if the instrument can resolve it (E8)."""
    expected = expected_temperature_k or spectrum.gas_temperature_k
    instrument = spectrum.settings.fwhm_nm
    doppler = doppler_fwhm_nm(line_nm, expected, mass_kg)
    if instrument > doppler:
        return DopplerResult(False, f"instrument FWHM {instrument} nm exceeds the expected Doppler FWHM "
                                    f"{doppler:.4f} nm at {expected:.0f} K (E8)")
    total = np.hypot(instrument, doppler)
    window = np.abs(spectrum.wavelength_nm - line_nm) <= 5 * total
    x, y = spectrum.wavelength_nm[window], spectrum.intensity[window]

    def gaussian(w, height, centre, fwhm, background):
        return height * np.exp(-0.5 * ((w - centre) / (fwhm * FWHM_TO_SIGMA)) ** 2) + background

    (height, centre, fwhm, background), _ = curve_fit(gaussian, x, y, p0=(y.max(), line_nm, total, 0.0))
    fwhm = abs(fwhm)
    if fwhm <= instrument:
        return DopplerResult(False, "the fitted line is no wider than the instrument", None, fwhm)
    doppler_part = np.sqrt(fwhm**2 - instrument**2)
    temperature = (doppler_part / line_nm) ** 2 * mass_kg * codata.c**2 / (8 * codata.k * np.log(2))
    return DopplerResult(True, "fitted", float(temperature), float(fwhm))


def render_band(wavelength_nm: np.ndarray, rotational_temperature_k: float, instrument_fwhm_nm: float,
                v_upper: int = 1, v_lower: int = 0) -> np.ndarray:
    """Shape of one N2 band on a given wavelength grid (area 1), through the instrument."""
    out = np.zeros_like(wavelength_nm)
    for wl, share in band_lines(v_upper, v_lower, rotational_temperature_k).items():
        width = np.hypot(instrument_fwhm_nm, doppler_fwhm_nm(wl, rotational_temperature_k, N2_MASS_KG))
        sigma = width * FWHM_TO_SIGMA
        out += share * np.exp(-0.5 * ((wavelength_nm - wl) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    return out


@dataclass(frozen=True)
class RotationalResult:
    rotational_temperature_k: float
    rms_relative_residual: float
    success: bool
    nh_excess_fraction: float  # power near 336 nm beyond the N2 prediction, as a fraction of the (0,0) head
    nh_overlap_flagged: bool


def nh_overlap(spectrum: Spectrum, rotational_temperature_k: float) -> tuple[float, bool]:
    """Excess power near 336 nm (NH A-X head) beyond what N2 alone puts there; flagged above 5 % of the
    N2 (0,0) head power.

    CHANGED 3 Nov 2026 from the rule in BUILD_STEPS.md, which compared the raw 336 nm power with the
    (0,0) head. The (0,0) band itself reaches past 336 nm, so that gave a false alarm (ratio 0.17) on a
    spectrum with no NH at all. Now the N2 contribution is predicted from the (0,0) band shape at the
    fitted rotational temperature, scaled to the measured head, and only the excess counts.
    """
    def power(values: np.ndarray, window: tuple[float, float]) -> float:
        inside = (spectrum.wavelength_nm >= window[0]) & (spectrum.wavelength_nm <= window[1])
        return float(np.trapezoid(values[inside], spectrum.wavelength_nm[inside]))
    measured_head = power(spectrum.intensity, N2_00_HEAD_WINDOW_NM)
    if measured_head <= 0:
        return float("inf"), True
    shape = render_band(spectrum.wavelength_nm, rotational_temperature_k, spectrum.settings.fwhm_nm, 0, 0)
    scale = measured_head / power(shape, N2_00_HEAD_WINDOW_NM)
    excess = (power(spectrum.intensity, NH_WINDOW_NM) - scale * power(shape, NH_WINDOW_NM)) / measured_head
    return excess, excess > NH_FLAG_FRACTION


def n2_rotational_temperature(spectrum: Spectrum) -> RotationalResult:
    """Fit T_rot, a scale and a flat background to the (1,0) band (312.0-316.2 nm)."""
    inside = (spectrum.wavelength_nm >= ROTATIONAL_WINDOW_NM[0]) & (spectrum.wavelength_nm <= ROTATIONAL_WINDOW_NM[1])
    x, y = spectrum.wavelength_nm[inside], spectrum.intensity[inside]
    if len(x) < 10 or y.max() <= 0:
        raise ValueError("the spectrum does not cover the N2 (1,0) band at 312-316 nm")
    fwhm = spectrum.settings.fwhm_nm
    shape0 = render_band(x, 400.0, fwhm)
    scale0 = y.max() / shape0.max()

    def residual(p: np.ndarray) -> np.ndarray:
        model = p[1] * scale0 * render_band(x, p[0], fwhm) + p[2] * y.max()
        return (model - y) / y.max()

    found = least_squares(residual, x0=[400.0, 1.0, 0.0], bounds=([200.0, 0.0, -1.0], [2000.0, 100.0, 1.0]),
                          x_scale=[100.0, 0.1, 0.01], xtol=1e-12, ftol=1e-12)
    ratio, flagged = nh_overlap(spectrum, float(found.x[0]))
    return RotationalResult(float(found.x[0]), float(np.sqrt(np.mean(found.fun**2))), bool(found.success), ratio, flagged)
