"""Electron energy distribution functions (EEDF): Phase 2a.

WHY the EEDF matters: every rate in the model is an average of a cross-section over the electrons'
energies. Ionization of argon needs 15.76 eV, far above a typical mean energy of 3-4 eV, so only
the high-energy tail ionizes. Two distributions with the same mean energy but different tails give
very different ionization rates. The supervisor chose Druyvesteyn for the low-pressure plasma
(FR2.7), and Maxwellian is kept for comparison and for Stage 2.

One family covers both. It is the "generalized" EEDF used to study exactly this question in an
argon global model by Gudmundsson, Plasma Sources Sci. Technol. 10, 76 (2001):

    f(e) = A * sqrt(e) * exp(-(e / e0)**x)        e = electron energy in eV

    x = 1  Maxwellian. Collisions between electrons have time to share energy out evenly.
    x = 2  Druyvesteyn. Elastic collisions with atoms dominate, which depletes the high-energy tail.

f(e) de is the fraction of electrons with energy between e and e + de, so the integral of f is 1.

WHY all shapes share one "T_e": the electron temperature is defined from the mean energy,
<e> = (3/2) T_e, for every shape. This is the "effective temperature" a Langmuir probe reports from
the EEDF, so model and measurement mean the same thing by T_e. For x = 1 it is the usual Maxwellian
temperature.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import gamma

MAXWELLIAN_SHAPE = 1.0
DRUYVESTEYN_SHAPE = 2.0
SHAPES = {"Maxwellian": MAXWELLIAN_SHAPE, "Druyvesteyn": DRUYVESTEYN_SHAPE}


@dataclass(frozen=True)
class EEDF:
    """An electron energy distribution with mean energy (3/2) T_e and tail shape x."""

    te_ev: float
    shape: float = DRUYVESTEYN_SHAPE

    def __post_init__(self) -> None:
        if not (self.te_ev > 0 and self.shape > 0):
            raise ValueError(f"T_e and shape must be positive, got {self.te_ev} and {self.shape}")

    @property
    def energy_scale_ev(self) -> float:
        """e0, chosen so that the mean energy is exactly (3/2) T_e.

        Using integral(e**a * exp(-(e/e0)**x)) = e0**(a+1) * Gamma((a+1)/x) / x gives
        <e> = e0 * Gamma(5/(2x)) / Gamma(3/(2x)). Setting this to 1.5 T_e and solving for e0:
        """
        x = self.shape
        return 1.5 * self.te_ev * gamma(1.5 / x) / gamma(2.5 / x)

    def __call__(self, energy_ev: np.ndarray) -> np.ndarray:
        """f(e) in 1/eV. The normalization A makes the integral exactly 1 (same Gamma identity)."""
        x, e0 = self.shape, self.energy_scale_ev
        energy = np.asarray(energy_ev, dtype=float)
        norm = x / (e0**1.5 * gamma(1.5 / x))
        return norm * np.sqrt(np.clip(energy, 0.0, None)) * np.exp(-((np.clip(energy, 0.0, None) / e0) ** x))


def from_name(name: str, te_ev: float) -> EEDF:
    """Build an EEDF from its screen name: 'Druyvesteyn' or 'Maxwellian' (envelope.toml)."""
    if name not in SHAPES:
        raise ValueError(f"Unknown EEDF {name!r}; choose one of {sorted(SHAPES)}")
    return EEDF(te_ev, SHAPES[name])
