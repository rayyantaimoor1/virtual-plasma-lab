"""Electron energy distribution from the second derivative of the probe current (Druyvesteyn): FR6.8.

WHY THE SECOND DERIVATIVE: with the probe held V volts below the plasma potential, the electron current
is (iv_model.py)
    I_e(V) = (A e n / 4) sqrt(2e/m) * [ integral_V^inf sqrt(e) F de  -  V integral_V^inf F/sqrt(e) de ].
Differentiating once in V: the two boundary terms cancel and dI_e/dV = -(A e n/4) sqrt(2e/m) integral_V^inf F/sqrt(e) de.
Differentiating again: d^2 I_e/dV^2 = (A e n/4) sqrt(2e/m) F(V)/sqrt(V). So, with e = V in eV,
    n F(e) = (4 / (A e)) * sqrt(m / (2e)) * sqrt(e) * d^2 I_e / dV^2,
which in joules is the textbook Druyvesteyn formula 2 sqrt(2 m E) / (e^2 A) d^2I/dV^2 (Chen 2003, Eq. 31,
gives the proportionality; the constant follows from the integral above).
The EEPF is the EEDF divided by sqrt(e): for a Maxwellian its logarithm is a straight line.

SMOOTHING (documented, FR6.8): the second derivative comes from a Savitzky-Golay filter, window
5 points, cubic polynomial, which differentiates a local cubic fit instead of raw differences.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import constants as codata
from scipy.signal import savgol_filter

E, M_E = codata.e, codata.m_e
SAVGOL_WINDOW, SAVGOL_ORDER = 5, 3


def second_derivative_noise_gain(step_v: float) -> float:
    """How much white noise of standard deviation 1 grows in the smoothed second derivative.

    The filter output is a weighted sum of the window's points, so its noise is sigma times the
    root-sum-square of the weights; the weights are read from scipy itself, not typed in.
    """
    from scipy.signal import savgol_coeffs
    return float(np.sqrt(np.sum(savgol_coeffs(SAVGOL_WINDOW, SAVGOL_ORDER, deriv=2, delta=step_v) ** 2)))


def derivatives(voltage: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """First and second derivative of the current on an evenly spaced sweep (Savitzky-Golay)."""
    step = float(voltage[1] - voltage[0])
    first = savgol_filter(current, SAVGOL_WINDOW, SAVGOL_ORDER, deriv=1, delta=step)
    second = savgol_filter(current, SAVGOL_WINDOW, SAVGOL_ORDER, deriv=2, delta=step)
    return first, second


@dataclass(frozen=True)
class EEPF:
    energy_ev: np.ndarray
    eedf_m3_per_ev: np.ndarray  # n F(e)
    eepf: np.ndarray  # F(e) / sqrt(e), normalised so that integral(sqrt(e) * eepf) = 1
    density_m3: float
    effective_temperature_ev: float  # (2/3) mean energy: the same definition as the model's T_e


def druyvesteyn(voltage: np.ndarray, second_derivative: np.ndarray, plasma_potential_v: float, area_m2: float) -> EEPF:
    """EEDF and EEPF from d2I/dV2 on the retarding side of the curve (probe below V_p)."""
    energy = plasma_potential_v - voltage
    keep = energy > 0
    eps, d2 = energy[keep][::-1], second_derivative[keep][::-1]  # increasing energy
    n_f = np.clip((4 / (area_m2 * E)) * np.sqrt(M_E / (2 * E)) * np.sqrt(eps) * d2, 0.0, None)
    # The point nearest V_p is inside the smoothing window of the kink at V_p, so the EEDF starts at the
    # first point and is taken as linear down to zero energy (F ~ sqrt(e) near 0 for both shapes).
    eps_full = np.concatenate(([0.0], eps))
    n_f_full = np.concatenate(([0.0], n_f))
    density = float(np.trapezoid(n_f_full, eps_full))
    mean = float(np.trapezoid(eps_full * n_f_full, eps_full)) / density if density > 0 else float("nan")
    with np.errstate(divide="ignore", invalid="ignore"):
        eepf = np.where(eps > 0, n_f / np.sqrt(eps) / density, 0.0)
    return EEPF(eps, n_f, eepf, density, 2 * mean / 3)
