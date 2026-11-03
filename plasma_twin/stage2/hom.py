"""E. coli survival by the Hom model: Phase 7 (FR9.1, FR9.3, LI-6).

RULES (BUILD_STEPS.md, Phase 7, decided with the student on 4 Nov 2026): the kinetics are those of
Hunt & Marinas (1997): inactivation first-order in dissolved ozone and in live cells, rate constant
130 L mg^-1 s^-1 at 20 C, activation energy 37,100 J mol^-1. In the Hom form log10(N/N0) = -k C^n t^m
that is n = 1, m = 1. Because C changes with time the dose is its integral:
    log10(N/N0) = -(k_T / ln 10) * integral(C dt)
k_T is k at the water temperature (Arrhenius from 20 C). Hunt & Marinas covered O3 = 6-41 ug/L and
t = 1.8-33 s; outside that the result is flagged as extrapolated. S. aureus and spores have no published
parameters here and are unavailable (LI-6).

Two more rules:
- the survivors cannot fall below one cell in the whole water volume, so the log reduction is capped
  at log10(N0 x volume in mL);
- D-value = treatment time / log reduction; energy yield = log reduction / (energy / volume), in
  log per kJ/L (SRS FR9.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import constants as codata

from plasma_twin.reference.loaders import load_stage2_constants

ORGANISMS_WITH_PARAMETERS = ("E. coli",)


class OrganismUnavailable(ValueError):
    """No published Hom parameters for this organism (LI-6)."""


@dataclass(frozen=True)
class SurvivalResult:
    time_s: np.ndarray
    log_survival: np.ndarray  # log10(N/N0), <= 0
    log_reduction: float  # at the end of the treatment, >= 0
    capped: bool  # reached fewer than one cell in the whole volume
    d_value_min: float | None  # minutes per log; None when nothing was inactivated
    energy_yield_log_per_kj_l: float
    rate_constant_l_mg_s: float
    flags: tuple[str, ...] = field(default_factory=tuple)


def rate_constant(temperature_c: float) -> float:
    """Hunt & Marinas k at the water temperature (L mg^-1 s^-1), from its 20 C value and E_a."""
    c = load_stage2_constants()
    t = temperature_c + 273.15
    return c["hunt_k_20c"] * float(np.exp(-c["hunt_ea"] / codata.R * (1 / t - 1 / 293.15)))


def survival(time_s: np.ndarray, ozone_mg_l: np.ndarray, ozone_ct_mg_s_l: np.ndarray, organism: str,
             initial_cfu_ml: float, volume_ml: float, temperature_c: float, power_w: float) -> SurvivalResult:
    """log10(N/N0) over the treatment, from the dissolved-ozone dose."""
    if organism not in ORGANISMS_WITH_PARAMETERS:
        raise OrganismUnavailable(f"{organism}: no published Hom parameters are used in this model (LI-6)")
    c = load_stage2_constants()
    k = rate_constant(temperature_c)
    cap = float(np.log10(initial_cfu_ml * volume_ml))
    log_survival = np.maximum(-k * ozone_ct_mg_s_l / np.log(10.0), -cap)
    reduction = float(-log_survival[-1])
    capped = reduction >= cap - 1e-12
    flags = []
    peak_ug_l = float(np.max(ozone_mg_l)) * 1000.0
    if not c["hunt_o3_min"] <= peak_ug_l <= c["hunt_o3_max"]:
        flags.append(f"dissolved ozone reaches {peak_ug_l:.3g} ug/L, outside the {c['hunt_o3_min']:g}-{c['hunt_o3_max']:g} ug/L "
                     "Hunt & Marinas measured: extrapolated")
    if time_s[-1] > c["hunt_t_max"]:
        flags.append(f"treatment of {time_s[-1]:.0f} s is longer than the {c['hunt_t_max']:g} s Hunt & Marinas measured: extrapolated")
    if not c["hunt_temp_min_c"] <= temperature_c <= c["hunt_temp_max_c"]:
        flags.append(f"water temperature outside the {c['hunt_temp_min_c']:g}-{c['hunt_temp_max_c']:g} C Hunt & Marinas "
                     "measured: extrapolated")
    if capped:
        flags.append("fewer than one live cell is left in the whole volume: the log reduction is capped there")
    minutes = time_s[-1] / 60.0
    energy_kj_per_l = power_w * time_s[-1] / 1000.0 / (volume_ml / 1000.0)
    return SurvivalResult(time_s, log_survival, reduction, capped, minutes / reduction if reduction > 0 else None,
                          reduction / energy_kj_per_l, k, tuple(flags))
