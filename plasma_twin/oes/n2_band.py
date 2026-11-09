"""The N2 second positive bands (C3Pi_u -> B3Pi_g): Phase 4e.

WHY: with nitrogen in the argon, the strongest molecular emission is the N2 "second positive"
system, with bands at 337.1 nm (0,0) and 315.9 nm (1,0). Its rotational structure depends on the
gas temperature, which is how OES measures T_gas (supervisor, B6 and Q5). The (1,0) band is used
because the (0,0) band can be overlapped by NH emission near 336 nm.

EVERYTHING HERE FOLLOWS THE RULES IN BUILD_STEPS.md (4e), FIXED BEFORE THIS CODE:
- Band wavenumbers, Franck-Condon factors and Einstein coefficients: Gilmore, Laher & Espy (1992),
  Table 9 (data/reference/constants/n2_second_positive.csv).
- How N2(C) splits between v'=0 and v'=1 when an electron excites ground-state N2: X(v=0) -> C(v')
  Franck-Condon factors, computed here from Morse potentials of the NIST constants. The same code
  must reproduce Gilmore's C -> B factors before it is trusted (a test checks this).
- Rotational structure in the singlet approximation (1Pi-1Pi: P, Q and R branches, Honl-London
  factors for Delta Lambda = 0, Lambda = 1). Real C-B bands are triplets; this simplification is
  stated and is enough for the model to fit its own spectra, not for a precise fit of a real
  high-resolution spectrum.
- F(J) = B_v J(J+1) - D_v J^2 (J+1)^2, B_v = B_e - alpha_e (v + 1/2), D_v = 4 B_e^3 / w_e^2 (Kratzer).
- Air wavelengths from vacuum wavenumbers with the Peck & Reeder (1972) refractive index used by NIST.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import constants as codata
from scipy.linalg import eigh_tridiagonal

from plasma_twin.reference.loaders import load_diatomic_constants, load_n2_second_positive, load_stage1_constants

N2_MASS_KG = 2 * 14.003074 * codata.atomic_mass  # 14N2
REDUCED_MASS_KG = N2_MASS_KG / 4  # mu = m m / (m + m) = m / 2, with m = N2_MASS / 2
STATES = {"X": "X1Sigma_g+", "B": "B3Pi_g", "C": "C3Pi_u"}
J_MAX = 60


# ---------------------------------------------------------------------------------------- level energies
def kratzer_d(state: str) -> float:
    """Centrifugal distortion D_e = 4 B_e^3 / w_e^2 (cm^-1)."""
    c = load_diatomic_constants("N2", STATES[state])
    return 4 * c["Be_cm1"] ** 3 / c["we_cm1"] ** 2


def rotational_constant(state: str, v: int) -> float:
    """B_v = B_e - alpha_e (v + 1/2) from the cited diatomic constants (cm^-1)."""
    c = load_diatomic_constants("N2", STATES[state])
    return c["Be_cm1"] - c["alpha_e_cm1"] * (v + 0.5)


def term(state: str, v: int, j: np.ndarray) -> np.ndarray:
    """Rotational energy F_v(J) in cm^-1."""
    j = np.asarray(j, dtype=float)
    return rotational_constant(state, v) * j * (j + 1) - kratzer_d(state) * (j * (j + 1)) ** 2


def honl_london(branch: str, j_lower: np.ndarray) -> np.ndarray:
    """Delta Lambda = 0, Lambda = 1 Honl-London factors indexed by the lower J'' (Herzberg)."""
    j = np.asarray(j_lower, dtype=float)
    if branch == "R":  # J' = J'' + 1
        return (j + 2) * j / (j + 1)
    if branch == "Q":  # J' = J''
        return (2 * j + 1) / (j * (j + 1))
    if branch == "P":  # J' = J'' - 1
        return (j + 1) * (j - 1) / j
    raise ValueError(branch)


def vacuum_to_air_nm(wavenumber_cm1: np.ndarray) -> np.ndarray:
    """Air wavelength (nm) from a vacuum wavenumber, with the Peck & Reeder (1972) dispersion formula."""
    sigma2 = (np.asarray(wavenumber_cm1, dtype=float) * 1e-4) ** 2  # (inverse micrometres)^2
    c = load_stage1_constants()  # the formula's coefficients, in stage1_constants.csv (Phase 15, MNT-2)
    n = 1 + c["air_dispersion_scale"] * (c["air_dispersion_a"] + c["air_dispersion_b"] / (c["air_dispersion_c"] - sigma2)
                                         + c["air_dispersion_d"] / (c["air_dispersion_e"] - sigma2))
    return 1e7 / (np.asarray(wavenumber_cm1, dtype=float) * n)


# ---------------------------------------------------------------------------------------- Franck-Condon
@lru_cache(maxsize=8)
def _morse_states(state: str, count: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Lowest vibrational wavefunctions of a Morse potential built from the NIST constants.

    Morse: V(r) = D (1 - exp(-a (r - r_e)))^2, with D = w_e^2 / (4 w_e x_e) and
    a = 2 pi c w_e sqrt(mu / (2 D)). r_e follows from B_e = h / (8 pi^2 c mu r_e^2).
    The radial equation is solved by finite differences on a fine grid.
    """
    c = load_diatomic_constants("N2", STATES[state])
    hc = codata.h * codata.c * 100  # J per cm^-1
    depth = c["we_cm1"] ** 2 / (4 * c["wexe_cm1"]) * hc
    a = 2 * np.pi * codata.c * 100 * c["we_cm1"] * np.sqrt(REDUCED_MASS_KG / (2 * depth))
    r_e = np.sqrt(codata.h / (8 * np.pi**2 * codata.c * REDUCED_MASS_KG * c["Be_cm1"] * 100))
    r = np.linspace(0.75e-10, 2.2e-10, 6000)
    dr = r[1] - r[0]
    potential = depth * (1 - np.exp(-a * (r - r_e))) ** 2
    kinetic = codata.hbar**2 / (2 * REDUCED_MASS_KG * dr**2)
    _, vectors = eigh_tridiagonal(potential + 2 * kinetic, -kinetic * np.ones(len(r) - 1),
                                  select="i", select_range=(0, count - 1))
    return r, vectors / np.sqrt(dr)  # normalised so that integral(psi^2 dr) = 1


