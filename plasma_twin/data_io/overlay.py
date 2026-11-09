"""Overlay of a measured spectrum on the synthetic one: Phase 8 (FR4.6).

RULE (BUILD_STEPS.md, Phase 8): both spectra are normalised to the same reference line, the strongest
model Ar I line inside both wavelength ranges, using each spectrum's peak within +/-3 FWHM of it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class NoCommonLine(ValueError):
    """No model argon line lies inside both spectra."""


@dataclass(frozen=True)
class Normalisation:
    reference_nm: float
    model_peak: float
    measured_peak: float

    @property
    def scale(self) -> float:
        """Multiply the measured intensities by this to put them on the model's scale."""
        return self.model_peak / self.measured_peak


def _peak(wavelength: np.ndarray, intensity: np.ndarray, centre: float, half: float) -> float:
    window = np.abs(wavelength - centre) <= half
    return float(intensity[window].max()) if window.any() else 0.0


def normalise(model_wavelength: np.ndarray, model_intensity: np.ndarray, model_fwhm_nm: float, line_power: dict[float, float],
              measured_wavelength: np.ndarray, measured_intensity: np.ndarray, measured_fwhm_nm: float) -> Normalisation:
    """Scale a model spectrum to a measured one on their common range by matching line areas, so different instrument widths compare fairly (FR10.4)."""
    low = max(model_wavelength[0], measured_wavelength[0])
    high = min(model_wavelength[-1], measured_wavelength[-1])
    candidates = [(power, wl) for wl, power in line_power.items() if low <= wl <= high and power > 0]
    if not candidates:
        raise NoCommonLine("no model argon line lies inside both wavelength ranges")
    reference = max(candidates)[1]
    model_peak = _peak(model_wavelength, model_intensity, reference, 3 * model_fwhm_nm)
    measured_peak = _peak(measured_wavelength, measured_intensity, reference, 3 * measured_fwhm_nm)
    if model_peak <= 0 or measured_peak <= 0:
        raise NoCommonLine(f"the reference line {reference:.3f} nm has no positive peak in one of the spectra")
    return Normalisation(reference, model_peak, measured_peak)
