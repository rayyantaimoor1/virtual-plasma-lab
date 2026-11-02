"""Electron-impact rate coefficients for argon from LXCat cross-sections: Phase 2b.

A rate coefficient K says how often one electron causes a process per target atom:
number of events per second per m^3 = K * n_e * n_gas. It is the cross-section averaged over the
electrons' speeds:

    K(T_e) = integral( sigma(e) * v(e) * f(e) de ),   v(e) = sqrt(2 e e / m_e)

WHY integrate measured cross-sections instead of using a fitted formula: the old project used
"representative" fits that nobody could trace to a source (UNDERSTANDING.md, Sec. 2). Here every
number comes from the Biagi database (data/reference/manifest.json) and the chosen EEDF, so a
Druyvesteyn and a Maxwellian plasma get rates that differ for a physical reason, not a guess.

WHY a table: the solvers call K thousands of times per run. K depends only on T_e and the EEDF
shape, not on pressure or power, so it is integrated once on a T_e grid and then interpolated
(a cubic spline through ln K versus ln T_e). A test checks the table against direct integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import constants as codata
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq
from scipy.special import gamma

from plasma_twin.reference.loaders import MANIFEST_PATH, CrossSection, load_cross_sections
from plasma_twin.stage1.eedf import EEDF

ELECTRON_MASS_KG = codata.m_e
ARGON_MASS_KG = 39.948 * codata.atomic_mass  # IUPAC standard atomic weight of argon
# Energy grid for the integrals: geometric, so it is fine near threshold and at low energy, and it
# reaches the end of the Biagi tables (965 eV). Spacing near 15.76 eV is about 0.013 eV.
ENERGY_GRID_EV = np.concatenate(([0.0], np.geomspace(1e-4, 1000.0, 20000)))
# T_e range of the tables. The particle balance gives 1-4 eV in the operating envelope; the wide
# margin lets the root finder search freely without leaving the table.
TABLE_TE_EV = np.geomspace(0.5, 20.0, 240)


def _trapezoid_weights(x: np.ndarray) -> np.ndarray:
    """Weights w so that sum(w * y) is the trapezoid-rule integral of y over the grid x."""
    w = np.zeros_like(x)
    w[1:] += np.diff(x) / 2
    w[:-1] += np.diff(x) / 2
    return w


_WEIGHTS = _trapezoid_weights(ENERGY_GRID_EV)
_SPEED = np.sqrt(2 * codata.e * ENERGY_GRID_EV / ELECTRON_MASS_KG)  # m/s


@dataclass(frozen=True)
class ArgonCrossSections:
    """Biagi argon cross-sections on the common energy grid (all in m^2)."""

    ionization: np.ndarray
    ionization_threshold_ev: float
    momentum_transfer: np.ndarray  # LXCat "ELASTIC" is the momentum-transfer cross-section
    excitation_total: np.ndarray  # sum over all excited states
    excitation_energy_weighted: np.ndarray  # sum of threshold * sigma, for the energy lost (eV m^2)
    n_excitations: int


def _on_grid(section: CrossSection) -> np.ndarray:
    """Interpolate a tabulated cross-section onto the grid; zero outside the table."""
    return np.interp(ENERGY_GRID_EV, section.energy_ev, section.sigma_m2, left=0.0, right=0.0)


@lru_cache(maxsize=4)
def argon_cross_sections(manifest_path: Path = MANIFEST_PATH) -> ArgonCrossSections:
    """Load and combine the verified argon cross-sections (checksum checked by the loader)."""
    sections = load_cross_sections("Ar", manifest_path)
    ionization = [s for s in sections if s.process_type == "IONIZATION"]
    elastic = [s for s in sections if s.process_type == "ELASTIC"]
    excitations = [s for s in sections if s.process_type == "EXCITATION"]
    if len(ionization) != 1 or len(elastic) != 1 or not excitations:
        raise ValueError("Argon data must hold one ionization, one elastic and some excitation processes")
    return ArgonCrossSections(
        ionization=_on_grid(ionization[0]),
        ionization_threshold_ev=ionization[0].threshold_ev,
        momentum_transfer=_on_grid(elastic[0]),
        excitation_total=sum(_on_grid(s) for s in excitations),
        excitation_energy_weighted=sum(s.threshold_ev * _on_grid(s) for s in excitations),
        n_excitations=len(excitations),
    )


def rate_coefficient(sigma_m2: np.ndarray, eedf: EEDF) -> float:
    """K = integral(sigma v f de) in m^3/s, by direct integration on the grid."""
    return float(np.sum(_WEIGHTS * sigma_m2 * _SPEED * eedf(ENERGY_GRID_EV)))


@dataclass(frozen=True)
class WallConstants:
    """Properties of the EEDF that set the losses at a wall, as multiples of T_e.

    For a fixed shape these scale exactly with T_e, so they are computed once (at T_e = 1 eV).
    For a Maxwellian they reduce to the textbook values, which a test checks:
    screening ratio 1, escaping energy 2 T_e, floating potential ln(sqrt(M / 2 pi m)) T_e = 4.68 T_e.
    """

    screening_ratio: float  # T_s / T_e. T_s sets the Bohm speed and the ambipolar field
    escape_energy_ratio: float  # E_e / T_e: kinetic energy carried away by each electron lost
    floating_ratio: float  # V_f / T_e: floating sheath voltage at an insulated wall
    mean_speed_ratio: float  # mean electron speed / sqrt(e T_e / m_e)


@lru_cache(maxsize=8)
def wall_constants(shape: float) -> WallConstants:
    """Compute the wall constants of an EEDF shape.

    WHY not just use the Maxwellian numbers: with a Druyvesteyn EEDF there are fewer fast
    electrons, so a smaller wall potential already holds them back, and those that escape carry
    less energy. Using the Maxwellian values would overstate the power lost at the walls.

    Bohm speed: kinetic Bohm criterion for a non-Maxwellian EEDF, 1/T_s = (1/2) integral(f / e de),
    which gives T_s = T_e for a Maxwellian (Lieberman & Lichtenberg 2005, Ch. 6).
    Wall flux over a barrier V (planar wall, isotropic electrons): electrons with energy e cross
    only if e * cos^2(angle) > V, giving flux n * integral(v f (1 - V/e) / 4 de) for e > V.
    The floating potential balances this against the ion flux n u_B.
    """
    eedf = EEDF(1.0, shape)
    energy = ENERGY_GRID_EV[1:]
    f, w, v = eedf(energy), _WEIGHTS[1:], _SPEED[1:]
    # integral(f / e) has a 1/sqrt(e) spike at zero that a grid cannot resolve, so it is done
    # exactly with the Gamma identity in eedf.py: 1/T_s = Gamma(1/(2x)) / (2 e0 Gamma(3/(2x))).
    screening = 2 * eedf.energy_scale_ev * gamma(1.5 / shape) / gamma(0.5 / shape)
    bohm_speed = np.sqrt(codata.e * screening / ARGON_MASS_KG)

    def electron_flux(barrier: float, weight: np.ndarray) -> float:
        above = energy > barrier
        return float(np.sum((w * v * f * weight * (1 - barrier / energy) / 4)[above]))

    ones = np.ones_like(energy)
    floating = brentq(lambda vb: electron_flux(vb, ones) - bohm_speed, 0.0, 60.0, xtol=1e-13)
    # Mean energy of escaping electrons, measured at the plasma edge. Part of it (the barrier)
    # is handed to the ions by the sheath field and is counted there, so it is subtracted here.
    escape = electron_flux(floating, energy) / electron_flux(floating, ones) - floating
    mean_speed = float(np.sum(w * v * f)) / np.sqrt(codata.e / ELECTRON_MASS_KG)
    return WallConstants(screening, escape, floating, mean_speed)


class RateTable:
    """Rate coefficients of argon versus T_e for one EEDF shape, interpolated from a table."""

    def __init__(self, shape: float, cross_sections: ArgonCrossSections) -> None:
        self.shape = shape
        self.cross_sections = cs = cross_sections
        self.wall = wall_constants(shape)
        # Each row is one T_e; one matrix product integrates every process for every T_e at once.
        f = np.array([EEDF(te, shape)(ENERGY_GRID_EV) for te in TABLE_TE_EV])
        kernel = _WEIGHTS * _SPEED
        mass_ratio = ELECTRON_MASS_KG / ARGON_MASS_KG
        columns = {
            "ionization": cs.ionization,
            "momentum_transfer": cs.momentum_transfer,
            "excitation": cs.excitation_total,
            "excitation_energy": cs.excitation_energy_weighted,
            # Elastic recoil: an electron of energy e loses on average 2 (m/M) e per momentum-
            # transfer collision (Lieberman & Lichtenberg 2005, Ch. 3), so the energy-loss rate
            # is 2 (m/M) integral(e sigma_m v f de). Gas temperature is neglected (T_gas << T_e).
            "elastic_energy": 2 * mass_ratio * ENERGY_GRID_EV * cs.momentum_transfer,
        }
        log_te = np.log(TABLE_TE_EV)
        self._splines = {}
        for name, sigma in columns.items():
            k = f @ (kernel * sigma)
            self._splines[name] = CubicSpline(log_te, np.log(np.maximum(k, 1e-300)))

    def _k(self, name: str, te_ev: float) -> float:
        if not TABLE_TE_EV[0] <= te_ev <= TABLE_TE_EV[-1]:
            raise ValueError(f"T_e = {te_ev} eV is outside the rate table ({TABLE_TE_EV[0]}-{TABLE_TE_EV[-1]} eV)")
        return float(np.exp(self._splines[name](np.log(te_ev))))

    def ionization(self, te_ev: float) -> float:
        """K_iz in m^3/s."""
        return self._k("ionization", te_ev)

    def momentum_transfer(self, te_ev: float) -> float:
        """K_m in m^3/s. Times the gas density it gives the collision frequency nu_m used in heating."""
        return self._k("momentum_transfer", te_ev)

    def excitation(self, te_ev: float) -> float:
        """Total excitation rate coefficient, summed over all excited states, in m^3/s."""
        return self._k("excitation", te_ev)

    def collisional_energy_loss_ev(self, te_ev: float) -> float:
        """E_c: energy the electrons spend per ion-electron pair created, in eV.

        E_c = E_iz + sum_j(E_j K_j) / K_iz + 2 (m/M) <e sigma_m v> / K_iz
        (Lieberman & Lichtenberg 2005, Ch. 3). At low T_e most collisions only excite or
        heat the gas, so E_c rises steeply as T_e falls: it is the main reason a cold plasma
        needs more power per ion.
        """
        k_iz = self.ionization(te_ev)
        return (self.cross_sections.ionization_threshold_ev
                + (self._k("excitation_energy", te_ev) + self._k("elastic_energy", te_ev)) / k_iz)

    def loss_parts_ev(self, te_ev: float) -> dict[str, float]:
        """E_c split into ionization, excitation and elastic parts, in eV per ion created."""
        k_iz = self.ionization(te_ev)
        return {
            "ionization": self.cross_sections.ionization_threshold_ev,
            "excitation": self._k("excitation_energy", te_ev) / k_iz,
            "elastic": self._k("elastic_energy", te_ev) / k_iz,
        }


@lru_cache(maxsize=8)
def rate_table(shape: float, manifest_path: Path = MANIFEST_PATH) -> RateTable:
    """The rate table for an EEDF shape, built once per run of the program."""
    return RateTable(shape, argon_cross_sections(manifest_path))
