"""Gas-phase model of the discharge inside O2 bubbles in water: Phase 7 (FR8.x, FR9.1, FR9.2).

WHY: the supervisor's underwater plasma burns inside O2 bubbles at 1 atm (Maxwellian EEDF). What
disinfects is the chemistry it starts: O atoms make ozone, and water vapour gives OH and H2O2. This
module goes from the electrical pulse to the O3 and H2O2 the bubbles carry into the water.

RULES (BUILD_STEPS.md, Phase 7, fixed before this code):
- Bubble gas: O2 saturated with water vapour at the water temperature (NIST Antoine coefficients), or
  O2 only. Gas temperature = water temperature, pressure 1 atm.
- T_e: during the pulse, electron production by ionization (O2 Biagi, H2O Itikawa) equals loss by
  dissociative attachment (O2 Biagi, H2O Itikawa). Recombination and three-body attachment are left
  out of this balance; that is stated, not hidden.
- Energy branching (G-values): each electron process takes the share n_g k_j eps_j / sum of the pulse
  energy. O2 "A3 DISOC" (6.1 eV) gives O + O, "B3 DISOC" (8.4 eV) gives O + O(1D) (Biagi's names);
  Itikawa's "OH (X)" cross-section (Harb et al. 2001) gives OH + H. No discharge volume is needed.
- n_e (only for the Stark width): P_pulse = e n_e n_g W V, V a channel of length = gap and diameter
  from p d_min = 0.20 mm bar (Briels et al. 2008). This diameter is an assumption.
- Afterglow: the radicals of one pulse are spread over the gas that flows past between pulses
  (Q / f, a plug-flow assumption) and react for one period with JPL 19-5 rate constants.
Every constant is read from data/reference/constants/stage2_constants.csv, which names its source.

ASSUMPTIONS, stated so they can be defended:
- Only a share of the electrical power reaches the bubble gas (`power_share`); the rest goes into the
  water (conduction, heat, shock waves). CHANGED WHILE BUILDING (4 Nov 2026): the first version put all
  100 W into 100 sccm of O2, about 14 eV per molecule, so every pulse split all the O2 and no ozone
  survived. The share is not measured for this device, so it is a visible input. Its default is the
  largest share that keeps the model valid (at most 10 % of the O2 split per pulse) at the default
  operating point; see default_power_share().
- Itikawa gives no electronic-excitation total for H2O; its energy loss is ionization, attachment,
  vibration, rotation (J = 0-1, 0-2, 0-3) and the OH(X) dissociation. The OH(X) table has no threshold,
  so its first tabulated energy (10 eV) is used as the energy each dissociation costs.
- Ions are not followed after the pulse; O- from dissociative attachment is counted as an O atom.
- O + O + M recombination is not in JPL 19-5 and is left out; the share of O2 dissociated per pulse is
  reported so the reader can judge when that matters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from scipy import constants as codata
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

from plasma_twin.reference.loaders import load_cross_sections, load_itikawa_h2o, load_stage2_constants
from plasma_twin.stage1.eedf import EEDF, MAXWELLIAN_SHAPE
from plasma_twin.stage1.gas_flow import ATOMS_PER_S_PER_SCCM
from plasma_twin.stage1.rates import (_SPEED, _WEIGHTS, ELECTRON_MASS_KG, ENERGY_GRID_EV, MOLECULE_MASS_KG, TABLE_TE_EV,
                                      _on_grid)
from plasma_twin.stage2.pulse import PulseSettings

E, K_B, N_A = codata.e, codata.k, codata.N_A
ATM_PA = 101325.0
WATER_MASS_KG = 18.0153e-3 / N_A  # NIST WebBook molar mass (stage2_constants.csv: water_molar_mass)
# O3 molar mass from the same IUPAC O2 value Stage 1 uses (rates.MOLECULE_MASS_KG): 1.5 x 31.998 g/mol.
O3_MOLAR_MASS_G = 1.5 * MOLECULE_MASS_KG["O2"] / codata.atomic_mass
SPECIES = ("O", "O1D", "O3", "OH", "H", "HO2", "H2O2", "O2", "H2O", "H2")  # H2 from H + HO2, kept so H atoms balance
# Above this share of O2 dissociated in one pulse, O + O + M (not in the reaction set) starts to matter.
DISSOCIATION_WARNING = 0.10


class BubbleModelError(RuntimeError):
    """The bubble model cannot give an answer for these settings."""


# ------------------------------------------------------------------------------------ water vapour
def water_vapour_pressure_pa(temperature_k: float) -> float:
    """Saturated vapour pressure of water: NIST WebBook Antoine coefficients (Bridgeman and Aldrich 1964)."""
    c = load_stage2_constants()
    band = "273_303" if temperature_k <= 303.0 else "304_333"
    if not 273.0 <= temperature_k <= 333.0:
        raise BubbleModelError(f"water temperature {temperature_k:.1f} K is outside the Antoine range 273-333 K")
    a, b, cc = c[f"antoine_water_A_{band}"], c[f"antoine_water_B_{band}"], c[f"antoine_water_C_{band}"]
    return 1e5 * 10 ** (a - b / (temperature_k + cc))


# ------------------------------------------------------------------------------------ electron rates
class ElectronRates:
    """Maxwellian rate coefficients versus T_e for named cross-section columns (same method as Stage 1)."""

    def __init__(self, columns: dict[str, np.ndarray]) -> None:
        f = np.array([EEDF(te, MAXWELLIAN_SHAPE)(ENERGY_GRID_EV) for te in TABLE_TE_EV])
        kernel = _WEIGHTS * _SPEED
        log_te = np.log(TABLE_TE_EV)
        self._splines = {name: CubicSpline(log_te, np.log(np.maximum(f @ (kernel * sigma), 1e-300)))
                         for name, sigma in columns.items()}

    def k(self, name: str, te_ev: float) -> float:
        if not TABLE_TE_EV[0] <= te_ev <= TABLE_TE_EV[-1]:
            raise BubbleModelError(f"T_e = {te_ev} eV is outside the rate table")
        return float(np.exp(self._splines[name](np.log(te_ev))))


def _one(sections, process_type: str, product: str | None = None, description: str | None = None):
    found = [s for s in sections if s.process_type == process_type and (product is None or s.product == product)
             and (description is None or description in s.description or description in " ".join(s.comments))]
    if len(found) != 1:
        raise BubbleModelError(f"expected one {process_type} {product or ''} {description or ''} process, found {len(found)}")
    return found[0]


@lru_cache(maxsize=2)
def o2_rates() -> tuple[ElectronRates, float]:
    """O2 (Biagi): ionization, dissociative attachment, the two dissociative states, and energy loss."""
    sections = load_cross_sections("O2")
    ionization = _one(sections, "IONIZATION")
    elastic = _one(sections, "ELASTIC")
    attachment = _one(sections, "ATTACHMENT", "O^- + O")
    excitations = [s for s in sections if s.process_type == "EXCITATION"]
    states = {s.product: s for s in excitations}
    columns = {
        "ionization": _on_grid(ionization),
        "attachment": _on_grid(attachment),
        "dissociation_a3": _on_grid(states["O2( EXC A3 DISOC)"]),
        "dissociation_b3": _on_grid(states["O2( EXC B3 DISOC)"]),
        "excitation_energy": sum(s.threshold_ev * _on_grid(s) for s in excitations),
        "elastic_energy": 2 * ELECTRON_MASS_KG / MOLECULE_MASS_KG["O2"] * ENERGY_GRID_EV * _on_grid(elastic),
        "attachment_energy": ENERGY_GRID_EV * _on_grid(attachment),
    }
    return ElectronRates(columns), ionization.threshold_ev


# Itikawa emission cross-sections used by the underwater spectrum (Phase 7, uw_oes.py).
H2O_EMISSIONS = {"h_alpha": "H (Balmar alpha 3-2)", "o_777": "O 777 .4 nm", "o_844": "O 844.7 nm", "oh_a": "OH(A)"}


@lru_cache(maxsize=2)
def h2o_rates() -> tuple[ElectronRates, float, float]:
    """H2O (Itikawa): total ionization, attachment, OH(X) dissociation, energy loss and emission columns."""
    sections = load_itikawa_h2o()
    ionization = _one(sections, "IONIZATION", "H2O^+", "Total Ionization")
    momentum = _one(sections, "ELASTIC", None, "Momentum transfer")
    attachments = [s for s in sections if s.process_type == "ATTACHMENT"]
    oh_x = _one(sections, "EXCITATION", "OH (X)")
    rotation = [s for s in sections if s.process_type == "EXCITATION" and s.product.startswith("H2O(rot") and s.threshold_ev > 0]
    vibration = [s for s in sections if s.process_type == "EXCITATION" and s.product.startswith("H2O(v")]
    if len(attachments) != 3 or len(rotation) != 3 or len(vibration) != 2:
        raise BubbleModelError("the Itikawa H2O file does not hold the expected processes")
    oh_x_energy = float(oh_x.energy_ev[0])  # first tabulated energy: the file gives no threshold
    columns = {
        "ionization": _on_grid(ionization),
        "attachment": sum(_on_grid(s) for s in attachments),
        "oh_x": _on_grid(oh_x),
        "excitation_energy": sum(s.threshold_ev * _on_grid(s) for s in rotation + vibration) + oh_x_energy * _on_grid(oh_x),
        "elastic_energy": 2 * ELECTRON_MASS_KG / WATER_MASS_KG * ENERGY_GRID_EV * _on_grid(momentum),
        "attachment_energy": ENERGY_GRID_EV * sum(_on_grid(s) for s in attachments),
    }
    for key, product in H2O_EMISSIONS.items():
        columns[key] = _on_grid(_one(sections, "EXCITATION", product))
    return ElectronRates(columns), ionization.threshold_ev, oh_x_energy


# ------------------------------------------------------------------------------------ results
@dataclass(frozen=True)
class BubbleInputs:
    pulse: PulseSettings
    water_temperature_c: float
    gap_mm: float
    o2_flow_sccm: float
    with_water_vapour: bool = True
    # Share of the average electrical power that reaches the gas inside the bubbles. Not measured for this
    # device: see default_power_share() and BUILD_STEPS.md, Phase 7 (changed while building).
    power_share: float = 1.0


@dataclass(frozen=True)
class BubbleResult:
    inputs: BubbleInputs
    gas_temperature_k: float
    gas_density_m3: float
    water_fraction: float  # mole fraction of H2O in the bubble gas
    te_ev: float
    ne_m3: float  # in the assumed streamer channel, during the pulse
    channel_diameter_m: float
    energy_per_electron_collision_ev_m3_s: float  # W: power = e n_e n_g W V
    yields_per_j: dict[str, float]  # radicals made per joule: O, O1D, OH, H
    energy_shares: dict[str, float]  # where the pulse energy goes
    dissociated_o2_fraction: float  # share of the O2 in one gas packet dissociated by one pulse
    production_mol_s: dict[str, float]  # O3, H2O2 and OH leaving the gas each second
    ozone_yield_g_per_kwh: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ------------------------------------------------------------------------------------ T_e and branching
def solve_te(water_fraction: float) -> float:
    """T_e at which ionization balances dissociative attachment in the bubble gas."""
    o2, _ = o2_rates()
    h2o, _, _ = h2o_rates()
    x_o2 = 1.0 - water_fraction

    def net(te: float) -> float:
        gain = x_o2 * o2.k("ionization", te) + water_fraction * h2o.k("ionization", te)
        loss = x_o2 * o2.k("attachment", te) + water_fraction * h2o.k("attachment", te)
        return np.log(gain / loss)

    low, high = float(TABLE_TE_EV[0]), float(TABLE_TE_EV[-1])
    if net(low) > 0 or net(high) < 0:
        raise BubbleModelError("ionization never balances attachment in the rate-table range")
    return float(brentq(net, low, high, xtol=1e-6))


def branching(te_ev: float, water_fraction: float) -> tuple[float, dict[str, float], dict[str, float]]:
    """W (eV m^3/s per n_e n_g), radicals per joule, and the share of energy in each channel."""
    o2, eps_o2 = o2_rates()
    h2o, eps_h2o, _ = h2o_rates()
    x_o2, x_w = 1.0 - water_fraction, water_fraction
    channels = {
        "O2 ionization": x_o2 * eps_o2 * o2.k("ionization", te_ev),
        "O2 excitation and dissociation": x_o2 * o2.k("excitation_energy", te_ev),
        "O2 elastic": x_o2 * o2.k("elastic_energy", te_ev),
        "O2 attachment": x_o2 * o2.k("attachment_energy", te_ev),
        "H2O ionization": x_w * eps_h2o * h2o.k("ionization", te_ev),
        "H2O excitation and dissociation": x_w * h2o.k("excitation_energy", te_ev),
        "H2O elastic": x_w * h2o.k("elastic_energy", te_ev),
        "H2O attachment": x_w * h2o.k("attachment_energy", te_ev),
    }
    w = sum(channels.values())
    per_joule = 1.0 / (E * w)  # electron-gas collisions per joule, per unit k
    yields = {
        "O": per_joule * x_o2 * (2 * o2.k("dissociation_a3", te_ev) + o2.k("dissociation_b3", te_ev) + o2.k("attachment", te_ev)),
        "O1D": per_joule * x_o2 * o2.k("dissociation_b3", te_ev),
        "OH": per_joule * x_w * h2o.k("oh_x", te_ev),
        "H": per_joule * x_w * h2o.k("oh_x", te_ev),
    }
    return w, yields, {k: v / w for k, v in channels.items()}


# ------------------------------------------------------------------------------------ afterglow chemistry
def _rate_constants(t: float, m: float) -> dict[str, float]:
    """JPL 19-5 rate constants at gas temperature t (K) and total density m (m^-3), in m^3/s (m^6/s)."""
    c = load_stage2_constants()

    def arr(name: str) -> float:
        return c[f"{name}_A"] * np.exp(-c[f"{name}_E_R"] / t) * 1e-6

    def falloff(name: str, has_kinf: bool = True) -> float:
        k0 = c[f"{name}_k0_298"] * (t / 298.0) ** (-c[f"{name}_n"]) * 1e-12 * m  # effective two-body, m^3/s
        if not has_kinf:
            return k0
        kinf = c[f"{name}_kinf_298"] * (t / 298.0) ** (-c[f"{name}_m"]) * 1e-6
        ratio = k0 / kinf
        return k0 / (1 + ratio) * c["jpl_falloff_fc"] ** (1 / (1 + np.log10(ratio) ** 2))

    return {
        "o_o2": falloff("jpl_o_o2", has_kinf=False), "o_o3": arr("jpl_o_o3"), "o1d_o2": arr("jpl_o1d_o2"),
        "o1d_h2o": arr("jpl_o1d_h2o"), "o_oh": arr("jpl_o_oh"), "o_ho2": arr("jpl_o_ho2"), "o_h2o2": arr("jpl_o_h2o2"),
        "h_o3": arr("jpl_h_o3"), "h_ho2_2oh": c["jpl_h_ho2_2oh_A"] * 1e-6, "h_ho2_o_h2o": c["jpl_h_ho2_o_h2o_A"] * 1e-6,
        "h_ho2_h2_o2": c["jpl_h_ho2_h2_o2_A"] * 1e-6, "oh_o3": arr("jpl_oh_o3"), "oh_oh_h2o_o": c["jpl_oh_oh_h2o_o_A"] * 1e-6,
        "oh_oh_m": falloff("jpl_oh_oh"), "oh_ho2": arr("jpl_oh_ho2"), "oh_h2o2": c["jpl_oh_h2o2_k"] * 1e-6,
        "ho2_o3": arr("jpl_ho2_o3"),
        "ho2_ho2": arr("jpl_ho2_ho2") + c["jpl_ho2_ho2_M_A"] * np.exp(-c["jpl_ho2_ho2_M_E_R"] / t) * 1e-12 * m,
        "h_o2": falloff("jpl_h_o2"),
    }


def afterglow(initial: dict[str, float], temperature_k: float, duration_s: float) -> dict[str, float]:
    """Densities (m^-3) after the radicals of one pulse react for `duration_s` at fixed temperature."""
    index = {s: i for i, s in enumerate(SPECIES)}
    m = initial["O2"] + initial["H2O"]
    k = _rate_constants(temperature_k, m)
    # (rate key, reactants, products)
    reactions = (
        ("o_o2", ("O", "O2"), ("O3",)), ("o_o3", ("O", "O3"), ("O2", "O2")), ("o1d_o2", ("O1D", "O2"), ("O", "O2")),
        ("o1d_h2o", ("O1D", "H2O"), ("OH", "OH")), ("o_oh", ("O", "OH"), ("O2", "H")), ("o_ho2", ("O", "HO2"), ("OH", "O2")),
        ("o_h2o2", ("O", "H2O2"), ("OH", "HO2")), ("h_o3", ("H", "O3"), ("OH", "O2")), ("h_ho2_2oh", ("H", "HO2"), ("OH", "OH")),
        ("h_ho2_o_h2o", ("H", "HO2"), ("O", "H2O")), ("h_ho2_h2_o2", ("H", "HO2"), ("H2", "O2")), ("oh_o3", ("OH", "O3"), ("HO2", "O2")),
        ("oh_oh_h2o_o", ("OH", "OH"), ("H2O", "O")), ("oh_oh_m", ("OH", "OH"), ("H2O2",)), ("oh_ho2", ("OH", "HO2"), ("H2O", "O2")),
        ("oh_h2o2", ("OH", "H2O2"), ("H2O", "HO2")), ("ho2_o3", ("HO2", "O3"), ("OH", "O2", "O2")),
        ("ho2_ho2", ("HO2", "HO2"), ("H2O2", "O2")), ("h_o2", ("H", "O2"), ("HO2",)),
    )
    plan = [(k[key], [index[r] for r in reactants], [index[p] for p in products]) for key, reactants, products in reactions]
    scale = max(initial.values())

    def rhs(_, y):
        n = y * scale
        dn = np.zeros_like(n)
        for rate, reactants, products in plan:
            r = rate * n[reactants[0]] * n[reactants[1]]
            for i in reactants:
                dn[i] -= r
            for i in products:
                dn[i] += r
        return dn / scale

    y0 = np.array([initial.get(s, 0.0) for s in SPECIES]) / scale
    solution = solve_ivp(rhs, (0.0, duration_s), y0, method="LSODA", rtol=1e-7, atol=1e-16)
    if not solution.success:
        raise BubbleModelError(f"afterglow chemistry failed: {solution.message}")
    return {s: float(max(solution.y[index[s], -1], 0.0) * scale) for s in SPECIES}


# ------------------------------------------------------------------------------------ the model
def solve(inputs: BubbleInputs) -> BubbleResult:
    """From the electrical pulse to the O3, H2O2 and OH the bubbles carry into the water."""
    warnings = list(inputs.pulse.check())
    c = load_stage2_constants()
    t_gas = inputs.water_temperature_c + 273.15
    n_g = ATM_PA / (K_B * t_gas)
    x_w = min(water_vapour_pressure_pa(t_gas) / ATM_PA, 0.99) if inputs.with_water_vapour else 0.0

    te = solve_te(x_w)
    w, yields, shares = branching(te, x_w)

    # n_e in the assumed streamer channel (only used for the Stark width)
    diameter = c["streamer_p_dmin"] * 1e-3 / (ATM_PA / 1e5)
    volume = np.pi * diameter**2 / 4 * inputs.gap_mm * 1e-3
    gas_pulse_power = inputs.power_share * inputs.pulse.pulse_power_w
    ne = gas_pulse_power / (E * n_g * w * volume)  # w is in eV m^3/s, so e*w is in J m^3/s

    # Afterglow of one pulse in the gas that flowed past since the last one (plug flow)
    f = inputs.pulse.frequency_hz
    o2_per_s = inputs.o2_flow_sccm * ATOMS_PER_S_PER_SCCM
    molecules_per_packet = o2_per_s / f / (1.0 - x_w)
    packet_volume = molecules_per_packet / n_g
    gas_energy = inputs.power_share * inputs.pulse.energy_per_pulse_j
    radicals = {s: yields[s] * gas_energy / packet_volume for s in ("O", "O1D", "OH", "H")}
    n_o2, n_h2o = n_g * (1.0 - x_w), n_g * x_w
    dissociated = (radicals["O"] + radicals["O1D"]) / 2 / n_o2
    if dissociated > 1.0:
        scale = 1.0 / dissociated
        radicals = {s: v * scale for s, v in radicals.items()}
        warnings.append("one pulse would dissociate more O2 than flows past it; radical production is capped at the "
                        "O2 supply (the extra energy only heats the gas and water)")
        dissociated = 1.0
    elif dissociated > DISSOCIATION_WARNING * (1 + 1e-6):  # the default share sits exactly on the limit
        warnings.append(f"one pulse dissociates {dissociated:.0%} of the O2 that flows past; O + O + M recombination, "
                        "not in the reaction set, would then lower the ozone")
    start = dict(radicals, O2=n_o2 * (1.0 - dissociated), H2O=max(n_h2o - radicals["OH"], 0.0))
    end = afterglow(start, t_gas, 1.0 / f)
    production = {s: end[s] * packet_volume * f / N_A for s in ("O3", "H2O2", "OH")}
    ozone_g_per_kwh = production["O3"] * O3_MOLAR_MASS_G / (inputs.pulse.power_w / 1000.0) * 3600.0
    return BubbleResult(inputs, t_gas, n_g, x_w, te, ne, diameter, w, yields, shares, dissociated, production,
                        ozone_g_per_kwh, tuple(warnings))


def default_power_share() -> float:
    """The largest power share that splits at most 10 % of the O2 per pulse at the default operating point.

    Below the O2-supply cap the share of O2 split is proportional to the power share, so one run at
    share 1 (uncapped) gives it directly. This is a validity limit of the model, not a measurement.
    """
    from plasma_twin.config.loader import load_envelope
    env = load_envelope()["stage2"]
    inputs = BubbleInputs(PulseSettings.defaults(), float(env["water_temperature_c"]["default"]),
                          float(env["options"]["default_gap_mm"]), float(env["o2_flow_sccm"]["default"]))
    t_gas = inputs.water_temperature_c + 273.15
    n_g = ATM_PA / (K_B * t_gas)
    x_w = water_vapour_pressure_pa(t_gas) / ATM_PA
    _, yields, _ = branching(solve_te(x_w), x_w)
    split_per_share = (yields["O"] + yields["O1D"]) / 2 * inputs.pulse.power_w / (inputs.o2_flow_sccm * ATOMS_PER_S_PER_SCCM)
    return DISSOCIATION_WARNING / split_per_share
