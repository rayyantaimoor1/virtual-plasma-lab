"""Synthetic Langmuir probe I-V curve: Phase 5 (FR6.1-FR6.5).

WHY: the supervisor wants the Stage 1 plasma probed with a virtual Langmuir probe (Stage 3, D1): make
the I-V curve a real probe would record from the model's plasma, then analyse it the way the laboratory
does. If the analysis gives back the model's T_e and n_e, the analysis chain is proven, and the same
code can then be trusted on measured curves (FR6.9).

RULES (BUILD_STEPS.md, Phase 5, fixed before this code):
- The probe sits at the centre: n_e = n_0 and the model's EEDF.
- Plasma potential against the grounded chamber: V_p = T_s/2 + V_f (presheath plus floating sheath
  at the large grounded wall), from the model's own wall constants.
- Below V_p (electrons held back by V = V_p - V_probe):
      I_e = (A e n / 4) sqrt(2e/m) * J(V),   J(V) = integral_V^inf sqrt(e) F(e) (1 - V/e) de
  valid for any convex probe with isotropic electrons (Chen 2003, Sec. V.A).
- Above V_p: OML cylinder law for a Maxwellian at T_s: I_e(V_p) [2 sqrt(eta/pi) + e^eta erfc(sqrt eta)].
- Ions (below V_p): OML limit I_i = A n_i e (sqrt 2 / pi) sqrt(e (V_p - V_probe) / M) (Chen 2003, Eq. 22).
- RF distortion: V_p oscillates as V_p + V~ sin(wt); the current is averaged over 64 phases.
- Noise: Gaussian, a percentage of I_e(V_p), from a seeded generator.
Sign convention: electron current collected by the probe is positive, ion current negative.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import dataclass, field

import numpy as np
from scipy import constants as codata
from scipy.special import erfcx

from plasma_twin.config.loader import load_envelope
from plasma_twin.stage1.eedf import EEDF, SHAPES
from plasma_twin.stage1.rates import ARGON_MASS_KG, wall_constants

if TYPE_CHECKING:  # used in annotations only (MNT-3): nothing extra is imported at run time
    from plasma_twin.stage1.global_model import Stage1Result

E, M_E = codata.e, codata.m_e
_ENERGY = np.geomspace(1e-5, 2000.0, 40000)
RF_PHASES = 64


class ProbeSettingsOutOfRange(ValueError):
    """A probe setting lies outside the envelope (E3)."""


@dataclass(frozen=True)
class ProbeSettings:
    tip_radius_mm: float
    exposed_length_mm: float
    sweep_start_v: float
    sweep_end_v: float
    sweep_step_v: float
    noise_percent: float
    rf_amplitude_v: float
    seed: int = 0

    @classmethod
    def defaults(cls, **overrides: float) -> "ProbeSettings":
        """The envelope's default probe (the COMSATS laboratory tip), with any settings overridden."""
        env = load_envelope()["probe"]
        values = {"tip_radius_mm": env["tip_radius_mm"]["default"], "exposed_length_mm": env["exposed_length_mm"]["default"],
                  "sweep_start_v": env["sweep_start_v"]["default"], "sweep_end_v": env["sweep_end_v"]["default"],
                  "sweep_step_v": env["sweep_step_v"]["default"], "noise_percent": env["noise_percent_of_saturation"]["default"],
                  "rf_amplitude_v": env["rf_amplitude_v"]["default"]}
        values.update(overrides)
        return cls(**values)

    @property
    def area_m2(self) -> float:
        """Side area of the cylindrical tip, 2 pi r L (the end face is ignored)."""
        return 2 * np.pi * self.tip_radius_mm * 1e-3 * self.exposed_length_mm * 1e-3

    def voltages(self) -> np.ndarray:
        """The swept bias voltages, start to end in equal steps."""
        n = int(round((self.sweep_end_v - self.sweep_start_v) / self.sweep_step_v)) + 1
        return self.sweep_start_v + self.sweep_step_v * np.arange(n)

    def validate(self) -> None:
        """Refuse probe settings outside the envelope (FR6.1-FR6.4)."""
        env = load_envelope()["probe"]
        keys = {"tip_radius_mm": self.tip_radius_mm, "exposed_length_mm": self.exposed_length_mm,
                "sweep_start_v": self.sweep_start_v, "sweep_end_v": self.sweep_end_v, "sweep_step_v": self.sweep_step_v,
                "noise_percent_of_saturation": self.noise_percent, "rf_amplitude_v": self.rf_amplitude_v}
        for key, value in keys.items():
            if not env[key]["min"] <= value <= env[key]["max"]:
                raise ProbeSettingsOutOfRange(f"{key} = {value} is outside {env[key]['min']}-{env[key]['max']}")
        if self.sweep_end_v <= self.sweep_start_v:
            raise ProbeSettingsOutOfRange("the sweep must end above where it starts")
        if len(self.voltages()) > env["limits"]["sweep_max_points"]:
            raise ProbeSettingsOutOfRange(f"the sweep has more than {env['limits']['sweep_max_points']} points")


