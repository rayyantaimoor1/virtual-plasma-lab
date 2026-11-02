"""Synthetic emission spectrum: Phase 4b.

WHY: a real spectrometer does not see sharp lines. Each line is smeared by the instrument (its
resolution, the FWHM) and by the motion of the emitting atoms (Doppler broadening). Noise is added on
top. This module turns the CR model's line powers into what a spectrometer would record, so that the
analysis tools (Boltzmann plot, line ratios, gas temperature) can be tested on realistic input, and
later on measured spectra in the same format.

RULES (BUILD_STEPS.md, Phase 4b, fixed before this code):
- Each line emits n_upper * A * escape * h c / lambda (W/m^3), at its NIST air wavelength.
- Its shape is a Gaussian whose width combines the instrument FWHM and the Doppler FWHM in quadrature
  (both are Gaussian, and the widths of convolved Gaussians add in quadrature).
- The area under each line equals its power, so the spectrum is in W m^-3 nm^-1.
- The grid has five points per FWHM; noise is Gaussian with a standard deviation of a set percentage
  of the peak, from a seeded random generator, so the same seed always gives the same spectrum.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import constants as codata

from plasma_twin.config.loader import load_envelope
from plasma_twin.stage1.rates import ARGON_MASS_KG

FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


class SpectrumSettingsOutOfRange(ValueError):
    """A spectrometer setting lies outside the envelope (E3)."""


def doppler_fwhm_nm(wavelength_nm: float, gas_temperature_k: float, mass_kg: float = ARGON_MASS_KG) -> float:
    """Doppler FWHM: lambda * sqrt(8 k T ln2 / (M c^2)). About 0.0015 nm for argon at 750 nm and 300 K."""
    return float(wavelength_nm * np.sqrt(8 * codata.k * gas_temperature_k * np.log(2) / (mass_kg * codata.c**2)))


@dataclass(frozen=True)
class SpectrometerSettings:
    fwhm_nm: float
    start_nm: float
    end_nm: float
    noise_percent: float
    seed: int = 0

    @classmethod
    def defaults(cls, **overrides: float) -> "SpectrometerSettings":
        env = load_envelope()["oes"]
        values = {"fwhm_nm": env["resolution_fwhm_nm"]["default"], "start_nm": env["wavelength_start_nm"]["default"],
                  "end_nm": env["wavelength_end_nm"]["default"], "noise_percent": env["noise_percent_of_peak"]["default"]}
        values.update(overrides)
        return cls(**values)

    def validate(self) -> None:
        env = load_envelope()["oes"]
        for value, key in ((self.fwhm_nm, "resolution_fwhm_nm"), (self.start_nm, "wavelength_start_nm"),
                           (self.end_nm, "wavelength_end_nm"), (self.noise_percent, "noise_percent_of_peak")):
            low, high = env[key]["min"], env[key]["max"]
            if not low <= value <= high:
                raise SpectrumSettingsOutOfRange(f"{key} = {value} is outside {low}-{high}")
        if self.end_nm <= self.start_nm:
            raise SpectrumSettingsOutOfRange("the wavelength range must end after it starts")


@dataclass(frozen=True)
class Spectrum:
    wavelength_nm: np.ndarray
    intensity: np.ndarray  # W m^-3 nm^-1
    line_power_w_m3: dict[float, float]  # the lines drawn, by wavelength
    settings: SpectrometerSettings
    gas_temperature_k: float


def build_spectrum(line_power_w_m3: dict[float, float], gas_temperature_k: float, settings: SpectrometerSettings,
                   mass_kg: float = ARGON_MASS_KG, masses_kg: dict[float, float] | None = None) -> Spectrum:
    """Draw every line inside the window as a Gaussian of the right area, then add seeded noise.

    `masses_kg` gives the emitter mass of particular lines (N2 lines are lighter than argon, so their
    Doppler width differs); other lines use `mass_kg`.
    """
    settings.validate()
    step = settings.fwhm_nm / 5
    grid = np.arange(settings.start_nm, settings.end_nm + step / 2, step)
    intensity = np.zeros_like(grid)
    drawn = {}
    for wavelength, power in line_power_w_m3.items():
        if not settings.start_nm <= wavelength <= settings.end_nm or power <= 0:
            continue
        mass = masses_kg.get(wavelength, mass_kg) if masses_kg else mass_kg
        width = np.hypot(settings.fwhm_nm, doppler_fwhm_nm(wavelength, gas_temperature_k, mass))
        sigma = width * FWHM_TO_SIGMA
        lo = max(int((wavelength - 8 * sigma - settings.start_nm) / step), 0)
        hi = min(int((wavelength + 8 * sigma - settings.start_nm) / step) + 2, len(grid))
        x = grid[lo:hi]
        intensity[lo:hi] += power * np.exp(-0.5 * ((x - wavelength) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
        drawn[wavelength] = power
    if settings.noise_percent > 0 and intensity.max() > 0:
        rng = np.random.default_rng(settings.seed)
        intensity = intensity + rng.normal(0.0, settings.noise_percent / 100 * intensity.max(), size=intensity.shape)
    return Spectrum(grid, intensity, drawn, settings, gas_temperature_k)


def spectrum_for(result, settings: SpectrometerSettings | None = None) -> Spectrum:
    """The spectrum of a solved global-model point (Stage1Result): CR model, then the spectrometer."""
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.oes.n2_band import N2_MASS_KG, n2_lines
    cr = solve_cr_for(result)
    lines = dict(cr.line_emission_w_m3)
    masses = {}
    production = result.mixture.get("n2c_excitation_m3_s", 0.0)
    if production > 0:  # N2 second positive bands, only when N2 is present (4e)
        for wl, power in n2_lines(production, result.inputs.gas_temperature_k).items():
            lines[wl] = lines.get(wl, 0.0) + power
            masses[wl] = N2_MASS_KG
    return build_spectrum(lines, result.inputs.gas_temperature_k, settings or SpectrometerSettings.defaults(),
                          masses_kg=masses)
