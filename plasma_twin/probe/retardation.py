"""What a Langmuir probe would report as T_e for a given EEDF (first piece of the Phase 5 probe).

WHY THIS EXISTS. The model's T_e is two-thirds of the mean electron energy. A probe usually reports
the inverse slope of ln(electron current) as its bias rises towards the plasma potential: Saikia et
al. (2018) say their T_e "is derived from the linear part of the logarithmic electron current".
For a Maxwellian both numbers are the same. For any other EEDF they differ, so comparing the
model's mean-energy T_e with a measured slope would compare two different quantities.

THE PHYSICS. Hold the probe V volts below the plasma potential. Only electrons that can climb the
barrier reach it. For isotropic electrons and any convex probe (Druyvesteyn's result), the collected
electron current is

    I_e(V) ∝ integral over e > V of  v(e) f(e) (1 - V/e) de

which is the same flux as in rates.wall_constants. Its shape does not depend on the probe's size or
form, so the probe's dimensions are not needed. For a Maxwellian it gives I_e ∝ exp(-V/T_e) exactly,
so -1/slope of ln I_e is T_e (a test checks this).

THE RULE (fixed in BUILD_STEPS.md before this code was written): fit one straight line by least
squares to ln I_e on an even voltage grid from V = 0 (plasma potential) to V = V_f (the floating
potential of the same EEDF), and report -1/slope. Ion current is taken as perfectly subtracted.
"""
from __future__ import annotations

import numpy as np

from plasma_twin.stage1.eedf import EEDF
from plasma_twin.stage1.rates import wall_constants

# Fine geometric energy grid, independent of the one used for the rates.
_ENERGY = np.geomspace(1e-5, 2000.0, 40000)
_WEIGHTS = np.gradient(_ENERGY)
WINDOWS = {"full": (0.0, 1.0), "near_plasma_potential": (0.0, 0.5), "near_floating_potential": (0.5, 1.0)}


def retarding_current(eedf: EEDF, retarding_volts: np.ndarray) -> np.ndarray:
    """Relative electron current at each retarding voltage (V below the plasma potential, >= 0)."""
    v = np.asarray(retarding_volts, dtype=float)[:, None]
    integrand = np.sqrt(_ENERGY) * eedf(_ENERGY) * np.clip(1.0 - v / _ENERGY, 0.0, None)
    return np.sum(integrand * _WEIGHTS, axis=1)  # the constant factors in v(e) cancel in the slope


def slope_temperature(eedf: EEDF, low_volts: float, high_volts: float, points: int = 201) -> float:
    """-1 / slope of a least-squares line through ln I_e between two retarding voltages."""
    volts = np.linspace(low_volts, high_volts, points)
    slope = np.polyfit(volts, np.log(retarding_current(eedf, volts)), 1)[0]
    return float(-1.0 / slope)


def probe_style_te(te_ev: float, shape: float, window: str = "full") -> float:
    """The T_e a probe would report for this EEDF, by the pre-registered rule (window "full").

    The window runs between the plasma potential and the floating potential of the same EEDF;
    the other two windows (each half) are for showing how much the choice matters.
    """
    start, end = WINDOWS[window]
    floating = wall_constants(shape).floating_ratio * te_ev
    return slope_temperature(EEDF(te_ev, shape), start * floating, end * floating)