@dataclass(frozen=True)
class ProbePlasma:
    """What the probe sees: electron density, EEDF, ions and the plasma potential against ground."""

    ne_m3: float
    te_ev: float
    shape: float
    ion_densities_m3: dict[str, float]
    ion_masses_kg: dict[str, float]
    plasma_potential_v: float
    negative_ion_density_m3: float = 0.0

    @property
    def screening_te_ev(self) -> float:
        """The effective temperature that screens the probe for this EEDF shape."""
        return wall_constants(self.shape).screening_ratio * self.te_ev


def plasma_from(result: Stage1Result) -> ProbePlasma:
    """The probe's view of a solved global-model point (Stage1Result)."""
    from plasma_twin.stage1.mixtures import ION_MASS_KG
    shape = SHAPES[result.inputs.eedf]
    wall = wall_constants(shape)
    potential = wall.screening_ratio * result.te_ev / 2 + wall.floating_ratio * result.te_ev
    ions = result.mixture.get("ion_densities_m3") or {"Ar+": result.ne_center_m3}
    return ProbePlasma(result.ne_center_m3, result.te_ev, shape, dict(ions), {k: ION_MASS_KG.get(k, ARGON_MASS_KG) for k in ions},
                       potential, result.mixture.get("negative_ion_density_m3", 0.0))


def _tail_integrals(eedf: EEDF) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative integrals from e to infinity of sqrt(e) F and F / sqrt(e), on the energy grid."""
    f = eedf(_ENERGY)
    def tail(values: np.ndarray) -> np.ndarray:
        pieces = np.diff(_ENERGY) * (values[1:] + values[:-1]) / 2
        return np.concatenate((np.cumsum(pieces[::-1])[::-1], [0.0]))
    return tail(np.sqrt(_ENERGY) * f), tail(f / np.sqrt(_ENERGY))


@dataclass(frozen=True)
class IVCurve:
    voltage_v: np.ndarray
    current_a: np.ndarray
    settings: ProbeSettings
    plasma: ProbePlasma
    electron_current_at_vp_a: float
    parts: dict[str, np.ndarray] = field(default_factory=dict)  # noise-free electron and ion currents


def generate(plasma: ProbePlasma, settings: ProbeSettings) -> IVCurve:
    """The I-V curve the probe would record (FR6.5)."""
    settings.validate()
    area = settings.area_m2
    eedf = EEDF(plasma.te_ev, plasma.shape)
    upper, lower = _tail_integrals(eedf)
    i_e0 = area * E * plasma.ne_m3 / 4 * np.sqrt(2 * E / M_E)
    t_s = plasma.screening_te_ev

    def electron(retarding: np.ndarray) -> np.ndarray:
        """Electron current for V = V_p - V_probe (positive = electrons held back)."""
        held = np.clip(retarding, 0.0, None)
        j = np.interp(held, _ENERGY, upper, left=upper[0]) - held * np.interp(held, _ENERGY, lower, left=lower[0])
        current = i_e0 * j
        eta = np.clip(-retarding, 0.0, None) / t_s
        oml = 2 * np.sqrt(eta / np.pi) + erfcx(np.sqrt(eta))  # erfcx(x) = e^(x^2) erfc(x) = e^eta erfc(sqrt eta)
        return np.where(retarding >= 0, current, i_e0 * upper[0] * oml)

    def ions(retarding: np.ndarray) -> np.ndarray:
        held = np.clip(retarding, 0.0, None)
        total = sum(n * np.sqrt(1.0 / plasma.ion_masses_kg[k]) for k, n in plasma.ion_densities_m3.items())
        return -area * E * (np.sqrt(2) / np.pi) * np.sqrt(E * held) * total

    voltages = settings.voltages()
    phases = np.linspace(0, 2 * np.pi, RF_PHASES, endpoint=False) if settings.rf_amplitude_v > 0 else np.array([0.0])
    retarding = plasma.plasma_potential_v + settings.rf_amplitude_v * np.sin(phases)[:, None] - voltages[None, :]
    electron_part = electron(retarding).mean(axis=0)
    ion_part = ions(retarding).mean(axis=0)
    at_vp = float(i_e0 * upper[0])
    current = electron_part + ion_part
    if settings.noise_percent > 0:
        rng = np.random.default_rng(settings.seed)
        current = current + rng.normal(0.0, settings.noise_percent / 100 * at_vp, size=current.shape)
    return IVCurve(voltages, current, settings, plasma, at_vp, {"electron": electron_part, "ion": ion_part})
