"""Gas flow through the chamber: Phase 3a.

WHY: the supervisor gives the argon feed as 100-500 sccm and says flow is used "for generation of
reactive species or tuning of plasma parameter". The pressure is set separately (by the pump and
valve), so flow does not change the gas density. What it does change is how long an atom stays in
the chamber before it is pumped away, the residence time:

    tau = (atoms in the chamber) / (atoms fed per second) = n_g V_chamber / (Q * atoms per sccm)

Any species made in the plasma can be pumped away at the rate 1/tau. For excited argon this is a
small effect: tau is seconds, while diffusion to the walls takes milliseconds. Flow matters most for
mixtures (Phase 3e), where it sets how much N2 and O2 enters and how long their fragments stay.
"""
from __future__ import annotations

import math

from scipy import constants as codata

# sccm = standard cubic centimetre per minute, defined at 0 °C and 1 atm.
STANDARD_TEMPERATURE_K = 273.15
STANDARD_PRESSURE_PA = 101325.0
ATOMS_PER_S_PER_SCCM = STANDARD_PRESSURE_PA * 1e-6 / (codata.k * STANDARD_TEMPERATURE_K) / 60.0


def chamber_volume_m3(diameter_m: float, height_m: float) -> float:
    """The supervisor's 40 x 40 cm chamber, taken as a cylinder."""
    return math.pi * (diameter_m / 2) ** 2 * height_m


def residence_time_s(gas_density_m3: float, chamber_volume: float, flow_sccm: float) -> float:
    """Mean time an atom spends in the chamber. Infinite when there is no flow."""
    if flow_sccm <= 0:
        return math.inf
    return gas_density_m3 * chamber_volume / (flow_sccm * ATOMS_PER_S_PER_SCCM)


def pumping_rate_per_s(gas_density_m3: float, chamber_volume: float, flow_sccm: float) -> float:
    """1 / tau: the rate at which any species is carried out by the flow."""
    return 1.0 / residence_time_s(gas_density_m3, chamber_volume, flow_sccm)
