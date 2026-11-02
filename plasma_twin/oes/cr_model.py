"""Collisional-radiative (CR) model of the argon 1s and 2p levels: Phase 4a.

WHY: an optical emission spectrum shows light from the 2p levels falling to the 1s levels (the
bright 690-850 nm argon lines). How bright each line is depends on how many atoms sit in each 2p
level, and that depends on T_e, n_e and the EEDF. A CR model balances, for every level, the ways in
(electron excitation, cascades) against the ways out (radiation, electron collisions, wall losses).
It turns the plasma state from the global model into level populations, and from those into lines.

WHAT IS SOLVED (rules fixed in BUILD_STEPS.md, Phase 4a, before this code):
- 14 levels, each on its own: 1s5, 1s4, 1s3, 1s2 and 2p10 ... 2p1.
- Electron excitation from the ground state and from every 1s level: integrated from the LXCat BSR
  cross-sections (Zatsarinny & Bartschat) with the model's own EEDF. De-excitation by electrons uses
  the same cross-sections through detailed balance on the cross-section (Klein-Rosseland):
      sigma_down(e) = (g_low / g_up) * ((e + dE) / e) * sigma_up(e + dE)
  which stays correct for a non-Maxwellian EEDF.
- Ionization from 1s and 2p: the published fits used in Phase 2d (Kemaneci Table III, rows 8 and 15).
- Radiation: every 2p -> 1s line from NIST (300-1400 nm), matched to its levels by energy. Lines
  ending on a 1s level are partly re-absorbed; Mewe's escape factor (Eqs. 27-28 of arXiv:2402.08092)
  scales their rate. The resonant 1s levels radiate to the ground at the trapped rate of Phase 2d.
- 1s atoms also diffuse to the walls (Chantry, Phase 2d) and, in mixtures, are quenched by N2 and O2.

Left out, stated: cascades from levels above 2p; 2p-2p electron mixing and 2p quenching by atoms
(both thousands of times slower than 2p radiation, which is ~10^7-10^8 per second); metastable
pooling (a few per cent of 1s loss). Without pooling the balances are linear once the escape
factors are known, so they are solved as a linear system and repeated until the escape factors settle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import constants as codata

from plasma_twin.reference.loaders import (
    CrossSection,
    load_bsr_argon,
    load_cross_sections,
    read_nist_lines,
    verified_path,
)
from plasma_twin.stage1 import argon_kinetics as kin
from plasma_twin.stage1.eedf import EEDF
from plasma_twin.stage1.rates import ARGON_MASS_KG, ENERGY_GRID_EV, _SPEED, _WEIGHTS

LEVELS_1S = ("1s5", "1s4", "1s3", "1s2")
LEVELS_2P = tuple(f"2p{i}" for i in range(10, 0, -1))  # 2p10 (lowest) ... 2p1
LEVELS = LEVELS_1S + LEVELS_2P
INDEX = {name: i for i, name in enumerate(LEVELS)}
METASTABLE = ("1s5", "1s3")
RESONANT = ("1s4", "1s2")


@dataclass(frozen=True)
class Line:
    wavelength_nm: float  # in air (NIST)
    upper: str
    lower: str
    a_per_s: float
    g_upper: int
    g_lower: int
    upper_energy_ev: float


@dataclass(frozen=True)
class LevelData:
    energy_ev: dict[str, float]  # from the NIST line list (measured energies)
    weight: dict[str, int]  # statistical weight g = 2J + 1
    lines: tuple[Line, ...]


def _normalise(label: str) -> str:
    """BSR writes 4s' as 4s! and sometimes puts a space before [: make one spelling."""
    return label.replace("!", "'").replace(" ", "")


@lru_cache(maxsize=1)
def racah_to_paschen() -> dict[str, str]:
    """Map Racah names to Paschen names, read from the BSR file itself.

    Its ground-state excitations are labelled like 'Ar(4p[1/2]1, 3S1, p10)', pairing both names.
    """
    out = {}
    for s in load_bsr_argon():
        if s.target == "Ar" and s.process_type == "EXCITATION":
            match = re.match(r"Ar\(([^,]+),\s*\S+,\s*(\S+)\)", s.product)
            if match:
                racah, paschen = _normalise(match.group(1)), match.group(2)
                if paschen.startswith("p"):
                    paschen = "2" + paschen  # BSR writes p10 for 2p10
                if paschen in LEVELS:
                    out[racah] = paschen
    if set(out.values()) != set(LEVELS):
        raise ValueError(f"BSR labels do not cover every 1s and 2p level: {sorted(set(LEVELS) - set(out.values()))}")
    return out


