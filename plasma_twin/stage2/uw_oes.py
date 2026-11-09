"""Synthetic spectrum of the bubble discharge and n_e from the H-alpha Stark width: Phase 7 (FR9.4).

RULES (BUILD_STEPS.md, Phase 7, fixed before this code):
- Emission rates use Itikawa's EMISSION cross-sections for e + H2O: OH(A-X) 309 nm, H Balmer alpha,
  O 777 and O 844 nm. photons / (m^3 s) = n_e n_H2O k_em(T_e), in the channel during the pulse.
  O I from dissociative excitation of O2 needs e-O2 emission data we do not have; it is left out.
- OH(A-X) (0,0) band: the band origin from the NIST/Huber-Herzberg constants already in
  diatomic_constants.csv; the rotational structure is drawn as a single Q-branch-like series,
  nu = nu_00 + (B' - B'') N(N + 1), weighted (2N + 1) exp(-hc B' N(N+1) / kT) at the gas temperature.
  This is APPROXIMATE (no spin splitting, no P and R branches) and is labelled so.
- H-alpha: NIST's merged 656.279 nm multiplet (fine structure, 0.02 nm, not resolved). Its shape is a
  Voigt: Gaussian = instrument and Doppler; Lorentzian = Stark, FWHM = 8.33e-3 nm (n_e / 1e20 m^-3)^(2/3)
  (van der Horst et al. 2012, from the tables of Gigosos et al. 2003, T_e = 10,000 K, mu* = 10).
- Stark n_e: fit the H-alpha line with the Gaussian width fixed, take the Lorentzian FWHM, invert the
  relation. Only when the instrument FWHM is smaller than the Stark FWHM (FR9.4); not in O2-only mode.
- O I lines are spread over the triplet components in proportion to g A (NIST).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import constants as codata
from scipy.optimize import curve_fit
from scipy.special import voigt_profile

from plasma_twin.oes.n2_band import vacuum_to_air_nm
from plasma_twin.oes.spectrum import FWHM_TO_SIGMA, SpectrometerSettings, doppler_fwhm_nm
from plasma_twin.reference.loaders import load_atomic_lines, load_diatomic_constants, load_stage2_constants
from plasma_twin.stage1.rates import MOLECULE_MASS_KG
from plasma_twin.stage2.bubble_model import BubbleResult, h2o_rates

H, C, K_B = codata.h, codata.c, codata.k
H_MASS_KG = codata.m_p + codata.m_e  # CODATA; the binding energy (13.6 eV) changes it by 1e-8
O_MASS_KG = MOLECULE_MASS_KG["O2"] / 2
OH_MASS_KG = O_MASS_KG + H_MASS_KG
HC_OVER_K = H * C * 100 / K_B  # cm K: converts a wavenumber in cm^-1 to a temperature
OH_N_MAX = 30


class StarkUnavailable(ValueError):
    """The Stark width cannot be measured with these settings."""


@dataclass(frozen=True)
class UnderwaterSpectrum:
    wavelength_nm: np.ndarray
    intensity: np.ndarray  # W m^-3 nm^-1, in the channel during the pulse
    line_power_w_m3: dict[str, float]  # per emitter: OH(A-X), H-alpha, O 777, O 844
    stark_fwhm_nm: float
    h_alpha_nm: float
    gaussian_fwhm_nm: float  # instrument and Doppler at H-alpha
    settings: SpectrometerSettings
    notes: tuple[str, ...] = field(default_factory=tuple)


def stark_fwhm_nm(ne_m3: float) -> float:
    """H-alpha Stark width for an electron density, from the cited Gigosos fit."""
    c = load_stage2_constants()
    return c["stark_halpha_coeff"] * (ne_m3 / 1e20) ** c["stark_halpha_exponent"]


def ne_from_stark(fwhm_nm: float) -> float:
    """The electron density that gives a measured H-alpha Stark width (the inverse of stark_fwhm_nm)."""
    c = load_stage2_constants()
    return 1e20 * (fwhm_nm / c["stark_halpha_coeff"]) ** (1 / c["stark_halpha_exponent"])


def _components(species: str, low: float, high: float) -> list[tuple[float, float]]:
    """(wavelength, share) of each NIST component in a window, shares in proportion to g A."""
    lines = load_atomic_lines(species)
    inside = (lines.wavelength_nm >= low) & (lines.wavelength_nm <= high)
    weight = lines.g_upper[inside] * lines.a_ki_per_s[inside]
    return list(zip(lines.wavelength_nm[inside], weight / weight.sum()))


def h_alpha_nm() -> float:
    """NIST's merged H-alpha multiplet (the row with g_upper = 18)."""
    lines = load_atomic_lines("H I")
    pick = (lines.wavelength_nm > 656.0) & (lines.wavelength_nm < 656.6) & (lines.g_upper == 18)
    if pick.sum() != 1:
        raise ValueError("NIST H I data lack the merged H-alpha multiplet")
    return float(lines.wavelength_nm[pick][0])


def oh_band_lines(temperature_k: float) -> list[tuple[float, float]]:
    """(air wavelength, share) of the approximate OH(A-X) (0,0) Q-branch-like series."""
    upper, lower = load_diatomic_constants("OH", "A2Sigma+"), load_diatomic_constants("OH", "X2Pi")

    def g0(s: dict[str, float]) -> float:  # vibrational term value of v = 0
        return s["we_cm1"] / 2 - s["wexe_cm1"] / 4

    origin = upper["Te_cm1"] + g0(upper) - g0(lower)
    b_up = upper["Be_cm1"] - upper["alpha_e_cm1"] / 2
    b_low = lower["Be_cm1"] - lower["alpha_e_cm1"] / 2
    n = np.arange(1, OH_N_MAX + 1)
    weight = (2 * n + 1) * np.exp(-HC_OVER_K * b_up * n * (n + 1) / temperature_k)
    wavelength = vacuum_to_air_nm(origin + (b_up - b_low) * n * (n + 1))
    return list(zip(wavelength, weight / weight.sum()))


