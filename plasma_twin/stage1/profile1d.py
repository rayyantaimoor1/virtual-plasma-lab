"""Electron density profile between the electrodes: Phase 3c.

WHY: the supervisor said the 0D model alone is not enough and some quantities need spatial
resolution; the agreed choice is an axial n_e profile for Stage 1 (SUPERVISOR_QUESTIONS.md, Q16).

THE PHYSICS. In the bulk, ions and electrons diffuse together (ambipolar diffusion) and are made by
ionization at a rate proportional to the local density. In steady state

    D_a d^2n/dx^2 + nu_iz n = 0,

whose symmetric solution is n(x) = n_0 cos(k x), with x measured from the middle of the gap. The 0D
model already fixes both ends of this curve: the centre density n_0 and the sheath-edge density
n_s = h_l n_0 at x = +/- d/2, where d is the bulk width (gap minus the two sheaths). So
k = (2/d) arccos(h_l). No new parameter is introduced, and the profile agrees with the 0D model at
the centre and at both sheath edges by construction.

Inside the sheaths, electrons are pushed out for most of each RF cycle, so the profile is given for
the bulk only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plasma_twin.stage1.global_model import Stage1Result


@dataclass(frozen=True)
class AxialProfile:
    position_m: np.ndarray  # from the middle of the gap; the bulk spans -half_width to +half_width
    ne_m3: np.ndarray
    half_width_m: float  # d / 2
    sheath_width_m: float
    wavenumber_per_m: float  # k

    @property
    def bulk_average_m3(self) -> float:
        """Exact average of n_0 cos(kx) over the bulk: n_0 sin(k d/2) / (k d/2)."""
        kd2 = self.wavenumber_per_m * self.half_width_m
        return float(self.ne_m3.max() * np.sin(kd2) / kd2)


def axial_profile(result: Stage1Result, points: int = 201) -> AxialProfile:
    """n_e(x) across the bulk for a solved operating point (an odd number of points puts one at x = 0)."""
    half = (result.inputs.electrode_gap_m - 2 * result.sheath_width_m) / 2
    k = float(np.arccos(result.h_axial) / half)
    x = np.linspace(-half, half, points)
    return AxialProfile(x, result.ne_center_m3 * np.cos(k * x), half, result.sheath_width_m, k)
