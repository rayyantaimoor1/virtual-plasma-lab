"""Gas temperature from a heat balance: Phase 3b.

WHY: the supervisor wants the gas temperature as an output (it is also measured by OES in Phase 4),
and the gas temperature sets the gas density at a given pressure, n_g = p / (k T_gas), which feeds
back into every rate. So T_gas is found together with the plasma: heat put into the gas must equal
heat conducted to the walls.

HEAT INTO THE GAS (chosen in BUILD_STEPS.md before this code was written):
- Elastic electron-atom collisions: each transfers 2 (m/M) of the electron's energy to the atom.
  Taken straight from the model's energy budget (losses_w["elastic"]).
- Quenching of metastables by ground-state atoms (Ar* + Ar -> 2 Ar): the 11.6 eV becomes motion.
- NOT counted: energy that ions gain in the sheaths. Ions and the fast neutrals they make by charge
  exchange carry it to the electrodes, heating the electrodes rather than the gas. Energy released in
  pooling ionization goes to the freed electron. So the T_gas computed here is a lower estimate.

HEAT TO THE WALLS: steady conduction, div(kappa grad T) + q = 0, in the cylinder between the
electrodes (radius R, length l), with uniform heating q and walls at T_wall.

Two exact tools make this solvable without a mesh:
1. Kirchhoff transform. With Phi(T) = integral of kappa dT from T_wall, the equation becomes
   laplacian(Phi) = -q, which is linear even though kappa depends on temperature.
2. Eigenfunction series for a uniform source in a finite cylinder with Phi = 0 on all walls:
       mean(Phi) = q * sum over odd m, n >= 1 of  [8 / (m pi)^2] [4 / a_n^2] / [(m pi / l)^2 + (a_n / R)^2]
   where a_n are the zeros of J0. For a very wide cylinder this gives the exact slab result
   q l^2 / (12 kappa), which a test checks.
The mean temperature is then the T whose Phi equals mean(Phi). (Averaging Phi instead of T is a small
approximation because kappa changes slowly; for the few-kelvin rises here it is negligible.)
Thermal conductivity is the NIST table (data/reference/constants/argon_thermal_conductivity.csv).
The temperature jump at the walls is neglected: the gas mean free path is far below the gap.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.optimize import brentq
from scipy.special import jn_zeros

from plasma_twin.reference.loaders import load_thermal_conductivity

_MODES = 400


@lru_cache(maxsize=64)
def conduction_factor_m2(radius_m: float, length_m: float, modes: int = _MODES) -> float:
    """mean(Phi) / q for a uniform source in the cylinder, in m^2 (the series above)."""
    m = np.arange(1, 2 * modes, 2)[:, None]  # odd axial modes
    a = jn_zeros(0, modes)[None, :]
    terms = (8 / (m * np.pi) ** 2) * (4 / a**2) / ((m * np.pi / length_m) ** 2 + (a / radius_m) ** 2)
    return float(terms.sum())


@lru_cache(maxsize=1)
def _kirchhoff_table() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Temperatures, conductivities and Phi at each table point (W/m), with kappa linear between points.

    Phi must be integrated from the interpolated kappa, not interpolated itself: between points 50 K
    apart kappa rises by about 13 %, so a straight line in Phi would misplace small temperature rises
    by several per cent (a test caught exactly this).
    """
    temperature, kappa = load_thermal_conductivity()
    phi = np.concatenate(([0.0], np.cumsum(np.diff(temperature) * (kappa[1:] + kappa[:-1]) / 2)))
    return temperature, kappa, phi


def kirchhoff_potential(temperature_k: float) -> float:
    """Phi(T) = integral of kappa dT from 300 K, exact for kappa linear between the table points."""
    temperature, kappa, phi = _kirchhoff_table()
    if not temperature[0] <= temperature_k <= temperature[-1]:
        raise ValueError(f"T = {temperature_k} K is outside the conductivity table")
    i = min(int(np.searchsorted(temperature, temperature_k, side="right")) - 1, len(temperature) - 2)
    dt = temperature_k - temperature[i]
    slope = (kappa[i + 1] - kappa[i]) / (temperature[i + 1] - temperature[i])
    return float(phi[i] + kappa[i] * dt + slope * dt**2 / 2)


def mean_gas_temperature(heating_w: float, radius_m: float, length_m: float, wall_temperature_k: float) -> float:
    """Volume-mean gas temperature for a given heating power (W) spread evenly over the cylinder."""
    q = heating_w / (np.pi * radius_m**2 * length_m)
    target = kirchhoff_potential(wall_temperature_k) + q * conduction_factor_m2(radius_m, length_m)
    temperature, _, phi = _kirchhoff_table()
    if target > phi[-1]:
        raise ValueError("the gas would be hotter than the conductivity table reaches (1000 K)")
    if target <= kirchhoff_potential(wall_temperature_k):
        return wall_temperature_k
    return float(brentq(lambda t: kirchhoff_potential(t) - target, wall_temperature_k, temperature[-1],
                        xtol=1e-12, rtol=4 * np.finfo(float).eps))
