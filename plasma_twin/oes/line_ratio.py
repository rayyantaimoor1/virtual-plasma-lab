"""Electron temperature and density from argon line ratios: Phase 4d (ACC-2).

WHY: the Boltzmann plot gives only an excitation temperature, which in a low-pressure plasma is far
below T_e. The CR model links the line pattern to T_e and n_e directly: T_e decides how hard it is to
reach each 2p level from the ground state, and n_e decides how much the two-step route through the 1s
levels contributes. Running the CR model "backwards", that is finding the T_e and n_e whose predicted
pattern best matches the measured one, gives an OES estimate of T_e that can be compared with the
Langmuir probe and the model (Phase 5).

METHOD (BUILD_STEPS.md, 4d): each intensity is divided by the sum over the lines used, so the fit
does not need an absolutely calibrated spectrometer. Then ln(measured share) - ln(model share) is
minimised by least squares over ln T_e and ln n_e (scipy.optimize.least_squares). Gas density, gas
temperature, EEDF shape and geometry are taken as known.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from plasma_twin.oes.cr_model import solve_cr

TE_BOUNDS_EV = (0.6, 19.0)
NE_BOUNDS_M3 = (1e14, 1e18)


@dataclass(frozen=True)
class LineRatioFit:
    te_ev: float
    ne_m3: float
    rms_log_residual: float  # typical mismatch of ln(intensity share) at the solution
    lines_used: tuple[float, ...]
    success: bool


def _shares(values: np.ndarray) -> np.ndarray:
    return np.log(values / values.sum())


def fit_te_ne(measured: dict[float, float], argon_density_m3: float, shape: float, gas_temperature_k: float,
              gap_m: float, radius_m: float, extra_metastable_loss_per_s: float = 0.0,
              start: tuple[float, float] = (2.0, 1e16)) -> LineRatioFit:
    """Fit T_e and n_e to measured line intensities given by wavelength (nm) -> integrated intensity."""
    wavelengths = tuple(sorted(w for w, v in measured.items() if v > 0))
    if len(wavelengths) < 3:
        raise ValueError("a line-ratio fit needs at least three lines")
    target = _shares(np.array([measured[w] for w in wavelengths]))

    def model_shares(log_te: float, log_ne: float) -> np.ndarray:
        cr = solve_cr(float(np.exp(log_te)), float(np.exp(log_ne)), argon_density_m3, shape, gas_temperature_k,
                      gap_m, radius_m, extra_metastable_loss_per_s)
        return _shares(np.array([cr.line_emission_w_m3[w] for w in wavelengths]))

    found = least_squares(lambda p: model_shares(*p) - target, x0=np.log(start),
                          bounds=(np.log([TE_BOUNDS_EV[0], NE_BOUNDS_M3[0]]), np.log([TE_BOUNDS_EV[1], NE_BOUNDS_M3[1]])),
                          x_scale=[0.3, 1.0], xtol=1e-10, ftol=1e-12, gtol=1e-12)
    rms = float(np.sqrt(np.mean(found.fun**2)))
    return LineRatioFit(float(np.exp(found.x[0])), float(np.exp(found.x[1])), rms, wavelengths, bool(found.success))


def fit_te_fixed_ne(measured: dict[float, float], ne_m3: float, argon_density_m3: float, shape: float,
                    gas_temperature_k: float, gap_m: float, radius_m: float, extra_metastable_loss_per_s: float = 0.0,
                    start_te: float = 2.0) -> LineRatioFit:
    """Fit T_e only, with n_e given (for example by the probe, as the supervisor proposed, Q2)."""
    wavelengths = tuple(sorted(w for w, v in measured.items() if v > 0))
    if len(wavelengths) < 3:
        raise ValueError("a line-ratio fit needs at least three lines")
    target = _shares(np.array([measured[w] for w in wavelengths]))

    def residual(p: np.ndarray) -> np.ndarray:
        cr = solve_cr(float(np.exp(p[0])), ne_m3, argon_density_m3, shape, gas_temperature_k, gap_m, radius_m,
                      extra_metastable_loss_per_s)
        return _shares(np.array([cr.line_emission_w_m3[w] for w in wavelengths])) - target

    found = least_squares(residual, x0=[np.log(start_te)], bounds=([np.log(TE_BOUNDS_EV[0])], [np.log(TE_BOUNDS_EV[1])]),
                          xtol=1e-10, ftol=1e-12, gtol=1e-12)
    return LineRatioFit(float(np.exp(found.x[0])), ne_m3, float(np.sqrt(np.mean(found.fun**2))), wavelengths,
                        bool(found.success))


def fit_spectrum_points(points, result, fixed_ne_m3: float | None = None) -> LineRatioFit:
    """Fit from Boltzmann-style LinePoints measured on a spectrum, using a global-model point for the
    known quantities (gas density and temperature, EEDF, geometry, quenching in mixtures)."""
    from plasma_twin.stage1.eedf import SHAPES
    from plasma_twin.stage1.mixtures import K_QUENCH_N2, K_QUENCH_O2_DISSOCIATING, K_QUENCH_O2_TO_GROUND
    x, m = result.inputs, result.mixture
    quench = (m.get("n2_density_m3", 0.0) * K_QUENCH_N2
              + m.get("o2_density_m3", 0.0) * (K_QUENCH_O2_TO_GROUND + K_QUENCH_O2_DISSOCIATING))
    measured = {p.wavelength_nm: p.intensity for p in points}
    if fixed_ne_m3 is not None:
        return fit_te_fixed_ne(measured, fixed_ne_m3, m.get("argon_density_m3", result.gas_density_m3), SHAPES[x.eedf],
                               x.gas_temperature_k, x.electrode_gap_m, x.electrode_radius_m, quench)
    return fit_te_ne(measured, m.get("argon_density_m3", result.gas_density_m3), SHAPES[x.eedf],
                     x.gas_temperature_k, x.electrode_gap_m, x.electrode_radius_m, quench)