def emission_photons(bubble: BubbleResult) -> dict[str, float]:
    """Photons per volume per second of each emitter in the channel during the pulse."""
    if bubble.water_fraction <= 0:
        return {"OH(A-X)": 0.0, "H-alpha": 0.0, "O 777": 0.0, "O 844": 0.0}
    rates, _, _ = h2o_rates()
    n_h2o = bubble.gas_density_m3 * bubble.water_fraction
    keys = {"OH(A-X)": "oh_a", "H-alpha": "h_alpha", "O 777": "o_777", "O 844": "o_844"}
    return {name: bubble.ne_m3 * n_h2o * rates.k(key, bubble.te_ev) for name, key in keys.items()}


def build(bubble: BubbleResult, settings: SpectrometerSettings) -> UnderwaterSpectrum:
    """Draw the four emitters on the spectrometer's grid, then add its seeded noise."""
    settings.validate()
    t = bubble.gas_temperature_k
    photons = emission_photons(bubble)
    ha = h_alpha_nm()
    stark = stark_fwhm_nm(bubble.ne_m3) if photons["H-alpha"] > 0 else 0.0
    gauss_ha = float(np.hypot(settings.fwhm_nm, doppler_fwhm_nm(ha, t, H_MASS_KG)))
    # (emitter, wavelength, share of its photons, gaussian fwhm, lorentzian fwhm)
    lines = [("OH(A-X)", wl, share, float(np.hypot(settings.fwhm_nm, doppler_fwhm_nm(wl, t, OH_MASS_KG))), 0.0)
             for wl, share in oh_band_lines(t)]
    lines.append(("H-alpha", ha, 1.0, gauss_ha, stark))
    for name, low, high in (("O 777", 776.9, 777.8), ("O 844", 844.4, 844.9)):  # windows around the NIST triplets
        lines += [(name, wl, share, float(np.hypot(settings.fwhm_nm, doppler_fwhm_nm(wl, t, O_MASS_KG))), 0.0)
                  for wl, share in _components("O I", low, high)]
    powers = {name: 0.0 for name in photons}
    step = settings.fwhm_nm / 5
    grid = np.arange(settings.start_nm, settings.end_nm + step / 2, step)
    intensity = np.zeros_like(grid)
    for name, wl, share, g_fwhm, l_fwhm in lines:
        power = photons[name] * share * H * C / (wl * 1e-9)  # W/m^3
        powers[name] += power
        if power <= 0 or not settings.start_nm <= wl <= settings.end_nm:
            continue
        half = 8 * g_fwhm + 100 * l_fwhm
        lo, hi = np.searchsorted(grid, wl - half), np.searchsorted(grid, wl + half)
        intensity[lo:hi] += power * voigt_profile(grid[lo:hi] - wl, g_fwhm * FWHM_TO_SIGMA, l_fwhm / 2)
    if settings.noise_percent > 0 and intensity.max() > 0:
        rng = np.random.default_rng(settings.seed)
        intensity = intensity + rng.normal(0.0, settings.noise_percent / 100 * intensity.max(), size=intensity.shape)
    notes = ["OH(A-X) band drawn approximately: one Q-branch-like series, no spin splitting",
             "O I from O2 dissociative excitation is not included (no e-O2 emission data)"]
    return UnderwaterSpectrum(grid, intensity, powers, stark, ha, gauss_ha, settings, tuple(notes))


@dataclass(frozen=True)
class StarkResult:
    ne_m3: float
    lorentzian_fwhm_nm: float
    window_nm: tuple[float, float]


def stark_density(spectrum: UnderwaterSpectrum) -> StarkResult:
    """Fit H-alpha with the Gaussian width fixed and invert the Stark FWHM to n_e (FR9.4)."""
    if spectrum.line_power_w_m3["H-alpha"] <= 0:
        raise StarkUnavailable("no H-alpha: the bubble gas has no water vapour (O2-only mode)")
    if spectrum.settings.fwhm_nm >= spectrum.stark_fwhm_nm:
        raise StarkUnavailable(f"instrument FWHM {spectrum.settings.fwhm_nm} nm is not smaller than the expected Stark "
                               f"FWHM {spectrum.stark_fwhm_nm:.4f} nm; use a finer resolution")
    centre = spectrum.h_alpha_nm
    half = 10 * (spectrum.gaussian_fwhm_nm + spectrum.stark_fwhm_nm)
    window = (spectrum.wavelength_nm >= centre - half) & (spectrum.wavelength_nm <= centre + half)
    x, y = spectrum.wavelength_nm[window], spectrum.intensity[window]
    sigma = spectrum.gaussian_fwhm_nm * FWHM_TO_SIGMA

    def model(w, area, mid, lorentz, background):
        return area * voigt_profile(w - mid, sigma, abs(lorentz) / 2) + background

    guess = (np.trapezoid(y, x), centre, spectrum.gaussian_fwhm_nm, 0.0)
    (area, mid, lorentz, background), _ = curve_fit(model, x, y, p0=guess, maxfev=20000)
    lorentz = abs(lorentz)
    return StarkResult(ne_from_stark(lorentz), lorentz, (float(x[0]), float(x[-1])))