def _paschen_of(label: str) -> str | None:
    """Paschen name of a BSR target or product such as 'Ar(4s[3/2]2)' or 'Ar(4p[1/2]1, 3S1, p10)'."""
    inner = _normalise(label.strip())[3:-1].split(",")[0]
    return racah_to_paschen().get(inner)


@lru_cache(maxsize=1)
def level_data() -> LevelData:
    """Level energies, weights and 2p -> 1s lines from NIST, each level identified by its energy.

    Level energies are anchored on the Biagi thresholds, which use measured Paschen energies, and
    every NIST line must match both its levels within 4 meV (2p5 and 2p4 are only 10 meV apart).
    """
    biagi = {s.product[3:-1].lower(): s.threshold_ev for s in load_cross_sections("Ar")
             if s.process_type == "EXCITATION" and s.product[3:5] in ("1S", "2P")}
    names, energies = list(biagi), np.array(list(biagi.values()))
    lines, level_energy, weight = [], {}, {}
    for dataset in ("nist_ar_i", "nist_ar_i_ir"):
        nist = read_nist_lines(verified_path(dataset), "Ar I")
        for i in range(len(nist.wavelength_nm)):
            du, dl = np.abs(energies - nist.upper_energy_ev[i]), np.abs(energies - nist.lower_energy_ev[i])
            if du.min() > 0.004 or dl.min() > 0.004:
                continue
            upper, lower = names[int(du.argmin())], names[int(dl.argmin())]
            if not (upper.startswith("2p") and lower.startswith("1s")):
                continue
            level_energy[upper], level_energy[lower] = float(nist.upper_energy_ev[i]), float(nist.lower_energy_ev[i])
            weight[upper], weight[lower] = int(nist.g_upper[i]), int(nist.g_lower[i])
            lines.append(Line(float(nist.wavelength_nm[i]), upper, lower, float(nist.a_ki_per_s[i]),
                              int(nist.g_upper[i]), int(nist.g_lower[i]), float(nist.upper_energy_ev[i])))
    missing = set(LEVELS) - set(level_energy)
    if missing:
        raise ValueError(f"NIST lines do not reach the levels {sorted(missing)}")
    return LevelData(level_energy, weight, tuple(sorted(lines, key=lambda line: line.wavelength_nm)))


@lru_cache(maxsize=1)
def _bsr_processes() -> tuple[tuple[str, str, float, np.ndarray], ...]:
    """(from, to, threshold, sigma on the grid) for every BSR excitation between tracked levels."""
    out = []
    for s in load_bsr_argon():
        if s.process_type != "EXCITATION":
            continue
        source = "ground" if s.target == "Ar" else _paschen_of(s.target)
        target = _paschen_of(s.product)
        if source is None or target is None or source == target:
            continue
        sigma = np.interp(ENERGY_GRID_EV, s.energy_ev, s.sigma_m2, left=0.0, right=0.0)
        out.append((source, target, s.threshold_ev, sigma))
    return tuple(out)


