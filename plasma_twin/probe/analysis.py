"""Analysis of a Langmuir probe I-V curve: Phase 5 (FR6.6, FR6.7, E11, E12).

The steps follow BUILD_STEPS.md (Phase 5) and the way the laboratory analyses its curves (V_p from the
zero crossing of the second derivative, EEDF by the Druyvesteyn method). Each step is named, so that if
one fails the report says exactly where (E11). It works the same on a synthetic curve and on a
measured one (FR6.9): it only needs voltages, currents and the probe dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import constants as codata

from plasma_twin.config.loader import load_envelope
from plasma_twin.probe.eepf import EEPF, derivatives, druyvesteyn, second_derivative_noise_gain
from plasma_twin.stage1.rates import ARGON_MASS_KG

E, EPS0, M_E = codata.e, codata.epsilon_0, codata.m_e
# The EEPF is trusted only if the noise it picks up adds at most this fraction to n_e and to the mean energy.
EEPF_MAX_NOISE_BIAS = 0.05
STEPS = ("floating potential", "ion current fit", "plasma potential", "EEPF", "slope temperature", "Debye length")


class ProbeAnalysisError(RuntimeError):
    """The analysis could not finish; `step` names where it stopped (E11)."""

    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"probe analysis failed at '{step}': {detail}")
        self.step = step


@dataclass(frozen=True)
class ProbeResult:
    floating_potential_v: float
    plasma_potential_v: float
    electron_density_m3: float  # from the EEPF integral
    saturation_density_m3: float  # textbook: I_e(V_p) = A e n sqrt(e T_slope / (2 pi m)), robust to noise
    noise_fraction: float  # estimated current noise / I_e(V_p)
    eepf_reliable: bool  # the noise picked up by the EEPF changes n_e and the mean energy by <= 5 %
    effective_temperature_ev: float  # (2/3) mean energy from the EEPF: same definition as the model T_e
    slope_temperature_ev: float  # inverse slope of ln I_e between V_f and V_p (what many labs report)
    debye_length_m: float
    radius_over_debye: float
    oml_valid: bool  # r_p / lambda_D <= limit (E12)
    eepf: EEPF
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # FR6.6: n_i from the OML ion current (Chen Eq. 22) = n_e by quasi-neutrality. NaN only if the fitted ion
    # current is not negative. Approximate with negative ions (LI-4).
    ion_density_m3: float = float("nan")


def point_noise(residual: np.ndarray) -> float:
    """Point-to-point noise of a residual, blind to any smooth misfit.

    Second differences r[i-1] - 2 r[i] + r[i+1] cancel any smooth trend, and for white noise of standard
    deviation s they have variance 6 s^2, so s = std(second differences) / sqrt(6).
    """
    second = residual[2:] - 2 * residual[1:-1] + residual[:-2]
    return float(np.std(second) / np.sqrt(6.0))


def analyse(voltage: np.ndarray, current: np.ndarray, tip_radius_mm: float, exposed_length_mm: float,
            ion_mass_kg: float = ARGON_MASS_KG) -> ProbeResult:
    """Run every step on one I-V curve (electron current positive). ion_mass_kg is used only for the OML n_i."""
    area = 2 * np.pi * tip_radius_mm * 1e-3 * exposed_length_mm * 1e-3
    warnings: list[str] = []

    step = STEPS[0]
    # The LAST negative-to-positive crossing: noise can make the small ion current cross zero far below
    # V_f, but above the true V_f the electron current only grows (robustness change, 3 Nov 2026).
    negative = np.where(current < 0)[0]
    if len(negative) == 0 or negative[-1] == len(current) - 1:
        raise ProbeAnalysisError(step, "the current never changes from negative to positive")
    i = int(negative[-1])
    v_f = float(voltage[i] - current[i] * (voltage[i + 1] - voltage[i]) / (current[i + 1] - current[i]))

    step = STEPS[1]
    below = np.where(voltage < v_f)[0]
    fit_points = below[: max(5, int(0.4 * len(below)))]
    if len(below) < 5:
        raise ProbeAnalysisError(step, "fewer than 5 points below the floating potential")
    # OML: I_i^2 is a straight line in V. Fit it, then extend it to every voltage below where it reaches zero.
    # FALLBACK (added 3 Nov 2026, recorded in BUILD_STEPS.md): when noise is as large as the ion current,
    # the I^2 fit can come out rising. Then a straight line in I is tried, and if that also rises, the ion
    # current is taken as constant (the mean of the fit points). Each fallback adds a warning.
    slope, intercept = np.polyfit(voltage[fit_points], current[fit_points] ** 2, 1)
    if slope < 0 and np.all(current[fit_points] < 0):
        ion = -np.sqrt(np.clip(slope * voltage + intercept, 0.0, None))
    else:
        line_slope, line_intercept = np.polyfit(voltage[fit_points], current[fit_points], 1)
        if line_slope > 0:
            ion = np.minimum(line_slope * voltage + line_intercept, 0.0)
            warnings.append("ion current fitted as a straight line: the OML I^2 fit was spoiled by noise")
        else:
            ion = np.full_like(voltage, min(float(np.mean(current[fit_points])), 0.0))
            warnings.append("ion current taken as constant: noise hides its voltage dependence")
    electron = current - ion
    noise_sigma = point_noise(current[fit_points] - ion[fit_points])

    step = STEPS[2]

    def find_plasma_potential(electron_current: np.ndarray) -> tuple[float, np.ndarray]:
        first, second = derivatives(voltage, electron_current)
        sign_change = np.where((second[:-1] > 0) & (second[1:] <= 0) & (voltage[:-1] > v_f))[0]
        if len(sign_change) == 0:
            raise ProbeAnalysisError(step, "d2I/dV2 never crosses zero above the floating potential")
        # Of all + to - crossings, take the one nearest the peak of dI/dV (the knee of the curve). The first
        # derivative is far less noisy than the second, so noise cannot pick a false crossing (3 Nov 2026).
        knee = voltage[np.argmax(np.where(voltage > v_f, first, -np.inf))]
        j = int(sign_change[np.argmin(np.abs(voltage[sign_change] - knee))])
        return float(voltage[j] + second[j] * (voltage[j + 1] - voltage[j]) / (second[j] - second[j + 1])), second

    v_p, second = find_plasma_potential(electron)
    # SECOND PASS (added 3 Nov 2026, recorded in BUILD_STEPS.md): OML says the ion current falls to zero
    # exactly at V_p (Chen Eq. 22). A free I^2 fit can reach zero earlier (the few electrons still collected
    # in the ion region tilt it), and the kink where it reaches zero shows up as a false spike in the EEPF.
    # So the I^2 fit is repeated with its zero fixed at the first-pass V_p, and V_p is found again.
    if slope < 0 and np.all(current[fit_points] < 0):
        distance = v_p - voltage[fit_points]
        a = float(np.sum(distance * current[fit_points] ** 2) / np.sum(distance**2))
        ion = -np.sqrt(np.clip(a * (v_p - voltage), 0.0, None))
        electron = current - ion
        noise_sigma = point_noise(current[fit_points] - ion[fit_points])
        v_p, second = find_plasma_potential(electron)

    # n_i from the OML ion current (FR6.6): I_i = -b sqrt(V_p - V) with b = A e n_i (sqrt 2 / pi) sqrt(e / M), so
    # n_i = (pi b / (A e)) sqrt(M / (2 e)). b is fitted to the CURRENT, not to I^2, by linear least squares with
    # the final V_p: squaring would turn noise as large as the ion current into a bias (1 % noise, the default).
    root = np.sqrt(np.clip(v_p - voltage[fit_points], 0.0, None))
    b = -float(np.sum(current[fit_points] * root) / np.sum(root**2))
    ion_density = float(np.pi * b / (area * E) * np.sqrt(ion_mass_kg / (2 * E))) if b > 0 else float("nan")

    step = STEPS[3]
    eepf = druyvesteyn(voltage, second, v_p, area)
    if not eepf.density_m3 > 0:
        raise ProbeAnalysisError(step, "the second derivative gives no positive electron density")

    step = STEPS[4]
    window = (voltage > v_f) & (voltage < v_p) & (electron > 0)
    if window.sum() < 3:
        raise ProbeAnalysisError(step, "fewer than 3 points between V_f and V_p")
    t_slope = float(1.0 / np.polyfit(voltage[window], np.log(electron[window]), 1)[0])

    i_at_vp = float(np.interp(v_p, voltage, electron))
    saturation_density = i_at_vp / (area * E * np.sqrt(E * t_slope / (2 * np.pi * M_E)))
    step_v = float(voltage[1] - voltage[0])
    # Negative EEDF values are clipped to zero, so noise only ever ADDS: on average sigma/sqrt(2 pi) per point
    # of d2I/dV2. Converted by the Druyvesteyn factor and integrated over the energy range used, that gives
    # the expected false density and false energy moment the noise brings in.
    d2_noise = noise_sigma * second_derivative_noise_gain(step_v)
    factor = (4 / (area * E)) * np.sqrt(M_E / (2 * E)) * d2_noise / np.sqrt(2 * np.pi)
    e_max = float(v_p - voltage[0])
    false_density = factor * (2 / 3) * e_max**1.5
    false_moment = factor * (2 / 5) * e_max**2.5
    bias_density = false_density / eepf.density_m3
    bias_energy = false_moment / (eepf.density_m3 * 1.5 * eepf.effective_temperature_ev)
    eepf_reliable = max(bias_density, bias_energy) <= EEPF_MAX_NOISE_BIAS
    if not eepf_reliable:
        warnings.append(f"EEPF unreliable: noise may add {bias_density:.0%} to n_e and {bias_energy:.0%} to the mean "
                        "energy (limit 5 %). Average more sweeps or reduce noise; use the slope T_e and saturation n_e.")

    step = STEPS[5]
    debye = float(np.sqrt(EPS0 * eepf.effective_temperature_ev / (E * eepf.density_m3)))
    ratio = tip_radius_mm * 1e-3 / debye
    limit = load_envelope()["probe"]["limits"]["oml_max_radius_over_debye"]
    oml_valid = ratio <= limit
    if not oml_valid:
        warnings.append(f"r_p / lambda_D = {ratio:.1f} exceeds {limit}: OML theory is outside its range (E12)")
    return ProbeResult(v_f, v_p, eepf.density_m3, float(saturation_density), noise_sigma / i_at_vp, eepf_reliable,
                       eepf.effective_temperature_ev, t_slope, debye, ratio, oml_valid, eepf, tuple(warnings), ion_density)


def analyse_curve(curve) -> ProbeResult:
    """Analyse an IVCurve from iv_model.generate."""
    s = curve.settings
    return analyse(curve.voltage_v, curve.current_a, s.tip_radius_mm, s.exposed_length_mm, mean_ion_mass(curve.plasma))


def mean_ion_mass(plasma) -> float:
    """The single mass that gives the same OML current as the ion mixture: M = (sum n_k / sum n_k M_k^-1/2)^2."""
    total = sum(plasma.ion_densities_m3.values())
    weighted = sum(n / np.sqrt(plasma.ion_masses_kg[k]) for k, n in plasma.ion_densities_m3.items())
    return float((total / weighted) ** 2) if weighted > 0 else ARGON_MASS_KG
