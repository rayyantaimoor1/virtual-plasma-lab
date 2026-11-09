"""Excited argon atoms and two-step ionization: Phase 2d.

WHY: ionizing a ground-state argon atom costs 15.76 eV, far above a typical electron energy. An
atom already excited to a 4s level (about 11.6 eV) needs only about 4.2 eV more, and a 4p atom
about 2.6 eV. Once n_e reaches about 10^16 m^-3, enough atoms sit in these levels that this two-step
route matters, and the plasma can be sustained at a lower T_e. The first benchmark comparison
showed a measured T_e lower than ground-state ionization alone allows
(docs/validation/phase2_stage1_benchmarks.md).

THE LEVELS (lumped, as in the Gudmundsson argon set):
    m  4s metastables (1s5, 1s3): cannot radiate, so they live until a collision or the wall.
    r  4s resonant (1s4, 1s2): radiate, but the photon is re-absorbed many times ("trapped").
    p  4p (2p1-2p10): radiate within about 30 ns.

RATES. Excitation from the ground state is integrated from the Biagi cross-sections with the chosen
EEDF (rates.py). Processes that start from an excited atom are not in the downloaded data, so they
use the published rate coefficients of Kemaneci et al., arXiv:1612.07268 (2016), Table III (the
Gudmundsson argon set). The row number is given beside each one below. These are Maxwellian fits;
evaluating them at the T_e of a Druyvesteyn plasma is an approximation.

Left out on purpose (also stated in BUILD_STEPS.md, Phase 2d, before the second comparison):
row 11 has no reference and an impossibly large value for a collision between two atoms; row 12
(charge exchange) changes no density; rows 27-33 (dimer ions, recombination) are negligible at
n_e of about 10^16 m^-3.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import constants as codata

from plasma_twin.reference.loaders import load_stage1_constants
from plasma_twin.stage1.rates import ARGON_MASS_KG, RateTable

# Lumped level energies in eV. E_m and E_p follow from the published two-step thresholds
# (rows 8 and 15: 15.76 - 4.20 and 15.76 - 2.61); E_r is the mean of 1s4 and 1s2 in the Biagi file.
E_IONIZATION = 15.76
E_METASTABLE = E_IONIZATION - 4.20
E_RESONANT = (11.624 + 11.828) / 2
E_4P = E_IONIZATION - 2.61

# Radiative rates in 1/s (rows 23-26). Row 23 is the effective rate of the trapped resonant levels.
A_RESONANT_TRAPPED = 1.0e5
A_4P_TO_GROUND = 3.2e7
A_4P_TO_METASTABLE = 3.0e7
A_4P_TO_RESONANT = 3.0e7

# Heavy-particle rate coefficients in m^3/s.
K_POOLING_MM = 6.4e-16  # row 14: Ar(4s_m) + Ar(4s_m) -> Ar + Ar+ + e
K_POOLING_PP = 5.0e-16  # row 14: Ar(4p) + Ar(4p) -> Ar + Ar+ + e
K_POOLING_MR = 2.1e-15  # row 13: Ar(4s_m) + Ar(4s_r) -> Ar + Ar+ + e
K_GROUND_QUENCH_M = 2.1e-21  # row 19: Ar + Ar(4s_m) -> 2Ar

# Diffusion of excited atoms in argon: D = D0 (p0/p) (T/T0)^1.92 with D0 = 0.073 cm^2/s at
# 273.15 K and 1 atm (Zhakhovskii & Nishihara, arXiv:physics/0507076, Eq. 13).
D0_M2_S = 0.073e-4
D0_TEMPERATURE_K = 273.15
D0_PRESSURE_PA = 101325.0
D_TEMPERATURE_EXPONENT = 1.92
WALL_DEEXCITATION_PROBABILITY = 1.0  # every excited atom that reaches a wall returns to the ground state


ELECTRON_PROCESSES = ("m_to_ground", "m_ionization", "m_to_r", "m_to_p", "p_ionization", "p_to_r", "p_to_m", "p_to_ground",
                      "r_to_ground", "r_to_m", "r_to_p")  # Table III rows 7-10, 15-18, 20-22


def _electron_fits() -> tuple[tuple[str, float, float, float], ...]:
    """(process, A, n, E) of k = A Te^n exp(-E/Te), from data/reference/constants/stage1_constants.csv (Phase 15, MNT-2)."""
    c = load_stage1_constants()
    return tuple((p, c[f"ar_{p}_A"], c.get(f"ar_{p}_n", 0.0), c.get(f"ar_{p}_E", 0.0)) for p in ELECTRON_PROCESSES)


def electron_rates(te: float) -> dict[str, float]:
    """Rate coefficients (m^3/s) of electron collisions with excited atoms, Table III rows 7-22.

    Each is the published Maxwellian fit k = A Te^n exp(-E/Te). A missing n or E is 0, and te**0 and exp(-0/te) are
    exactly 1, so the values are the same, bit for bit, as when the fits were written out here (Phase 15 check).
    """
    return {p: a * te**n * np.exp(-e / te) for p, a, n, e in _electron_fits()}


# Energy each electron collision takes from (+) or gives to (-) the electron, in eV.
ELECTRON_ENERGY_CHANGE = {
    "m_to_ground": -E_METASTABLE, "m_ionization": E_IONIZATION - E_METASTABLE,
    "m_to_r": E_RESONANT - E_METASTABLE, "m_to_p": E_4P - E_METASTABLE,
    "p_ionization": E_IONIZATION - E_4P, "p_to_r": E_RESONANT - E_4P, "p_to_m": E_METASTABLE - E_4P,
    "p_to_ground": -E_4P, "r_to_ground": -E_RESONANT, "r_to_m": E_METASTABLE - E_RESONANT,
    "r_to_p": E_4P - E_RESONANT,
}
_SOURCE_LEVEL = {name: name[0] for name in ELECTRON_ENERGY_CHANGE}  # "m_...", "p_...", "r_..."


def wall_loss_rate(gap_m: float, radius_m: float, gas_density_m3: float, gas_temperature_k: float,
                   mass_kg: float = ARGON_MASS_KG, gamma: float = WALL_DEEXCITATION_PROBABILITY,
                   diffusion_scale: float = 1.0) -> float:
    """Rate (1/s) at which excited atoms are lost to the walls, by Chantry's formula.

    k = [Lambda0^2 / D + 2 V (2 - gamma) / (A v gamma)]^-1, with Lambda0^-2 = (pi/l)^2 + (2.405/R)^2.
    The first term is the time to diffuse to a wall, the second the time to be absorbed there
    (Chantry, J. Appl. Phys. 62, 1141, 1987, as written in Kemaneci et al. 2016, Eq. 21). The whole
    gap is used: neutral atoms cross the sheaths freely.
    """
    pressure_pa = gas_density_m3 * codata.k * gas_temperature_k
    diffusion = (diffusion_scale * D0_M2_S * (D0_PRESSURE_PA / pressure_pa)
                 * (gas_temperature_k / D0_TEMPERATURE_K) ** D_TEMPERATURE_EXPONENT)
    inverse_lambda_sq = (np.pi / gap_m) ** 2 + (2.404825557695773 / radius_m) ** 2
    volume = np.pi * radius_m**2 * gap_m
    area = 2 * np.pi * radius_m**2 + 2 * np.pi * radius_m * gap_m
    thermal_speed = np.sqrt(8 * codata.k * gas_temperature_k / (np.pi * mass_kg))
    return float(1.0 / (1.0 / (inverse_lambda_sq * diffusion)
                        + 2 * volume * (2 - gamma) / (area * thermal_speed * gamma)))


@dataclass(frozen=True)
class ExcitedDensities:
    metastable_m3: float
    resonant_m3: float
    p4_m3: float


def balances(te: float, ne: float, ng: float, d: ExcitedDensities, table: RateTable,
             k_wall: float, extra_metastable_loss: float = 0.0) -> dict[str, tuple[float, float]]:
    """(gain, loss) in m^-3 s^-1 for each level. Steady state means gain = loss for all three.

    ng is the argon density. `extra_metastable_loss` (1/s) is quenching by N2 and O2 in a mixture (3e).
    """
    k = electron_rates(te)
    nm, nr, npp = d.metastable_m3, d.resonant_m3, d.p4_m3
    gm = table.lumped_excitation("to_metastable", te)
    gr = table.lumped_excitation("to_resonant", te)
    gp = table.lumped_excitation("to_4p", te)
    metastable = (
        ne * ng * gm + ne * nr * k["r_to_m"] + ne * npp * k["p_to_m"] + npp * A_4P_TO_METASTABLE,
        nm * (ne * (k["m_to_ground"] + k["m_ionization"] + k["m_to_r"] + k["m_to_p"])
              + ng * K_GROUND_QUENCH_M + k_wall + extra_metastable_loss)
        + 2 * K_POOLING_MM * nm**2 + K_POOLING_MR * nm * nr,
    )
    resonant = (
        ne * ng * gr + ne * nm * k["m_to_r"] + ne * npp * k["p_to_r"] + npp * A_4P_TO_RESONANT,
        nr * (ne * (k["r_to_ground"] + k["r_to_m"] + k["r_to_p"]) + A_RESONANT_TRAPPED + k_wall)
        + K_POOLING_MR * nm * nr,
    )
    p4 = (
        ne * ng * gp + ne * nm * k["m_to_p"] + ne * nr * k["r_to_p"],
        npp * (ne * (k["p_ionization"] + k["p_to_r"] + k["p_to_m"] + k["p_to_ground"])
               + A_4P_TO_GROUND + A_4P_TO_METASTABLE + A_4P_TO_RESONANT) + 2 * K_POOLING_PP * npp**2,
    )
    return {"metastable": metastable, "resonant": resonant, "p4": p4}


def solve_densities(te: float, ne: float, ng: float, table: RateTable, k_wall: float,
                    start: ExcitedDensities | None = None, extra_metastable_loss: float = 0.0) -> ExcitedDensities:
    """Steady-state excited densities for given T_e and n_e.

    The balances are linear except for pooling (two excited atoms meeting). Each step freezes the
    pooling terms at the previous densities, solves the linear 3 x 3 system, and repeats. Pooling
    is a small loss, so this converges in a few steps; the global solver then polishes the answer.
    """
    d = start or ExcitedDensities(0.0, 0.0, 0.0)
    k = electron_rates(te)
    gm = table.lumped_excitation("to_metastable", te)
    gr = table.lumped_excitation("to_resonant", te)
    gp = table.lumped_excitation("to_4p", te)
    for _ in range(200):
        out_m = (ne * (k["m_to_ground"] + k["m_ionization"] + k["m_to_r"] + k["m_to_p"]) + ng * K_GROUND_QUENCH_M
                 + k_wall + extra_metastable_loss + 2 * K_POOLING_MM * d.metastable_m3 + K_POOLING_MR * d.resonant_m3)
        out_r = (ne * (k["r_to_ground"] + k["r_to_m"] + k["r_to_p"]) + A_RESONANT_TRAPPED + k_wall
                 + K_POOLING_MR * d.metastable_m3)
        out_p = (ne * (k["p_ionization"] + k["p_to_r"] + k["p_to_m"] + k["p_to_ground"]) + A_4P_TO_GROUND
                 + A_4P_TO_METASTABLE + A_4P_TO_RESONANT + 2 * K_POOLING_PP * d.p4_m3)
        matrix = np.array([
            [out_m, -ne * k["r_to_m"], -(ne * k["p_to_m"] + A_4P_TO_METASTABLE)],
            [-ne * k["m_to_r"], out_r, -(ne * k["p_to_r"] + A_4P_TO_RESONANT)],
            [-ne * k["m_to_p"], -ne * k["r_to_p"], out_p],
        ])
        source = ne * ng * np.array([gm, gr, gp])
        nm, nr, npp = np.linalg.solve(matrix, source)
        new = ExcitedDensities(float(nm), float(nr), float(npp))
        if np.allclose([new.metastable_m3, new.resonant_m3, new.p4_m3],
                       [d.metastable_m3, d.resonant_m3, d.p4_m3], rtol=1e-13, atol=0):
            return new
        d = new
    return d


def ionization_rate(te: float, ne: float, ng: float, d: ExcitedDensities, table: RateTable) -> dict[str, float]:
    """Ions created per m^3 per second, by route."""
    k = electron_rates(te)
    return {
        "from_ground": ne * ng * table.ionization(te),
        "from_metastable": ne * d.metastable_m3 * k["m_ionization"],
        "from_4p": ne * d.p4_m3 * k["p_ionization"],
        "pooling": (K_POOLING_MM * d.metastable_m3**2 + K_POOLING_PP * d.p4_m3**2
                    + K_POOLING_MR * d.metastable_m3 * d.resonant_m3),
    }


def excited_electron_power(te: float, ne: float, d: ExcitedDensities) -> dict[str, float]:
    """Electron energy exchanged with excited atoms, in eV m^-3 s^-1, split by meaning.

    'two_step_ionization' and 'excitation_between_levels' are losses for the electrons;
    'superelastic_return' is negative: energy an excited atom gives back to an electron.
    """
    k = electron_rates(te)
    density = {"m": d.metastable_m3, "r": d.resonant_m3, "p": d.p4_m3}
    out = {"two_step_ionization": 0.0, "excitation_between_levels": 0.0, "superelastic_return": 0.0}
    for name, energy in ELECTRON_ENERGY_CHANGE.items():
        power = ne * density[_SOURCE_LEVEL[name]] * k[name] * energy
        if name.endswith("ionization"):
            out["two_step_ionization"] += power
        elif energy > 0:
            out["excitation_between_levels"] += power
        else:
            out["superelastic_return"] += power
    return out