def franck_condon(upper: str, v_upper: int, lower: str, v_lower: int) -> float:
    """|<v_upper | v_lower>|^2 on a common grid."""
    r, psi_u = _morse_states(upper)
    _, psi_l = _morse_states(lower)
    overlap = np.trapezoid(psi_u[:, v_upper] * psi_l[:, v_lower], r)
    return float(overlap**2)


def excitation_shares() -> dict[int, float]:
    """Share of electron-impact N2(C) production going into v' = 0 and v' = 1 (from X, v = 0)."""
    return {v: franck_condon("C", v, "X", 0) for v in (0, 1)}


# ---------------------------------------------------------------------------------------- bands
@lru_cache(maxsize=1)
def _band_table() -> dict[tuple[int, int], dict[str, float]]:
    return {(r["v_upper"], r["v_lower"]): r for r in load_n2_second_positive()}


def total_radiative_rate(v_upper: int) -> float:
    """Sum of Gilmore's A values over v'' = 0-10 (the rest are below 10^3 per second)."""
    return sum(r["a_per_s"] for (vu, _), r in _band_table().items() if vu == v_upper)


def band_lines(v_upper: int, v_lower: int, rotational_temperature_k: float) -> dict[float, float]:
    """Rotational lines of one band as {air wavelength (nm): share of the band power}."""
    origin = _band_table()[(v_upper, v_lower)]["wavenumber_cm1"]
    j_lower = np.arange(1, J_MAX + 1)
    hc_over_k = codata.h * codata.c * 100 / codata.k
    out: dict[float, float] = {}
    total = 0.0
    for branch, shift in (("R", 1), ("Q", 0), ("P", -1)):
        j_upper = j_lower + shift
        keep = j_upper >= 1
        jl, ju = j_lower[keep], j_upper[keep]
        upper_term = term("C", v_upper, ju)
        wavenumber = origin + upper_term - term("B", v_lower, jl)
        power = wavenumber**4 * honl_london(branch, jl) * np.exp(-upper_term * hc_over_k / rotational_temperature_k)
        for wl, p in zip(vacuum_to_air_nm(wavenumber), power):
            out[float(wl)] = out.get(float(wl), 0.0) + float(p)
            total += float(p)
    return {wl: p / total for wl, p in out.items()}


def band_powers(n2c_production_m3_s: float) -> dict[tuple[int, int], float]:
    """Power (W/m^3) of each (v', v'') band from the N2(C) production rate of the mixture model."""
    shares = excitation_shares()
    table = _band_table()
    out = {}
    for (vu, vl), row in table.items():
        population = n2c_production_m3_s * shares[vu] / total_radiative_rate(vu)
        out[(vu, vl)] = population * row["a_per_s"] * codata.h * codata.c * 100 * row["wavenumber_cm1"]
    return out


def n2_lines(n2c_production_m3_s: float, rotational_temperature_k: float) -> dict[float, float]:
    """Every rotational line of every band, in W/m^3, keyed by air wavelength."""
    out: dict[float, float] = {}
    for band, power in band_powers(n2c_production_m3_s).items():
        for wl, share in band_lines(*band, rotational_temperature_k).items():
            out[wl] = out.get(wl, 0.0) + power * share
    return out
