"""Transfer of the bubble products into the water, and the water's state: Phase 7 (FR9.2, FR9.5).

RULES (BUILD_STEPS.md, Phase 7, fixed before this code); every constant is read from
data/reference/constants/stage2_constants.csv, which names its source:
- H2O2 is very soluble (JPL 19-5 Henry constant ~ 9e4 M/atm), so all of it dissolves.
- O3 dissolves through a two-film transfer: dC/dt = k_La (H p_O3 - C) - k_d C.
  * H: JPL 19-5 Table 5-4. p_O3: the outlet-gas partial pressure, production / total gas flow.
  * k_d = k(O3 + OH-) [OH-] with k = 70 M^-1 s^-1 (Staehelin & Hoigne 1982), the start of ozone's
    self-decomposition. Its chain (2-3 O3 per start) and any organic ozone demand are NOT included,
    so k_d is a lower limit and the dissolved ozone an upper limit, for low-organic water.
  * k_La: Gao et al. (2005), as quoted by Ratnawati et al. (2018): 2.95e-3 s^-1 at 100 mL/min and
    7.47e-3 s^-1 at 600 mL/min, interpolated linearly in the gas flow (sccm taken as mL/min).
    Gao used a different contactor from ours; that is stated on the screen.
- OH in the water: steady state between its arrival from the bubbles and OH + OH, OH + H2O2
  (Buxton et al. 1988).
- Temperature rise = deposited energy / (water mass x specific heat). All the electrical energy ends
  as heat in the water. Water density and heat capacity from NIST.
- pH and conductivity: no ions form in this chemistry set (O2 + H2O without N2 makes no nitric acid;
  H2O2 is a very weak acid; ozone decay makes no net acid), so both stay as they were. Said on screen.
- ORP: the Nernst potential of O3 + 2H+ + 2e- -> O2 + H2O (E0 = 2.076 V, CRC Handbook), with the O3
  partial pressure in equilibrium with the dissolved ozone. A thermodynamic estimate: real ORP
  electrodes read lower.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import constants as codata

from plasma_twin.reference.loaders import load_stage2_constants
from plasma_twin.stage1.gas_flow import ATOMS_PER_S_PER_SCCM
from plasma_twin.stage2.bubble_model import O3_MOLAR_MASS_G, BubbleResult

R, F, N_A = codata.R, codata.physical_constants["Faraday constant"][0], codata.N_A


@dataclass(frozen=True)
class WaterInputs:
    volume_ml: float
    ph: float
    temperature_c: float
    conductivity_us_cm: float
    cod_mg_l: float
    treatment_time_min: float


@dataclass(frozen=True)
class LiquidResult:
    time_s: np.ndarray
    ozone_mg_l: np.ndarray
    h2o2_mmol_l: np.ndarray
    oh_mol_l: np.ndarray
    ozone_ct_mg_s_l: np.ndarray  # running integral of the dissolved ozone (the Hom model's dose)
    kla_per_s: float
    henry_m_per_atm: float
    ozone_saturation_mg_l: float  # H p_O3: the most ozone the gas could dissolve
    decay_per_s: float
    temperature_before_c: float
    temperature_after_c: float
    ph_before: float
    ph_after: float
    conductivity_before_us_cm: float
    conductivity_after_us_cm: float
    orp_after_v: float | None
    notes: tuple[str, ...] = field(default_factory=tuple)


def transfer_coefficient(flow_sccm: float) -> float:
    """k_La (1/s) interpolated linearly in gas flow between Gao's two measurements."""
    c = load_stage2_constants()
    return float(np.interp(flow_sccm, [100.0, 600.0], [c["kla_gao_100mlmin"], c["kla_gao_600mlmin"]]))


def henry_ozone(temperature_k: float) -> float:
    c = load_stage2_constants()
    return float(np.exp(c["henry_o3_A"] + c["henry_o3_B"] / temperature_k))


def solve_liquid(bubble: BubbleResult, water: WaterInputs, points: int = 241) -> LiquidResult:
    """The water over the treatment time: O3, H2O2 and OH concentrations, temperature, pH, ORP."""
    c = load_stage2_constants()
    notes: list[str] = []
    t_k = water.temperature_c + 273.15
    volume_l = water.volume_ml / 1000.0
    time = np.linspace(0.0, water.treatment_time_min * 60.0, points)

    # ozone: two-film transfer with first-order decay, solved exactly
    gas_molecules_per_s = bubble.inputs.o2_flow_sccm * ATOMS_PER_S_PER_SCCM / (1.0 - bubble.water_fraction)
    p_o3_atm = bubble.production_mol_s["O3"] * N_A / gas_molecules_per_s
    henry = henry_ozone(t_k)
    saturation = henry * p_o3_atm  # mol/L
    kla = transfer_coefficient(bubble.inputs.o2_flow_sccm)
    decay = c["o3_oh_minus"] * 10 ** (water.ph - 14.0)
    rate = kla + decay
    steady = kla * saturation / rate
    ozone = steady * (1 - np.exp(-rate * time))
    ct = steady * (time - (1 - np.exp(-rate * time)) / rate)
    if not 100.0 <= bubble.inputs.o2_flow_sccm <= 600.0:
        notes.append("the O2 flow is outside Gao's 100-600 mL/min, so k_La is extrapolated")

    # H2O2: everything the bubbles carry dissolves
    h2o2 = bubble.production_mol_s["H2O2"] * time / volume_l

    # OH: steady state of arrival against OH + OH and OH + H2O2
    arrival = bubble.production_mol_s["OH"] / volume_l
    two_k, k_h2o2 = c["buxton_oh_oh_2k"], c["buxton_oh_h2o2"]
    b = k_h2o2 * h2o2
    oh = (-b + np.sqrt(b * b + 4 * two_k * arrival)) / (2 * two_k)

    # temperature: all the electrical energy ends as heat in the water
    mass_kg = c["water_density_298"] * volume_l / 1000.0
    specific_heat = c["water_cp_molar"] / (c["water_molar_mass"] / 1000.0)  # J/(kg K)
    rise = bubble.inputs.pulse.power_w * time[-1] / (mass_kg * specific_heat)

    orp = None
    if ozone[-1] > 0:
        p_o2_atm = 1.0 - bubble.water_fraction
        orp = c["e0_o3_o2"] + R * t_k / (2 * F) * np.log(ozone[-1] / henry * 10 ** (-2 * water.ph) / p_o2_atm)
    if water.cod_mg_l > 0:
        notes.append("COD is recorded but its ozone demand is not modelled (no published first-order demand constant "
                     "for municipal waste water was found), so the ozone is an upper limit for this water")
    notes.append("pH and conductivity do not change: O2 and water vapour without N2 form no acid or salt in this model")
    return LiquidResult(time, ozone * O3_MOLAR_MASS_G * 1000.0, h2o2 * 1000.0, oh, ct * O3_MOLAR_MASS_G * 1000.0, kla, henry,
                        saturation * O3_MOLAR_MASS_G * 1000.0, decay, water.temperature_c, water.temperature_c + rise,
                        water.ph, water.ph, water.conductivity_us_cm, water.conductivity_us_cm, orp, tuple(notes))
