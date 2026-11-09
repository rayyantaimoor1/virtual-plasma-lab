"""Argon with N2 and O2 admixtures: Phase 3e.

WHY: the supervisor's Stage 1 gas is argon with 5 % N2 and 5 % O2 of the argon flow (SUPERVISOR_
QUESTIONS.md, Q5). Even a few per cent of a molecular gas changes an argon plasma a lot:
- molecules soak up electron energy in vibrational and electronic excitation, so T_e must rise;
- they quench argon metastables (and N2 gets excited to N2(C), the 337 nm band used in Phase 4);
- Ar+ hands its charge to N2 and O2, so new ions appear;
- O2 captures electrons (O2 + e -> O- + O), making a negative-ion ("electronegative") plasma,
  which changes how ions reach the walls.

Every reaction, rate and choice here was written into BUILD_STEPS.md (Phase 3e) with its source
before this code was written. Row numbers refer to Dong et al., arXiv:2601.08138 (2026), Table A1,
unless another source is named.

THE UNKNOWNS, solved together with scipy.optimize.root (Powell's hybrid method):
    T_e, n_e, s_m, V~_s, the three excited argon levels, one density per positive ion (Ar+, N2+, O2+)
    and, with O2, the densities of O-, O atoms and O2(a1Delta).
THE EQUATIONS: one balance per species (gain = loss), quasi-neutrality (positive charge = electrons
+ negative ions), the electron power balance, the collisional Child law and the total power balance.
Each is written as ln(gain / loss) so that every residual is a relative error.
To find the solution reliably, the admixture is stepped up from 0.1 % of its value to 100 %, each
step starting from the previous answer, beginning with the pure-argon solution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import constants as codata
from scipy.optimize import root

from plasma_twin.stage1 import argon_kinetics as kin
from plasma_twin.stage1 import gas_flow
from plasma_twin.stage1.eedf import SHAPES
from plasma_twin.stage1.rates import ARGON_MASS_KG, ELECTRON_MASS_KG, MOLECULE_MASS_KG, molecule_table

E = codata.e
EPS0 = codata.epsilon_0
OXYGEN_ATOM_MASS_KG = 15.999 * codata.atomic_mass
ION_MASS_KG = {"Ar+": ARGON_MASS_KG, "N2+": MOLECULE_MASS_KG["N2"], "O2+": MOLECULE_MASS_KG["O2"]}

# Charge transfer, Anicich, J. Phys. Chem. Ref. Data 22, 1469 (1993), evaluated, 300 K, +/-20 %.
K_CHARGE_TRANSFER = {"N2": 1.10e-17, "O2": 4.60e-17}
# Argon metastables quenched by N2: 3e-17 m^3/s in total (Le Calve & Bourene 1973, as cited in
# arXiv:1104.5373), of which 2.8e-17 forms N2(C) (Pothiraja et al. 2010, as cited in arXiv:1109.5620).
K_QUENCH_N2 = 3.0e-17
K_QUENCH_N2_TO_C = 2.8e-17
# Argon metastables quenched by O2, rows 31 and 33 (row 31 flagged as fast in BUILD_STEPS.md).
K_QUENCH_O2_TO_GROUND = 1.12e-15
K_QUENCH_O2_DISSOCIATING = 5.8e-17
# Oxygen heavy-particle reactions.
K_DETACH_BY_O = 1.4e-16  # row 27: O- + O -> O2 + e
K_DETACH_BY_O2A = 1.0e-16  # row 28: O- + O2(a) -> O3 + e (O3 not tracked)
GAMMA_O = 0.09  # O wall recombination, Kemaneci et al., arXiv:1612.07268, Table VIII
GAMMA_O2A = 0.007  # O2(a) wall quenching, row 93
O_ELECTRON_AFFINITY_EV = 1.461  # NIST Chemistry WebBook (Neumark et al. 1985; Blondel et al. 2005)
O2_IONIZATION_EV = 12.072  # Biagi O2 ionization threshold
O2A_ENERGY_EV = 0.977  # Biagi O2(a1Delta) excitation threshold


def ion_ion_recombination(gas_temperature_k: float) -> float:
    """Row 19 (O2+ + O-), used for O- with every positive ion; see BUILD_STEPS.md, 3e."""
    return 1.5e-13 * (300.0 / gas_temperature_k) ** 0.5


def oxygen_electron_rates(te: float) -> dict[str, float]:
    """Electron reactions with O-, O2+ and O2(a) (Maxwellian fits, rows 16, 21, 23-26), m^3/s."""
    return {
        "detach": 1.73e-13 * np.exp(-5.76 / te + 7.3 / te**2 - 3.48 / te**3),  # row 16: e + O- -> O + 2e
        "recombine_o2p": 2.2e-14 * te**-0.5,  # row 21: e + O2+ -> O + O
        "a_attach": 2.28e-16 * np.exp(-2.29 / te),  # row 23: e + O2(a) -> O + O-
        "a_ionize": 9.0e-16 * np.exp(-11.6 / te),  # row 24: e + O2(a) -> O2+ + 2e
        "a_dissociate": 4.2e-15 * np.exp(-4.6 / te),  # row 25: e + O2(a) -> 2O + e
        "a_deexcite": 5.6e-15 * np.exp(-2.2 / te),  # row 26: e + O2(a) -> O2 + e
    }


def _diffusion_scale(mass_kg: float) -> float:
    """sqrt(mu(Ar-Ar) / mu(X-Ar)): Chapman-Enskog mass scaling of the excited-argon diffusion coefficient."""
    reduced = lambda m: m * ARGON_MASS_KG / (m + ARGON_MASS_KG)  # noqa: E731
    return float(np.sqrt(reduced(ARGON_MASS_KG) / reduced(mass_kg)))


@dataclass(frozen=True)
class Composition:
    """Feed mole fractions from flows given as a percentage of the Ar flow."""

    n2_percent: float
    o2_percent: float

    @property
    def fractions(self) -> tuple[float, float, float]:
        """Ar, N2 and O2 feed fractions; the admixtures are a percentage of the Ar flow (LI-2)."""
        f_n2, f_o2 = self.n2_percent / 100, self.o2_percent / 100
        total = 1 + f_n2 + f_o2
        return 1 / total, f_n2 / total, f_o2 / total


class MixtureModel:
    """All mixture balances for one operating point (inputs and geometry come from a _Discharge)."""

    def __init__(self, discharge: Any) -> None:
        self.d = discharge
        x = discharge.x
        self.composition = Composition(x.n2_percent_of_ar, x.o2_percent_of_ar)
        self.shape = SHAPES[x.eedf]
        self.has_n2, self.has_o2 = x.n2_percent_of_ar > 0, x.o2_percent_of_ar > 0
        self.ions = ["Ar+"] + (["N2+"] if self.has_n2 else []) + (["O2+"] if self.has_o2 else [])
        self.n2_rates = molecule_table("N2", self.shape) if self.has_n2 else None
        self.o2_rates = molecule_table("O2", self.shape) if self.has_o2 else None
        self.names = (["te", "ne", "sheath", "v", "m", "r", "p"] + [f"ion:{i}" for i in self.ions]
                      + (["o_minus", "o", "o2a"] if self.has_o2 else []))
        volume = gas_flow.chamber_volume_m3(x.chamber_diameter_m, x.chamber_height_m)
        self.k_flow = gas_flow.pumping_rate_per_s(discharge.n_g, volume, x.ar_flow_sccm)
        self.k_wall_m = discharge.excited_loss_rate()
        tg = x.gas_temperature_k
        self.k_wall_o = (kin.wall_loss_rate(x.electrode_gap_m, x.electrode_radius_m, discharge.n_g, tg, OXYGEN_ATOM_MASS_KG,
                                            GAMMA_O, _diffusion_scale(OXYGEN_ATOM_MASS_KG)) + self.k_flow)
        self.k_wall_a = (kin.wall_loss_rate(x.electrode_gap_m, x.electrode_radius_m, discharge.n_g, tg, MOLECULE_MASS_KG["O2"],
                                            GAMMA_O2A, _diffusion_scale(MOLECULE_MASS_KG["O2"])) + self.k_flow)
        self.k_rec = ion_ion_recombination(tg)
        self.scale = 1.0  # fraction of the requested admixture, stepped up by the solver

    # ------------------------------------------------------------------ feed densities at the current step
    def feed(self) -> tuple[float, float, float]:
        """The feed fractions after the admixture scaling used to reach a hard mixture step by step."""
        n2 = Composition(self.composition.n2_percent * self.scale, self.composition.o2_percent * self.scale)
        x_ar, x_n2, x_o2 = n2.fractions
        n = self.d.n_g
        return x_ar * n, x_n2 * n, x_o2 * n

    def unpack(self, y: np.ndarray) -> dict[str, float]:
        """The solver's log-variables as physical values, with T_e kept inside the rate table."""
        values = dict(zip(self.names, np.exp(y)))
        values["te"] = float(np.clip(values["te"], 0.56, 19.4))
        values["sheath"] = float(min(values["sheath"], 0.49 * self.d.x.electrode_gap_m))
        return values

    # ------------------------------------------------------------------ every balance at once
    def evaluate(self, y: np.ndarray) -> dict[str, Any]:
        """Every balance equation (particles, power, sheath) at one solver state."""
        d, x, w, v = self.d, self.d.x, self.d.wall, self.unpack(y)
        te, ne, sheath, vrf = v["te"], v["ne"], v["sheath"], v["v"]
        n_ar, n_n2, n_o2_feed = self.feed()
        ions = {i: v[f"ion:{i}"] for i in self.ions}
        n_neg = v.get("o_minus", 0.0)
        n_o, n_a = v.get("o", 0.0), v.get("o2a", 0.0)
        # Oxygen atoms are conserved: what is not O, O2(a), O- or O2+ is still ground-state O2.
        n_o2 = n_o2_feed - n_a - n_o / 2 - n_neg / 2 - ions.get("O2+", 0.0)
        if self.has_o2 and n_o2 <= 0:
            return {"equations": {"oxygen_conservation": 50.0}}
        bulk = x.electrode_gap_m - 2 * sheath
        volume = d.area * bulk
        radial_area = 2 * np.pi * x.electrode_radius_m * bulk
        alpha = n_neg / ne
        t_s = w.screening_ratio * te
        # Electronegative Bohm factor (Kemaneci et al. 2016, Eqs. 11 and 14): sqrt((1 + a_s)/(1 + a_s g)),
        # g = T_e / T_negative, unless attachment outpaces ambipolar diffusion (then the factor is 1).
        # a_s is the electronegativity AT THE SHEATH EDGE, as Eq. 11 defines it. With Boltzmann negative
        # ions (the assumption behind Eq. 11), n_- ∝ n_e^g, so a_s = a_0 (n_e,edge / n_e,centre)^(g - 1).
        # CHANGED 3 Nov 2026 from the pre-registered rule, which used the centre value a_0: with g ~ 110
        # that cut the ion exit speed about threefold at 1 % O2 and made n_e RISE with O2, against the
        # measured trend. The fix follows the source's own definition, not any comparison with data.
        en_factor, attachment_dominated, alpha_edge = 1.0, True, alpha
        if self.has_o2:
            k_att = n_o2 * self.o2_rates.k("attachment", te)
            inverse_lambda_sq = (np.pi / bulk) ** 2 + (2.404825557695773 / x.electrode_radius_m) ** 2
            tau = 1.0 / (inverse_lambda_sq * d.ambipolar_diffusion(te))
            attachment_dominated = tau * k_att > 1
            if not attachment_dominated:
                gamma = te / (codata.k * x.gas_temperature_k / E)
                h_ar, _ = d.h_factors(te, bulk, sheath, ION_MASS_KG["Ar+"])
                alpha_edge = alpha * (h_ar / (1 + alpha)) ** (gamma - 1)
                en_factor = float(np.sqrt((1 + alpha_edge) / (1 + alpha_edge * gamma)))

        # Transport of each positive ion to the electrodes and the side.
        flux, lost, h = {}, {}, {}
        for ion in self.ions:
            h_l, h_r = d.h_factors(te, bulk, sheath, ION_MASS_KG[ion])
            h_l, h_r = h_l / (1 + alpha), h_r / (1 + alpha)
            u_b = d.bohm_speed(te, ION_MASS_KG[ion]) * en_factor
            flux[ion] = h_l * ions[ion] * u_b  # per m^2 at each electrode
            lost[ion] = ions[ion] * u_b * (2 * d.area * h_l + radial_area * h_r)  # per s
            h[ion] = (h_l, h_r, u_b)

        # Argon: excited levels and ionization, with metastables also quenched by the molecules.
        excited = kin.ExcitedDensities(v["m"], v["r"], v["p"])
        quench_m = n_n2 * K_QUENCH_N2 + n_o2 * (K_QUENCH_O2_TO_GROUND + K_QUENCH_O2_DISSOCIATING)
        kin_bal = kin.balances(te, ne, n_ar, excited, d.rates, self.k_wall_m, quench_m)
        ar_routes = kin.ionization_rate(te, ne, n_ar, excited, d.rates)
        rec = self.k_rec * n_neg  # per positive ion, 1/s
        gains = {"Ar+": sum(ar_routes.values())}
        losses = {"Ar+": lost["Ar+"] / volume + ions["Ar+"] * (n_n2 * K_CHARGE_TRANSFER["N2"]
                                                               + n_o2 * K_CHARGE_TRANSFER["O2"] + rec)}
        routes = {f"argon_{k}": val for k, val in ar_routes.items()}
        if self.has_n2:
            direct = ne * n_n2 * self.n2_rates.k("ionization", te)
            transfer = ions["Ar+"] * n_n2 * K_CHARGE_TRANSFER["N2"]
            gains["N2+"] = direct + transfer
            losses["N2+"] = lost["N2+"] / volume + ions["N2+"] * rec
            routes["n2_direct"] = direct
        ox = oxygen_electron_rates(te)
        if self.has_o2:
            direct = ne * n_o2 * self.o2_rates.k("ionization", te) + ne * n_a * ox["a_ionize"]
            transfer = ions["Ar+"] * n_o2 * K_CHARGE_TRANSFER["O2"]
            gains["O2+"] = direct + transfer
            losses["O2+"] = lost["O2+"] / volume + ions["O2+"] * (rec + ne * ox["recombine_o2p"])
            routes["o2_direct"] = direct

        equations: dict[str, float] = {f"{ion}_balance": np.log(gains[ion] / losses[ion]) for ion in self.ions}
        for level, (gain, loss) in kin_bal.items():
            equations[f"{level}_balance"] = np.log(gain / loss)
        equations["quasi_neutrality"] = np.log(sum(ions.values()) / (ne + n_neg))

        # Oxygen species.
        attach = dissociation = 0.0
        if self.has_o2:
            attach = ne * n_o2 * self.o2_rates.k("attachment", te)
            dissociation = ne * n_o2 * self.o2_rates.k("dissociation", te)
            positive = sum(ions.values())
            neg_gain = attach + ne * n_a * ox["a_attach"]
            neg_loss = n_neg * (n_o * K_DETACH_BY_O + n_a * K_DETACH_BY_O2A + ne * ox["detach"] + self.k_rec * positive)
            o_gain = (2 * dissociation + attach + 2 * excited.metastable_m3 * n_o2 * K_QUENCH_O2_DISSOCIATING
                      + 2 * ne * ions["O2+"] * ox["recombine_o2p"] + self.k_rec * n_neg * positive
                      + 2 * ne * n_a * ox["a_dissociate"] + ne * n_a * ox["a_attach"])
            o_loss = n_o * self.k_wall_o + n_neg * n_o * K_DETACH_BY_O
            a_gain = ne * n_o2 * self.o2_rates.k("to_o2_a", te)
            a_loss = n_a * (self.k_wall_a + ne * (ox["a_attach"] + ox["a_ionize"] + ox["a_dissociate"] + ox["a_deexcite"])
                            + n_neg * K_DETACH_BY_O2A)
            equations["o_minus_balance"] = np.log(neg_gain / neg_loss)
            equations["o_balance"] = np.log(o_gain / o_loss)
            equations["o2a_balance"] = np.log(a_gain / a_loss)

        # Electron heating (same formulas as the argon model), with the electron sheath-edge density
        # equal to the positive-ion density there and nu_m summed over the gases.
        n_edge = sum(h[i][0] * ions[i] for i in self.ions)
        h_e = n_edge / ne
        nu_m = n_ar * d.rates.momentum_transfer(te)
        if self.has_n2:
            nu_m += n_n2 * self.n2_rates.k("momentum_transfer", te)
        if self.has_o2:
            nu_m += n_o2 * self.o2_rates.k("momentum_transfer", te)
        v_e = w.mean_speed_ratio * np.sqrt(E * te / ELECTRON_MASS_KG)
        from plasma_twin.stage1.global_model import bulk_ohmic_power, collisional_child_width, sheath_heating_power
        p_ohm_bulk = bulk_ohmic_power(te, vrf, nu_m, h_e, x.electrode_gap_m, sheath, d.area, d.omega)
        one_ohmic, one_stochastic = sheath_heating_power(nu_m, sheath, v_e, vrf, d.area, d.omega)
        heating_electrons = p_ohm_bulk + 2 * one_ohmic + 2 * one_stochastic

        # Electron energy losses (W).
        parts = d.rates.loss_parts_ev(te)
        ground = ar_routes["from_ground"] * volume * E
        excited_power = kin.excited_electron_power(te, ne, excited)
        loss_w = {
            "ionization": ground * parts["ionization"] + E * volume * excited_power["two_step_ionization"],
            "excitation": ground * parts["excitation"] + E * volume * excited_power["excitation_between_levels"],
            "elastic": ground * parts["elastic"],
            "superelastic_return": E * volume * excited_power["superelastic_return"],
        }
        for gas, rates, density in (("N2", self.n2_rates, n_n2), ("O2", self.o2_rates, n_o2)):
            if rates is None:
                continue
            base = E * volume * ne * density
            loss_w["ionization"] += base * rates.k("ionization", te) * rates.ionization_threshold_ev
            loss_w["excitation"] += base * rates.k("excitation_energy", te)
            loss_w["elastic"] += base * rates.k("elastic_energy", te)
            if gas == "O2":
                loss_w["attachment"] = base * rates.k("attachment_energy", te)
        if self.has_o2:
            loss_w["ionization"] += E * volume * ne * n_a * ox["a_ionize"] * (O2_IONIZATION_EV - O2A_ENERGY_EV)
            loss_w["excitation"] += E * volume * ne * n_a * ox["a_dissociate"] * 4.6  # row 25 activation energy
            loss_w["superelastic_return"] -= E * volume * ne * n_a * ox["a_deexcite"] * O2A_ENERGY_EV
            loss_w["detachment"] = E * volume * ne * n_neg * ox["detach"] * O_ELECTRON_AFFINITY_EV
        e_e, v_f = w.escape_energy_ratio * te, w.floating_ratio * te
        electrons_lost = sum(lost.values())  # O- stays inside, so electrons leave with the positive ions
        loss_w["electron_kinetic_to_walls"] = E * electrons_lost * e_e
        loss_w["ion_energy_to_walls"] = sum(
            E * ions[i] * h[i][2] * (2 * d.area * h[i][0] * t_s / 2 + radial_area * h[i][1] * (t_s / 2 + v_f))
            for i in self.ions)
        electron_losses = sum(loss_w.values())

        v_dc = 0.78 * vrf
        total_flux = sum(flux.values())
        mean_mass = sum(ION_MASS_KG[i] * flux[i] for i in self.ions) / total_flux
        p_ion_rf = 2 * E * total_flux * d.area * v_dc
        loss_w["ion_energy_to_walls"] += p_ion_rf
        child = collisional_child_width(v_dc, d.lambda_i, total_flux, mean_mass)
        p_abs = heating_electrons + p_ion_rf
        equations["electron_power_balance"] = np.log(heating_electrons / electron_losses)
        equations["child_law"] = np.log(sheath / child)
        equations["power_balance"] = np.log(p_abs / x.rf_power_w)

        made = sum(gains.values())
        n2c = 0.0
        if self.has_n2:
            n2c = ne * n_n2 * self.n2_rates.k("to_n2_c", te) + excited.metastable_m3 * n_n2 * K_QUENCH_N2_TO_C
        e_c = sum(loss_w[k] for k in ("ionization", "excitation", "elastic", "superelastic_return", "attachment",
                                       "detachment") if k in loss_w) / (E * volume * made)
        return {
            "equations": equations, "te": te, "t_s": t_s, "n0": ne, "n_s": n_edge, "h_l": h_e,
            "h_r": h["Ar+"][1], "u_b": h["Ar+"][2], "sheath": sheath, "v_rf_sheath": vrf, "v_dc": v_dc,
            "excited": excited, "routes": {k: val / made for k, val in routes.items()}, "e_c": e_c,
            "heating": {"ohmic_bulk": p_ohm_bulk, "ohmic_sheaths": 2 * one_ohmic, "stochastic": 2 * one_stochastic,
                        "ion_acceleration_rf_sheaths": p_ion_rf},
            "losses": loss_w, "p_abs": p_abs,
            "rf_current": 1.52 * d.omega * EPS0 * d.area * vrf / sheath,
            "flux_electrode": total_flux, "flux_radial": sum(ions[i] * h[i][2] * h[i][1] for i in self.ions),
            "mixture": {
                "ion_densities_m3": ions, "negative_ion_density_m3": n_neg, "electronegativity": alpha,
                "o_atom_density_m3": n_o, "o2a_density_m3": n_a, "n2_density_m3": n_n2, "o2_density_m3": n_o2,
                "argon_density_m3": n_ar, "n2c_excitation_m3_s": n2c,
                "attachment_dominated": attachment_dominated if self.has_o2 else None,
                "sheath_edge_electronegativity": alpha_edge,
            },
        }

    def residuals(self, y: np.ndarray) -> np.ndarray:
        """The balance equations as residuals for the root finder (ACC-3)."""
        eq = self.evaluate(y)["equations"]
        if "oxygen_conservation" in eq:
            return np.full(len(self.names), 50.0)
        return np.array(list(eq.values()))

    # ------------------------------------------------------------------ the continuation solver
    def solve(self, argon: dict[str, Any], start: np.ndarray | None = None) -> dict[str, Any]:
        """Step the admixture up from 0.1 % of its value, starting from the pure-argon solution."""
        if start is not None:
            steps, y = [1.0], start
        else:
            steps = [1e-3, 3e-3, 1e-2, 3e-2, 0.1, 0.2, 0.4, 0.7, 1.0]
            ne = argon["n0"]
            ex = argon["excited"]
            guess = {"te": argon["te"], "ne": ne, "sheath": argon["sheath"], "v": argon["v_rf_sheath"],
                     "m": ex.metastable_m3, "r": ex.resonant_m3, "p": ex.p4_m3, "ion:Ar+": ne,
                     "ion:N2+": 1e-3 * ne, "ion:O2+": 1e-3 * ne, "o_minus": 1e-4 * ne}
            _, _, o2_feed = Composition(0, self.composition.o2_percent * steps[0]).fractions
            guess["o"] = guess["o2a"] = 1e-3 * o2_feed * self.d.n_g + 1.0
            y = np.log([guess[n] for n in self.names])
        for step in steps:
            self.scale = step
            best = None
            for method in ("hybr", "lm"):
                found = root(self.residuals, y, method=method,
                             options={"xtol": 1e-14} if method == "hybr" else {"xtol": 1e-15, "maxiter": 5000})
                if best is None or np.max(np.abs(found.fun)) < np.max(np.abs(best.fun)):
                    best = found
                if np.max(np.abs(best.fun)) < 1e-11:
                    break
            if np.max(np.abs(best.fun)) > 1e-9:
                from plasma_twin.stage1.global_model import SolverFailure
                raise SolverFailure(f"the mixture balances did not converge at {100 * step:.1f} % of the admixture "
                                    f"(largest residual {np.max(np.abs(best.fun)):.1e})")
            y = best.x
        state = self.evaluate(y)
        state["solution_vector"] = y
        return state