def _superelastic(sigma_up: np.ndarray, threshold: float, g_low: int, g_up: int) -> np.ndarray:
    """Klein-Rosseland: the de-excitation cross-section from the excitation one (see module docstring)."""
    e = ENERGY_GRID_EV
    shifted = np.interp(e + threshold, e, sigma_up, right=0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(e > 0, (g_low / g_up) * (e + threshold) / e * shifted, 0.0)


def escape_factor(lower_density_m3: float, line: Line, gas_temperature_k: float, length_m: float) -> float:
    """Mewe's escape factor: the fraction of photons of a line that leave the plasma without re-absorption."""
    lam = line.wavelength_nm * 1e-9
    kappa = (lower_density_m3 * line.a_per_s * (line.g_upper / line.g_lower) * lam**3 / (8 * np.pi)
             * np.sqrt(ARGON_MASS_KG / (2 * np.pi * codata.k * gas_temperature_k)))
    x = kappa * length_m
    return float((2 - np.exp(-1e-3 * x)) / (1 + x))


@dataclass(frozen=True)
class CRResult:
    populations_m3: dict[str, float]
    escape_factors: dict[float, float]  # by wavelength (nm)
    line_emission_w_m3: dict[float, float]  # power emitted per m^3 in each line
    lines: tuple[Line, ...]
    iterations: int
    balance_residual: float  # largest |gain - loss| / loss over the 14 levels, with the final escape factors


def solve_cr(te_ev: float, ne_m3: float, argon_density_m3: float, shape: float, gas_temperature_k: float,
             gap_m: float, radius_m: float, extra_metastable_loss_per_s: float = 0.0,
             electron_collisions: bool = True) -> CRResult:
    """Populations of the 14 levels for a given plasma state (all inputs from the global model)."""
    data = level_data()
    eedf = EEDF(te_ev, shape)
    f_kernel = _WEIGHTS * _SPEED * eedf(ENERGY_GRID_EV)
    n = len(LEVELS)
    loss = np.zeros(n)  # out of each level, per second (diagonal)
    coupling = np.zeros((n, n))  # coupling[i, j]: rate from level j into level i, per second
    source = np.zeros(n)  # from the ground state, per m^3 per second

    if electron_collisions:
        for origin, target, threshold, sigma in _bsr_processes():
            k_up = float(np.sum(f_kernel * sigma))
            if origin == "ground":
                source[INDEX[target]] += ne_m3 * argon_density_m3 * k_up
                # De-excitation to the ground state is a loss of the excited level.
                g_ground = 1
                k_down = float(np.sum(f_kernel * _superelastic(sigma, threshold, g_ground, data.weight[target])))
                loss[INDEX[target]] += ne_m3 * k_down
            else:
                i, j = INDEX[origin], INDEX[target]
                coupling[j, i] += ne_m3 * k_up
                loss[i] += ne_m3 * k_up
                k_down = float(np.sum(f_kernel * _superelastic(sigma, threshold, data.weight[origin], data.weight[target])))
                coupling[i, j] += ne_m3 * k_down
                loss[j] += ne_m3 * k_down
        k = kin.electron_rates(te_ev)
        for name in LEVELS_1S:
            loss[INDEX[name]] += ne_m3 * k["m_ionization"]
        for name in LEVELS_2P:
            loss[INDEX[name]] += ne_m3 * k["p_ionization"]

    k_wall = kin.wall_loss_rate(gap_m, radius_m, argon_density_m3, gas_temperature_k)
    for name in LEVELS_1S:
        loss[INDEX[name]] += k_wall
    for name in METASTABLE:
        loss[INDEX[name]] += argon_density_m3 * kin.K_GROUND_QUENCH_M + extra_metastable_loss_per_s
    for name in RESONANT:
        loss[INDEX[name]] += kin.A_RESONANT_TRAPPED

    length = gap_m / 2  # shortest way out of the slab-shaped plasma (BUILD_STEPS.md, 4a)
    def system(escape: dict[float, float]) -> tuple[np.ndarray, np.ndarray]:
        matrix = coupling.copy() * -1
        diag = loss.copy()
        for line in data.lines:
            rate = line.a_per_s * escape[line.wavelength_nm]
            u, lo = INDEX[line.upper], INDEX[line.lower]
            diag[u] += rate
            matrix[lo, u] -= rate
        matrix[np.diag_indices(n)] += diag
        return matrix, diag

    populations = np.zeros(n)
    escape = {line.wavelength_nm: 1.0 for line in data.lines}
    for iteration in range(1, 101):
        matrix, _ = system(escape)
        new = np.linalg.solve(matrix, source)
        new_escape = {line.wavelength_nm: escape_factor(new[INDEX[line.lower]], line, gas_temperature_k, length)
                      for line in data.lines}
        settled = np.allclose(new, populations, rtol=1e-12, atol=0)
        populations, escape = new, new_escape
        if settled:
            break
    matrix, diag = system(escape)
    with np.errstate(divide="ignore", invalid="ignore"):
        relative = np.abs(matrix @ populations - source) / (diag * populations)
    residual = float(np.nanmax(relative)) if np.any(populations > 0) else 0.0
    pops = {name: float(populations[INDEX[name]]) for name in LEVELS}
    photon_energy = lambda line: codata.h * codata.c / (line.wavelength_nm * 1e-9)  # noqa: E731
    emission = {line.wavelength_nm: pops[line.upper] * line.a_per_s * escape[line.wavelength_nm] * photon_energy(line)
                for line in data.lines}
    return CRResult(pops, escape, emission, data.lines, iteration, residual)


def solve_cr_for(result) -> CRResult:
    """Run the CR model on a solved global-model point (Stage1Result)."""
    from plasma_twin.stage1.eedf import SHAPES
    from plasma_twin.stage1.mixtures import K_QUENCH_N2, K_QUENCH_O2_DISSOCIATING, K_QUENCH_O2_TO_GROUND
    x, m = result.inputs, result.mixture
    argon = m.get("argon_density_m3", result.gas_density_m3)
    quench = (m.get("n2_density_m3", 0.0) * K_QUENCH_N2
              + m.get("o2_density_m3", 0.0) * (K_QUENCH_O2_TO_GROUND + K_QUENCH_O2_DISSOCIATING))
    return solve_cr(result.te_ev, result.ne_center_m3, argon, SHAPES[x.eedf], x.gas_temperature_k,
                    x.electrode_gap_m, x.electrode_radius_m, quench)
