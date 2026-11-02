"""0D (volume-averaged) global model of a 13.56 MHz argon CCP: Phase 2c.

WHAT IT SOLVES. Given RF power, pressure and geometry, find the electron temperature T_e, the
electron density n_e and the sheaths. Three balances must hold at once:

1. Particle balance -> T_e. Every ion lost to a surface must be replaced by ionization:
       n_g K_iz(T_e) V = u_B(T_e) A_eff
   n_g, V and A_eff do not depend on n_e, so this fixes T_e alone (Lieberman & Lichtenberg 2005,
   Ch. 10). Power only enters through the sheath width, which shrinks the bulk slightly.
   With excited atoms (Phase 2d, on by default), ionization also runs through metastable and 4p
   atoms whose numbers grow with n_e, so T_e and n_e are then solved together with the three
   excited-state balances (argon_kinetics.py).
2. Electron power balance -> n_e. The power that heats electrons (ohmic heating in the bulk and
   in the sheaths, and stochastic heating at the moving sheath edges) equals what electrons lose
   per ion created (E_c), carry to the walls (E_e) and give the ions in the presheath (T_s / 2).
3. Total power balance -> RF voltage. Ions also gain energy falling through the two RF sheaths
   at the electrodes (V_s per ion). The RF voltage is adjusted until everything absorbed adds up
   to the requested power.

WHY THIS SHEATH MODEL. 0.1-0.5 mbar is 75-375 mTorr. There, an ion's mean free path (about
0.1 mm) is far shorter than the sheath (a few mm), so the collisionless Child law of the
low-pressure textbook model does not apply. This module uses the high-pressure capacitive model
of M. A. Lieberman, UC Berkeley short course (2015), slides 279-285 ("Summary - high pressure
capacitive model", slide 283). Its equations reproduce that course's own worked example, which a
test checks:

    V_s (dc)  = 0.78 V~_s                      V~_s = RF voltage amplitude across one sheath
    e n_s u_B = 1.68 eps0 (2e/M)^(1/2) V_s^(3/2) lambda_i^(1/2) / s_m^(5/2)  (collisional Child law)
    I~_rf     = 1.52 omega eps0 A V~_s / s_m
    P_sh      = (m/2e) eps0 omega^2 (0.24 nu_m s_m + 0.92 v_e) V~_s A          (one sheath)
    P_ohm     = 1.73 (m/2e) eps0 omega^2 (T_e V~_s)^(1/2) nu_m h_l [l + 2 s_m (ln(2/h_l)/pi - 1)] A

(Slide 281 prints the electron mass m inside the Child law; the summary slide and the units show
it is the ion mass M, which is used here.)

WHY THESE EDGE-TO-CENTRE FACTORS. Ions reach the walls by free fall at low pressure and by
diffusion at high pressure. The h factors join both limits smoothly (Lieberman & Lichtenberg 2005,
Ch. 10; the high-pressure limit h_l = 2 (T_e/T_i)^(1/2) lambda_i / l is on slide 271):

    h_l = 0.86 / sqrt(3 + L/(2 lambda_i) + (0.86 L u_B / (pi D_a))^2)
    h_R = 0.80 / sqrt(4 + R/lambda_i + (0.80 R u_B / (chi01 J1(chi01) D_a))^2)

Particle-in-cell simulations show that in a CCP above about 70 mTorr ionization concentrates near
the sheath edges, so the real h_l is 2-3 times above this formula with L = gap (Lafleur & Chabert
2014, shown on slides 277-278). Lieberman's correction is to use the effective size 2 s_m instead
of the gap. That is the default here (`edge_length="sheath"`); `"bulk"` keeps the plain formula
for comparison.

ASSUMPTIONS, stated so they can be defended and later relaxed:
- Symmetric parallel plates of radius R and gap l; the plasma fills the space between them.
  Radial losses go to a floating boundary at r = R.
- Single-step ionization from the ground state. Metastables and stepwise ionization come in Phase 3.
- Gas at a fixed temperature (envelope.toml) until Phase 3 computes it. Ions are at gas temperature.
- Argon ion-neutral cross-section 1e-18 m^2, from lambda_i = 0.003 cm at 1 Torr (slide 284).
- The RF power given is the power absorbed by the plasma (SUPERVISOR_QUESTIONS.md, Q3).
- Production uses the centre density n_0, as in the standard global model (Lieberman & Lichtenberg
  2005, Ch. 10).
- No secondary electrons from the electrodes (pure alpha mode). Known consequence: at tens of watts
  on 14 cm electrodes the model needs RF voltages above 1 kV, and most of the power goes into
  accelerating ions. Real discharges at such voltages start to be sustained partly by secondary
  electrons (gamma mode), which this model leaves out.

Every output is computed from T_e, n_e and the sheath solution; none is set by hand.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy import constants as codata
from scipy.optimize import brentq
from scipy.special import j1

from plasma_twin.config.loader import load_envelope
from plasma_twin.stage1.eedf import SHAPES
from scipy.optimize import root

from plasma_twin.stage1 import argon_kinetics as kin
from plasma_twin.stage1 import gas_flow
from plasma_twin.stage1.rates import ARGON_MASS_KG, ELECTRON_MASS_KG, RateTable, rate_table

E = codata.e
EPS0 = codata.epsilon_0
K_B = codata.k
ION_NEUTRAL_CROSS_SECTION_M2 = 1.0e-18
CHI01 = 2.404825557695773  # first zero of the Bessel function J0: the radial diffusion mode
EDGE_LENGTHS = ("sheath", "bulk")
_REL_TOL = 4 * np.finfo(float).eps


class InputOutOfRange(ValueError):
    """An input lies outside the operating envelope, so the run is refused (event E3)."""


class SolverFailure(RuntimeError):
    """The balances have no solution for these inputs, for example a sheath filling the gap."""


@dataclass(frozen=True)
class Stage1Inputs:
    """One operating point. SI units except where the name says otherwise."""

    rf_power_w: float
    pressure_mbar: float
    electrode_radius_m: float
    electrode_gap_m: float
    eedf: str = "Druyvesteyn"
    gas_temperature_k: float = 300.0
    frequency_hz: float = 13.56e6
    edge_length: str = "sheath"
    excited_states: bool = True  # Phase 2d: metastables and two-step ionization (argon_kinetics.py)
    ar_flow_sccm: float = 0.0  # Phase 3a: 0 means no flow term (the Phase 2 model)
    chamber_diameter_m: float = 0.40
    chamber_height_m: float = 0.40

    @property
    def gas_density_m3(self) -> float:
        """Ideal gas: n_g = p / (k_B T_g), with 1 mbar = 100 Pa."""
        return self.pressure_mbar * 100.0 / (K_B * self.gas_temperature_k)


# ---------------------------------------------------------------- sheath and heating formulas
# Lieberman (2015) slide 283, one function per line, so a test can feed in the slide's own example.
def _heating_constant(omega: float) -> float:
    return ELECTRON_MASS_KG / (2 * E) * EPS0 * omega**2


def bulk_ohmic_power(te: float, v_rf_sheath: float, nu_m: float, h_l: float, gap: float, sheath: float,
                     area: float, omega: float) -> float:
    """P_ohm: electrons pushed back and forth by the RF field lose energy in collisions with atoms."""
    return float(1.73 * _heating_constant(omega) * np.sqrt(te * v_rf_sheath) * nu_m * h_l
                 * (gap + 2 * sheath * (np.log(2 / h_l) / np.pi - 1)) * area)


def sheath_heating_power(nu_m: float, sheath: float, mean_speed: float, v_rf_sheath: float, area: float,
                         omega: float) -> tuple[float, float]:
    """(ohmic, stochastic) heating in ONE sheath. Stochastic: electrons bounce off the moving edge."""
    c = _heating_constant(omega) * v_rf_sheath * area
    return float(c * 0.24 * nu_m * sheath), float(c * 0.92 * mean_speed)


def collisional_child_width(v_dc: float, lambda_i: float, ion_flux: float) -> float:
    """s_m from the collisional Child law, given the ion flux e n_s u_B / e = n_s u_B."""
    return float((1.68 * EPS0 * np.sqrt(2 * E / ARGON_MASS_KG) * v_dc**1.5 * np.sqrt(lambda_i)
                  / (E * ion_flux)) ** 0.4)


def default_inputs(**overrides: Any) -> Stage1Inputs:
    """The envelope defaults (envelope.toml), with any field replaced by a keyword."""
    env = load_envelope()["stage1"]
    values: dict[str, Any] = {
        "rf_power_w": env["rf_power_w"]["default"],
        "pressure_mbar": env["pressure_mbar"]["default"],
        "electrode_radius_m": env["geometry_cm"]["electrode_diameter"] / 200.0,
        "electrode_gap_m": env["geometry_cm"]["electrode_gap"] / 100.0,
        "eedf": env["options"]["eedf"][0],
        "gas_temperature_k": env["fixed"]["gas_temperature_k"],
        "frequency_hz": env["fixed"]["rf_frequency_mhz"] * 1e6,
        "ar_flow_sccm": env["ar_flow_sccm"]["default"],
        "chamber_diameter_m": env["geometry_cm"]["chamber_diameter"] / 100.0,
        "chamber_height_m": env["geometry_cm"]["chamber_height"] / 100.0,
    }
    values.update(overrides)
    return Stage1Inputs(**values)


def validate(inputs: Stage1Inputs) -> None:
    """Refuse inputs outside the operating envelope or impossible geometry (E3, FR2.6)."""
    env = load_envelope()["stage1"]
    for name, value, key in (("RF power (W)", inputs.rf_power_w, "rf_power_w"),
                             ("pressure (mbar)", inputs.pressure_mbar, "pressure_mbar")):
        low, high = env[key]["min"], env[key]["max"]
        if not low <= value <= high:
            raise InputOutOfRange(f"{name} = {value} is outside {low}-{high}")
    geometry = env["geometry_cm"]
    if not (inputs.electrode_radius_m > 0 and inputs.electrode_gap_m > 0):
        raise InputOutOfRange("electrode radius and gap must be positive")
    if 2 * inputs.electrode_radius_m * 100 >= geometry["chamber_diameter"]:
        raise InputOutOfRange("the electrodes must be smaller than the chamber")
    if inputs.electrode_gap_m * 100 >= geometry["chamber_height"]:
        raise InputOutOfRange("the electrode gap must be smaller than the chamber height")
    if inputs.eedf not in SHAPES:
        raise InputOutOfRange(f"EEDF must be one of {sorted(SHAPES)}")
    flow = env["ar_flow_sccm"]
    if inputs.ar_flow_sccm != 0 and not flow["min"] <= inputs.ar_flow_sccm <= flow["max"]:
        raise InputOutOfRange(f"Ar flow (sccm) = {inputs.ar_flow_sccm} is outside {flow['min']}-{flow['max']}")
    if inputs.edge_length not in EDGE_LENGTHS:
        raise InputOutOfRange(f"edge_length must be one of {EDGE_LENGTHS}")


@dataclass(frozen=True)
class Stage1Result:
    """Everything the model computed for one operating point."""

    inputs: Stage1Inputs
    te_ev: float  # effective electron temperature, (2/3) of the mean energy
    screening_te_ev: float  # T_s: sets the Bohm speed and the ambipolar field
    ne_center_m3: float  # n_0, at the centre of the discharge
    ne_sheath_edge_m3: float  # n_s = h_l n_0, at the electrode sheath edge
    gas_density_m3: float
    ion_mean_free_path_m: float
    bohm_speed_m_s: float
    h_axial: float
    h_radial: float
    sheath_width_m: float  # s_m, maximum width of each electrode sheath
    rf_voltage_amplitude_v: float  # across the whole discharge: 2 V~_s
    dc_sheath_voltage_v: float  # V_s at each electrode: sets the ion energy budget
    rf_current_amplitude_a: float
    ion_flux_electrode_m2_s: float
    ion_flux_radial_m2_s: float
    collisional_energy_loss_ev: float  # E_c
    absorbed_power_w: float
    metastable_density_m3: float = 0.0
    resonant_density_m3: float = 0.0
    p4_density_m3: float = 0.0
    ionization_routes: dict[str, float] = field(default_factory=dict)  # fraction of ions from each route
    heating_w: dict[str, float] = field(default_factory=dict)  # how the power enters
    # Where the power goes. "superelastic_return" is negative: energy excited atoms give back.
    losses_w: dict[str, float] = field(default_factory=dict)
    residuals: dict[str, float] = field(default_factory=dict)  # relative, all must be < 1e-8

    def shares_percent(self, which: str) -> dict[str, float]:
        """Heating or loss channels as percentages of the absorbed power (ACC-3)."""
        parts = self.heating_w if which == "heating" else self.losses_w
        return {k: 100.0 * v / self.absorbed_power_w for k, v in parts.items()}

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Discharge:
    """The balance equations for fixed inputs. Kept separate so each step can be tested."""

    def __init__(self, inputs: Stage1Inputs, table: RateTable | None = None) -> None:
        self.x = inputs
        self.rates = table or rate_table(SHAPES[inputs.eedf])
        self.wall = self.rates.wall
        self.n_g = inputs.gas_density_m3
        self.lambda_i = 1.0 / (self.n_g * ION_NEUTRAL_CROSS_SECTION_M2)
        self.t_i_volt = K_B * inputs.gas_temperature_k / E
        self.omega = 2 * np.pi * inputs.frequency_hz
        self.area = np.pi * inputs.electrode_radius_m**2

    # ---------------------------------------------------------------- transport to the walls
    def excited_loss_rate(self) -> float:
        """Excited atoms lost per second: diffusion to the walls plus being pumped away (3a)."""
        x = self.x
        volume = gas_flow.chamber_volume_m3(x.chamber_diameter_m, x.chamber_height_m)
        return (kin.wall_loss_rate(x.electrode_gap_m, x.electrode_radius_m, self.n_g, x.gas_temperature_k)
                + gas_flow.pumping_rate_per_s(self.n_g, volume, x.ar_flow_sccm))

    def bohm_speed(self, te: float) -> float:
        return float(np.sqrt(E * self.wall.screening_ratio * te / ARGON_MASS_KG))

    def ambipolar_diffusion(self, te: float) -> float:
        """D_a = D_i (1 + T_s/T_i), with D_i = k T_i / (M nu_i) and nu_i = v_i / lambda_i."""
        v_i = np.sqrt(8 * E * self.t_i_volt / (np.pi * ARGON_MASS_KG))
        d_i = E * self.t_i_volt * self.lambda_i / (ARGON_MASS_KG * v_i)
        return float(d_i * (1 + self.wall.screening_ratio * te / self.t_i_volt))

    def h_factors(self, te: float, bulk: float, sheath: float) -> tuple[float, float]:
        u_b, d_a, lam = self.bohm_speed(te), self.ambipolar_diffusion(te), self.lambda_i
        length = min(bulk, 2 * sheath) if self.x.edge_length == "sheath" else bulk
        h_l = 0.86 / np.sqrt(3 + length / (2 * lam) + (0.86 * length * u_b / (np.pi * d_a)) ** 2)
        r = self.x.electrode_radius_m
        h_r = 0.80 / np.sqrt(4 + r / lam + (0.80 * r * u_b / (CHI01 * j1(CHI01) * d_a)) ** 2)
        return float(h_l), float(h_r)

    # ---------------------------------------------------------------- balance 1: T_e
    def particle_balance(self, te: float, sheath: float) -> float:
        """ln(production / loss) per unit n_0: zero at the solution."""
        bulk = self.x.electrode_gap_m - 2 * sheath
        h_l, h_r = self.h_factors(te, bulk, sheath)
        r = self.x.electrode_radius_m
        loss_area = 2 * self.area * h_l + 2 * np.pi * r * bulk * h_r
        return float(np.log(self.n_g * self.rates.ionization(te) * self.area * bulk)
                     - np.log(self.bohm_speed(te) * loss_area))

    def solve_te(self, sheath: float) -> float:
        low, high = 0.55, 19.5  # inside the rate table
        if self.particle_balance(low, sheath) > 0 or self.particle_balance(high, sheath) < 0:
            raise SolverFailure("particle balance has no T_e between 0.55 and 19.5 eV")
        return brentq(self.particle_balance, low, high, args=(sheath,), xtol=1e-14, rtol=_REL_TOL, maxiter=200)

    # ---------------------------------------------------------------- balances 2 and 3 for one RF voltage
    def state(self, v_rf_sheath: float, sheath: float) -> dict[str, float]:
        """Everything that follows from a sheath voltage amplitude V~_s and sheath width s_m."""
        x, w = self.x, self.wall
        te = self.solve_te(sheath)
        bulk = x.electrode_gap_m - 2 * sheath
        h_l, h_r = self.h_factors(te, bulk, sheath)
        u_b, t_s = self.bohm_speed(te), w.screening_ratio * te
        nu_m = self.n_g * self.rates.momentum_transfer(te)
        v_e = w.mean_speed_ratio * np.sqrt(E * te / ELECTRON_MASS_KG)
        p_ohm_bulk = bulk_ohmic_power(te, v_rf_sheath, nu_m, h_l, x.electrode_gap_m, sheath, self.area, self.omega)
        one_ohmic, one_stochastic = sheath_heating_power(nu_m, sheath, v_e, v_rf_sheath, self.area, self.omega)
        p_ohm_sheath, p_stochastic = 2 * one_ohmic, 2 * one_stochastic  # two electrode sheaths
        heating_electrons = p_ohm_bulk + p_ohm_sheath + p_stochastic

        loss = self.rates.loss_parts_ev(te)
        e_c = sum(loss.values())
        e_e, v_f = w.escape_energy_ratio * te, w.floating_ratio * te
        electrode_area, radial_area = 2 * self.area * h_l, 2 * np.pi * x.electrode_radius_m * bulk * h_r
        ions_per_n0 = u_b * (electrode_area + radial_area)  # ions lost per second, per unit n_0
        # Energy the electrons supply per ion lost (eV), weighted by where the ion is lost.
        per_n0 = E * u_b * (electrode_area * (e_c + e_e + t_s / 2) + radial_area * (e_c + e_e + t_s / 2 + v_f))
        n0 = heating_electrons / per_n0
        n_s = h_l * n0
        v_dc = 0.78 * v_rf_sheath
        p_ion_rf = 2 * E * n_s * u_b * self.area * v_dc
        child_width = collisional_child_width(v_dc, self.lambda_i, n_s * u_b)
        n_ions = n0 * ions_per_n0
        return {
            "te": te, "t_s": t_s, "n0": n0, "n_s": n_s, "h_l": h_l, "h_r": h_r, "u_b": u_b, "bulk": bulk,
            "child_width": child_width, "v_dc": v_dc, "e_c": e_c,
            "p_ohm_bulk": p_ohm_bulk, "p_ohm_sheath": p_ohm_sheath, "p_stochastic": p_stochastic,
            "p_ion_rf": p_ion_rf, "p_abs": heating_electrons + p_ion_rf,
            "loss_ionization": E * n_ions * loss["ionization"],
            "loss_excitation": E * n_ions * loss["excitation"],
            "loss_elastic": E * n_ions * loss["elastic"],
            "loss_electron_kinetic": E * n_ions * e_e,
            "loss_ion": E * n0 * u_b * (electrode_area * t_s / 2 + radial_area * (t_s / 2 + v_f)) + p_ion_rf,
            "rf_current": 1.52 * self.omega * EPS0 * self.area * v_rf_sheath / sheath,
            "flux_electrode": n_s * u_b, "flux_radial": h_r * n0 * u_b,
        }

    def solve_sheath(self, v_rf_sheath: float) -> dict[str, float]:
        """Find the s_m at which the collisional Child law is satisfied for this voltage."""
        gap = self.x.electrode_gap_m
        mismatch = lambda s: s - self.state(v_rf_sheath, s)["child_width"]  # noqa: E731
        low, high = 1e-7, 0.45 * gap
        if mismatch(low) > 0 or mismatch(high) < 0:
            raise SolverFailure(f"no sheath width fits inside the {gap * 100:.1f} cm gap at V~_s = {v_rf_sheath:.1f} V")
        sheath = brentq(mismatch, low, high, xtol=1e-15, rtol=_REL_TOL, maxiter=200)
        result = self.state(v_rf_sheath, sheath)
        result["sheath"] = sheath
        result["v_rf_sheath"] = v_rf_sheath
        return result

    def solve(self) -> dict[str, float]:
        """Adjust the RF voltage until the absorbed power equals the requested power."""
        target = self.x.rf_power_w
        excess = lambda log_v: self.solve_sheath(np.exp(log_v))["p_abs"] / target - 1  # noqa: E731
        low, high = np.log(1.0), np.log(5000.0)
        if excess(low) > 0 or excess(high) < 0:
            raise SolverFailure(f"no RF voltage between 1 and 5000 V absorbs {target} W")
        log_v = brentq(excess, low, high, xtol=1e-15, rtol=_REL_TOL, maxiter=200)
        return self.solve_sheath(np.exp(log_v))

    # ---------------------------------------------------------------- the full state from all unknowns
    def assemble(self, te: float, n0: float, sheath: float, v_rf_sheath: float,
                 excited: kin.ExcitedDensities | None) -> dict[str, Any]:
        """Every output, and every balance written as ln(gain / loss), from the seven unknowns.

        Both solvers report through this one function, so results and residuals are always
        computed the same way. With `excited=None` the excited-atom terms are left out (Phase 2c).
        """
        x, w = self.x, self.wall
        bulk = x.electrode_gap_m - 2 * sheath
        volume = self.area * bulk
        h_l, h_r = self.h_factors(te, bulk, sheath)
        u_b, t_s = self.bohm_speed(te), w.screening_ratio * te
        nu_m = self.n_g * self.rates.momentum_transfer(te)
        v_e = w.mean_speed_ratio * np.sqrt(E * te / ELECTRON_MASS_KG)
        p_ohm_bulk = bulk_ohmic_power(te, v_rf_sheath, nu_m, h_l, x.electrode_gap_m, sheath, self.area, self.omega)
        one_ohmic, one_stochastic = sheath_heating_power(nu_m, sheath, v_e, v_rf_sheath, self.area, self.omega)
        heating_electrons = p_ohm_bulk + 2 * one_ohmic + 2 * one_stochastic  # two electrode sheaths

        # Ion production (per m^3 per s) and loss (per s) must match: the particle balance.
        if excited is None:
            routes = {"from_ground": n0 * self.n_g * self.rates.ionization(te)}
            excited_power = {"two_step_ionization": 0.0, "excitation_between_levels": 0.0, "superelastic_return": 0.0}
        else:
            routes = kin.ionization_rate(te, n0, self.n_g, excited, self.rates)
            excited_power = kin.excited_electron_power(te, n0, excited)
        electrode_area, radial_area = 2 * self.area * h_l, 2 * np.pi * x.electrode_radius_m * bulk * h_r
        ions_lost = n0 * u_b * (electrode_area + radial_area)
        ions_made = volume * sum(routes.values())

        # Electron energy losses in W. Collisions with ground-state atoms cost E_c per ground ionization.
        ground_parts = self.rates.loss_parts_ev(te)
        ground_rate = routes["from_ground"] * volume * E
        e_e, v_f = w.escape_energy_ratio * te, w.floating_ratio * te
        wall_electron = E * n0 * u_b * (electrode_area + radial_area) * e_e
        wall_ion = E * n0 * u_b * (electrode_area * t_s / 2 + radial_area * (t_s / 2 + v_f))
        losses = {
            "ionization": ground_rate * ground_parts["ionization"] + E * volume * excited_power["two_step_ionization"],
            "excitation": ground_rate * ground_parts["excitation"]
            + E * volume * excited_power["excitation_between_levels"],
            "elastic": ground_rate * ground_parts["elastic"],
            "superelastic_return": E * volume * excited_power["superelastic_return"],
            "electron_kinetic_to_walls": wall_electron,
            "ion_energy_to_walls": wall_ion,
        }
        if excited is None:
            del losses["superelastic_return"]
        electron_losses = sum(losses.values())

        n_s = h_l * n0
        v_dc = 0.78 * v_rf_sheath
        p_ion_rf = 2 * E * n_s * u_b * self.area * v_dc
        losses["ion_energy_to_walls"] += p_ion_rf  # ions also carry the RF-sheath energy to the electrodes
        child_width = collisional_child_width(v_dc, self.lambda_i, n_s * u_b)
        p_abs = heating_electrons + p_ion_rf

        equations = {
            "particle_balance": np.log(ions_made / ions_lost),
            "electron_power_balance": np.log(heating_electrons / electron_losses),
            "child_law": np.log(sheath / child_width),
            "power_balance": np.log(p_abs / x.rf_power_w),
        }
        if excited is not None:
            k_wall = self.excited_loss_rate()
            for level, (gain, loss) in kin.balances(te, n0, self.n_g, excited, self.rates, k_wall).items():
                equations[f"{level}_balance"] = np.log(gain / loss)
        return {
            "te": te, "t_s": t_s, "n0": n0, "n_s": n_s, "h_l": h_l, "h_r": h_r, "u_b": u_b, "sheath": sheath,
            "v_rf_sheath": v_rf_sheath, "v_dc": v_dc, "excited": excited,
            "routes": {k: v * volume / ions_made for k, v in routes.items()},
            "e_c": (losses["ionization"] + losses["excitation"] + losses["elastic"]
                    + losses.get("superelastic_return", 0.0)) / (E * ions_made),
            "heating": {"ohmic_bulk": p_ohm_bulk, "ohmic_sheaths": 2 * one_ohmic, "stochastic": 2 * one_stochastic,
                        "ion_acceleration_rf_sheaths": p_ion_rf},
            "losses": losses, "p_abs": p_abs, "equations": equations,
            "rf_current": 1.52 * self.omega * EPS0 * self.area * v_rf_sheath / sheath,
            "flux_electrode": n_s * u_b, "flux_radial": h_r * n0 * u_b,
        }

    def solve_with_excited_states(self) -> dict[str, Any]:
        """Solve all seven balances together, starting from the ground-state-only solution.

        With two-step ionization, T_e depends on n_e (more electrons -> more excited atoms -> more
        ionization), so the balances can no longer be solved one after another. The unknowns are
        ln T_e, ln n_0, ln s_m, ln V~_s and the three excited densities; Powell's hybrid method
        (scipy.optimize.root) drives every ln(gain / loss) to zero.
        """
        x = self.x
        ground = self.solve()
        k_wall = self.excited_loss_rate()
        start = kin.solve_densities(ground["te"], ground["n0"], self.n_g, self.rates, k_wall)
        y0 = np.log([ground["te"], ground["n0"], ground["sheath"], ground["v_rf_sheath"],
                     start.metastable_m3, start.resonant_m3, start.p4_m3])
        low_te, high_te = 0.56, 19.4
        max_sheath = 0.49 * x.electrode_gap_m

        def unpack(y: np.ndarray) -> tuple[float, float, float, float, kin.ExcitedDensities]:
            te, n0, sheath, v, nm, nr, npp = np.exp(y)
            return (float(np.clip(te, low_te, high_te)), float(n0), float(min(sheath, max_sheath)), float(v),
                    kin.ExcitedDensities(float(nm), float(nr), float(npp)))

        def residuals(y: np.ndarray) -> np.ndarray:
            return np.array(list(self.assemble(*unpack(y))["equations"].values()))

        best = None
        for method in ("hybr", "lm"):
            found = root(residuals, y0, method=method, options={"xtol": 1e-14} if method == "hybr" else {"xtol": 1e-15})
            if best is None or np.max(np.abs(found.fun)) < np.max(np.abs(best.fun)):
                best = found
            if np.max(np.abs(best.fun)) < 1e-11:
                break
        te, n0, sheath, v, excited = unpack(best.x)
        if not (low_te < te < high_te and sheath < max_sheath) or np.max(np.abs(best.fun)) > 1e-9:
            raise SolverFailure(f"the excited-state balances did not converge (largest residual {np.max(np.abs(best.fun)):.1e})")
        return self.assemble(te, n0, sheath, v, excited)


def solve(inputs: Stage1Inputs, check_envelope: bool = True) -> Stage1Result:
    """Run the global model for one operating point.

    `check_envelope=False` is only for reproducing published cases outside our envelope (tests and
    validation); everything the user runs goes through the envelope check (E3).
    """
    if check_envelope:
        validate(inputs)
    discharge = _Discharge(inputs)
    if inputs.excited_states:
        s = discharge.solve_with_excited_states()
    else:
        g = discharge.solve()
        s = discharge.assemble(g["te"], g["n0"], g["sheath"], g["v_rf_sheath"], None)
    residuals = {name: float(abs(np.expm1(value))) for name, value in s["equations"].items()}
    residuals["energy_accounting"] = abs(sum(s["losses"].values()) - s["p_abs"]) / s["p_abs"]
    excited = s["excited"] or kin.ExcitedDensities(0.0, 0.0, 0.0)
    return Stage1Result(
        inputs=inputs, te_ev=s["te"], screening_te_ev=s["t_s"], ne_center_m3=s["n0"], ne_sheath_edge_m3=s["n_s"],
        gas_density_m3=discharge.n_g, ion_mean_free_path_m=discharge.lambda_i, bohm_speed_m_s=s["u_b"],
        h_axial=s["h_l"], h_radial=s["h_r"], sheath_width_m=s["sheath"],
        rf_voltage_amplitude_v=2 * s["v_rf_sheath"], dc_sheath_voltage_v=s["v_dc"],
        rf_current_amplitude_a=s["rf_current"], ion_flux_electrode_m2_s=s["flux_electrode"],
        ion_flux_radial_m2_s=s["flux_radial"], collisional_energy_loss_ev=s["e_c"],
        absorbed_power_w=s["p_abs"], metastable_density_m3=excited.metastable_m3,
        resonant_density_m3=excited.resonant_m3, p4_density_m3=excited.p4_m3, ionization_routes=s["routes"],
        heating_w=s["heating"], losses_w=s["losses"], residuals=residuals,
    )
