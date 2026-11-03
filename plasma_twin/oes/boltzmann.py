"""Boltzmann plot and excitation temperature: Phase 4c (FR5.2, FR5.3, event E9).

WHY: if the upper levels of a set of lines were populated in Boltzmann equilibrium at a temperature
T, then n_u / g_u ∝ exp(-E_u / T). Each line's intensity (power per volume) is I = n_u A h c / lambda,
so ln(I lambda / (g_u A)) = constant - E_u / T: a straight line against E_u whose slope is -1/T.
The temperature found this way is the EXCITATION temperature, T_exc. In a low-pressure plasma the
levels are not in equilibrium with the electrons, so T_exc is usually far below T_e. That is why it is
never called T_e anywhere in this project (Phase 4 exit gate).

RELIABILITY (E9, envelope.toml): a fit needs at least `min_lines` lines spanning at least
`min_energy_span_ev`; a low R^2 is also flagged. The argon 2p levels span only about 0.6 eV, so a plot
made from 2p -> 1s lines alone is always flagged. That is a property of argon, not a fault.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from plasma_twin.config.loader import load_envelope


@dataclass(frozen=True)
class LinePoint:
    wavelength_nm: float
    intensity: float  # integrated line power (any constant units)
    g_upper: int
    a_per_s: float
    upper_energy_ev: float

    @property
    def y(self) -> float:
        return float(np.log(self.intensity * self.wavelength_nm / (self.g_upper * self.a_per_s)))


@dataclass(frozen=True)
class BoltzmannFit:
    excitation_temperature_ev: float  # T_exc: NOT the electron temperature
    excitation_temperature_uncertainty_ev: float  # one standard error, from the fitted slope
    r_squared: float
    n_lines: int
    energy_span_ev: float
    reliable: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)  # why it is flagged, if it is
    points: tuple[LinePoint, ...] = field(default_factory=tuple)


def fit(points: list[LinePoint]) -> BoltzmannFit:
    """Least-squares straight line through the Boltzmann plot."""
    rules = load_envelope()["oes"]["boltzmann_fit"]
    usable = [p for p in points if p.intensity > 0]
    if len(usable) < 2:
        raise ValueError("a Boltzmann plot needs at least two lines with positive intensity")
    x = np.array([p.upper_energy_ev for p in usable])
    y = np.array([p.y for p in usable])
    n = len(x)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    ss_res, ss_tot = float(np.sum(residuals**2)), float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    slope_error = float(np.sqrt(ss_res / (n - 2) / np.sum((x - x.mean()) ** 2))) if n > 2 else float("inf")
    span = float(x.max() - x.min())
    temperature = -1.0 / slope if slope < 0 else float("inf")
    reasons = []
    if n < rules["min_lines"]:
        reasons.append(f"only {n} lines (at least {rules['min_lines']} needed)")
    if span < rules["min_energy_span_ev"]:
        reasons.append(f"upper levels span {span:.2f} eV (at least {rules['min_energy_span_ev']} eV needed)")
    if r_squared < rules["unreliable_below_r_squared"]:
        reasons.append(f"R^2 = {r_squared:.2f} (below {rules['unreliable_below_r_squared']})")
    if slope >= 0:
        reasons.append("the slope is not negative, so no temperature can be read")
    return BoltzmannFit(temperature, slope_error / slope**2 if slope < 0 else float("inf"), r_squared, n, span,
                        not reasons, tuple(reasons), tuple(usable))


def integrated_intensities(spectrum, lines, half_width_fwhm: float = 3.0) -> list[LinePoint]:
    """Measure each line's area in a spectrum, after removing a flat background.

    The window is +/- `half_width_fwhm` line widths. The background is the median of the edges of a
    window three times wider. Lines whose windows overlap another listed line are skipped, so blends
    never enter the fit.
    """
    from plasma_twin.oes.spectrum import doppler_fwhm_nm
    s = spectrum.settings
    wl = spectrum.wavelength_nm
    chosen = [line for line in lines if s.start_nm < line.wavelength_nm < s.end_nm]
    points = []
    for line in chosen:
        width = np.hypot(s.fwhm_nm, doppler_fwhm_nm(line.wavelength_nm, spectrum.gas_temperature_k))
        half = half_width_fwhm * width
        if any(other is not line and abs(other.wavelength_nm - line.wavelength_nm) < 2 * half for other in chosen):
            continue
        inside = np.abs(wl - line.wavelength_nm) <= half
        edges = (np.abs(wl - line.wavelength_nm) > half) & (np.abs(wl - line.wavelength_nm) <= 3 * half)
        background = float(np.median(spectrum.intensity[edges])) if edges.any() else 0.0
        area = float(np.trapezoid(spectrum.intensity[inside] - background, wl[inside]))
        points.append(LinePoint(line.wavelength_nm, area, line.g_upper, line.a_per_s, line.upper_energy_ev))
    return points


# FR5.4: a level counts as in Boltzmann equilibrium with the electrons when its density is within this factor
# of g_k n_0 exp(-E_k / T_e) (ground state g_0 = 1). Any wider gap means the plasma is not in equilibrium.
EQUILIBRIUM_FACTOR = 2.0


@dataclass(frozen=True)
class LevelPopulation:
    level: str
    energy_ev: float
    weight: int
    density_m3: float  # from the CR model
    boltzmann_m3: float  # what Boltzmann equilibrium at T_e with the ground state would give

    @property
    def ratio(self) -> float:
        return self.density_m3 / self.boltzmann_m3


def populations_vs_boltzmann(cr, ground_density_m3: float, te_ev: float) -> tuple[list[LevelPopulation], bool]:
    """FR5.4: each CR-model level against a Boltzmann distribution at T_e, and whether all of them are in it."""
    from plasma_twin.oes.cr_model import level_data
    data = level_data()
    rows = [LevelPopulation(name, data.energy_ev[name], data.weight[name], density,
                            data.weight[name] * ground_density_m3 * float(np.exp(-data.energy_ev[name] / te_ev)))
            for name, density in cr.populations_m3.items()]
    in_equilibrium = all(1 / EQUILIBRIUM_FACTOR <= r.ratio <= EQUILIBRIUM_FACTOR for r in rows)
    return sorted(rows, key=lambda r: r.energy_ev), in_equilibrium
