"""0D (volume-averaged) global model of a 13.56 MHz argon CCP: Phase 2c.

WHAT IT SOLVES. Given RF power, pressure and geometry, find the electron temperature T_e, the
electron density n_e and the sheaths. Three balances must hold at once:

1. Particle balance -> T_e. Every ion lost to a surface must be replaced by ionization:
       n_g K_iz(T_e) V = u_B(T_e) A_eff
   n_g, V and A_eff do not depend on n_e, so this fixes T_e alone (Lieberman & Lichtenberg 2005,
   Ch. 10). Power only enters through the sheath width, which shrinks the bulk slightly.
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
    heating_w: dict[str, float] = field(default_factory=dict)  # how the power enters
    losses_w: dict[str, float] = field(default_factory=dict)  # where the power goes
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


def solve(inputs: Stage1Inputs, check_envelope: bool = True) -> Stage1Result:
    """Run the global model for one operating point.

    `check_envelope=False` is only for reproducing published cases outside our envelope (tests and
    validation); everything the user runs goes through the envelope check (E3).
    """
    if check_envelope:
        validate(inputs)
    discharge = _Discharge(inputs)
    s = discharge.solve()
    x = inputs
    heating = {"ohmic_bulk": s["p_ohm_bulk"], "ohmic_sheaths": s["p_ohm_sheath"],
               "stochastic": s["p_stochastic"], "ion_acceleration_rf_sheaths": s["p_ion_rf"]}
    losses = {"ionization": s["loss_ionization"], "excitation": s["loss_excitation"],
              "elastic": s["loss_elastic"], "electron_kinetic_to_walls": s["loss_electron_kinetic"],
              "ion_energy_to_walls": s["loss_ion"]}
    bulk = x.electrode_gap_m - 2 * s["sheath"]
    production = discharge.n_g * discharge.rates.ionization(s["te"]) * s["n0"] * discharge.area * bulk
    lost = s["n0"] * s["u_b"] * (2 * discharge.area * s["h_l"] + 2 * np.pi * x.electrode_radius_m * bulk * s["h_r"])
    residuals = {
        "particle_balance": abs(production - lost) / lost,
        "power_balance": abs(s["p_abs"] - x.rf_power_w) / x.rf_power_w,
        "energy_accounting": abs(sum(losses.values()) - s["p_abs"]) / s["p_abs"],
        "child_law": abs(s["sheath"] - s["child_width"]) / s["sheath"],
    }
    return Stage1Result(
        inputs=x, te_ev=s["te"], screening_te_ev=s["t_s"], ne_center_m3=s["n0"], ne_sheath_edge_m3=s["n_s"],
        gas_density_m3=discharge.n_g, ion_mean_free_path_m=discharge.lambda_i, bohm_speed_m_s=s["u_b"],
        h_axial=s["h_l"], h_radial=s["h_r"], sheath_width_m=s["sheath"],
        rf_voltage_amplitude_v=2 * s["v_rf_sheath"], dc_sheath_voltage_v=s["v_dc"],
        rf_current_amplitude_a=s["rf_current"], ion_flux_electrode_m2_s=s["flux_electrode"],
        ion_flux_radial_m2_s=s["flux_radial"], collisional_energy_loss_ev=s["e_c"],
        absorbed_power_w=s["p_abs"], heating_w=heating, losses_w=losses, residuals=residuals,
    )
