"""Application services for the Stage 1 screens (Phase 6).

WHY A SEPARATE LAYER: the screens (app/) must contain no physics, and the physics (plasma_twin/)
must never import Streamlit. This layer sits between them. It turns the values a user types (in
cm, mbar, %) into model inputs (in SI), checks them against the envelope with a message per field
(FR2.10), runs the model and the virtual instruments, and turns results into plain JSON that can be
saved, reloaded and exported. Because nothing here depends on Streamlit, every rule can be unit-tested.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from plasma_twin.config.loader import load_envelope

PRESETS_PATH = Path(__file__).resolve().parents[1] / "config" / "presets.toml"
MIXTURES = ("Ar", "Ar+N2", "Ar+O2", "Ar+N2+O2")


# ------------------------------------------------------------------------------ the screen's configuration
def default_config() -> dict[str, Any]:
    """Every field of the chamber screen (M2) at its envelope default, in the screen's units."""
    env = load_envelope()["stage1"]
    geometry = env["geometry_cm"]
    return {
        "rf_power_w": float(env["rf_power_w"]["default"]),
        "pressure_mbar": float(env["pressure_mbar"]["default"]),
        "ar_flow_sccm": float(env["ar_flow_sccm"]["default"]),
        "mixture": env["options"]["gas_mixtures"][0],
        "n2_percent": float(env["admixture_percent_of_ar"]["default"]),
        "o2_percent": float(env["admixture_percent_of_ar"]["default"]),
        "chamber_diameter_cm": float(geometry["chamber_diameter"]),
        "chamber_height_cm": float(geometry["chamber_height"]),
        "electrode_diameter_cm": float(geometry["electrode_diameter"]),
        "electrode_gap_cm": float(geometry["electrode_gap"]),
        "eedf": env["options"]["eedf"][0],
        "spatial": env["options"]["spatial"][0],
    }


def load_presets() -> dict[str, dict[str, Any]]:
    """Named example experiments, each a full configuration plus a title and description."""
    with open(PRESETS_PATH, "rb") as handle:
        raw = tomllib.load(handle)
    presets = {}
    for key, values in raw.items():
        config = default_config()
        config.update({k: v for k, v in values.items() if k not in ("title", "description")})
        presets[key] = {"title": values["title"], "description": values["description"], "config": config}
    return presets


def pressure_units(mbar: float) -> dict[str, float]:
    """FR2.2: the same pressure in Pa and mTorr (1 mbar = 100 Pa; 1 Torr = 101325/760 Pa)."""
    pascal = mbar * 100.0
    return {"Pa": pascal, "mTorr": pascal / (101325.0 / 760.0) * 1000.0}


def validate_config(config: dict[str, Any]) -> dict[str, str]:
    """FR2.10: a message for every field that is out of range or impossible. Empty means valid."""
    env = load_envelope()["stage1"]
    problems: dict[str, str] = {}
    for field, key, unit in (("rf_power_w", "rf_power_w", "W"), ("pressure_mbar", "pressure_mbar", "mbar"),
                             ("ar_flow_sccm", "ar_flow_sccm", "sccm")):
        low, high = env[key]["min"], env[key]["max"]
        if not low <= config[field] <= high:
            problems[field] = f"must be between {low} and {high} {unit} (envelope)"
    mix = env["admixture_percent_of_ar"]
    if config["mixture"] not in MIXTURES:
        problems["mixture"] = f"must be one of {', '.join(MIXTURES)}"
    for gas, field in (("N2", "n2_percent"), ("O2", "o2_percent")):
        if gas in config["mixture"] and not mix["min"] <= config[field] <= mix["max"]:
            problems[field] = f"must be between {mix['min']} and {mix['max']} % of the argon flow (envelope)"
    for field in ("chamber_diameter_cm", "chamber_height_cm", "electrode_diameter_cm", "electrode_gap_cm"):
        if not config[field] > 0:
            problems[field] = "must be greater than zero"
    if config["electrode_diameter_cm"] >= config["chamber_diameter_cm"]:
        problems["electrode_diameter_cm"] = "the electrodes must be smaller than the chamber"
    if config["electrode_gap_cm"] >= config["chamber_height_cm"]:
        problems["electrode_gap_cm"] = "the electrode gap must be smaller than the chamber height"
    if config["eedf"] not in env["options"]["eedf"]:
        problems["eedf"] = f"must be one of {', '.join(env['options']['eedf'])}"
    if config["spatial"] not in env["options"]["spatial"]:
        problems["spatial"] = f"must be one of {', '.join(env['options']['spatial'])}"
    return problems


def admixture_flows_sccm(config: dict[str, Any]) -> dict[str, float]:
    """FR2.5: each admixture as a flow in sccm (a percentage of the argon flow); 0 for gases not in the mixture."""
    return {gas: config["ar_flow_sccm"] * config[field] / 100 if gas in config["mixture"] else 0.0
            for gas, field in (("N2", "n2_percent"), ("O2", "o2_percent"))}


def regime_notes(config: dict[str, Any]) -> list[str]:
    """FR2.10: the model regime of a configuration, before it is run.

    The ion mean free path uses the model's own numbers (ion-neutral cross-section 1e-18 m^2, gas at the
    fixed Stage 1 temperature). Whether the sheath is collisional needs the sheath width, which only a
    run gives, so the Results screen checks lambda_i < s_m (sheath_regime).
    """
    from plasma_twin.stage1.global_model import ION_NEUTRAL_CROSS_SECTION_M2, K_B
    temperature = load_envelope()["stage1"]["fixed"]["gas_temperature_k"]
    density = config["pressure_mbar"] * 100.0 / (K_B * temperature)
    mean_free_path_mm = 1e3 / (density * ION_NEUTRAL_CROSS_SECTION_M2)
    notes = [f"ion mean free path λ_i = {mean_free_path_mm:.3f} mm, against an electrode gap of "
             f"{10 * config['electrode_gap_cm']:.0f} mm: diffusion-limited transport, and the model uses the "
             "collisional-sheath law (Lieberman 2015 high-pressure capacitive model)"]
    if "O2" in config["mixture"]:
        notes.append("O₂ makes the plasma electronegative: probe and OES values will be flagged approximate (LI-4)")
    return notes


def sheath_regime(result) -> tuple[bool, str]:
    """FR2.10 after a run: the sheath is collisional when the ion mean free path is shorter than the sheath."""
    ratio = result.ion_mean_free_path_m / result.sheath_width_m
    if ratio < 1:
        return True, (f"collisional sheath: λ_i / s_m = {ratio:.2f} < 1, so the collisional Child law the "
                      "model uses applies")
    return False, (f"λ_i / s_m = {ratio:.2f} ≥ 1: the sheath is not collisional, outside the regime of the "
                   "model's sheath law; treat the sheath values with care")


def config_hash(config: dict[str, Any]) -> str:
    """SHA-256 of the configuration written as sorted JSON: the cache key and the stored config_hash (E2)."""
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()


def to_inputs(config: dict[str, Any]):
    """The model's inputs (SI) for a valid configuration."""
    from plasma_twin.stage1.global_model import default_inputs
    return default_inputs(
        rf_power_w=config["rf_power_w"], pressure_mbar=config["pressure_mbar"], ar_flow_sccm=config["ar_flow_sccm"],
        n2_percent_of_ar=config["n2_percent"] if "N2" in config["mixture"] else 0.0,
        o2_percent_of_ar=config["o2_percent"] if "O2" in config["mixture"] else 0.0,
        chamber_diameter_m=config["chamber_diameter_cm"] / 100, chamber_height_m=config["chamber_height_cm"] / 100,
        electrode_radius_m=config["electrode_diameter_cm"] / 200, electrode_gap_m=config["electrode_gap_cm"] / 100,
        eedf=config["eedf"],
    )


# ------------------------------------------------------------------------------ running and summarising
def run(config: dict[str, Any]):
    """Run the global model for a configuration (raises if the configuration is invalid)."""
    from plasma_twin.stage1.global_model import InputOutOfRange, solve
    problems = validate_config(config)
    if problems:
        raise InputOutOfRange("; ".join(f"{k}: {v}" for k, v in problems.items()))
    return solve(to_inputs(config))


def _plain(value: Any) -> Any:
    """Turn numpy numbers and arrays into plain Python, so results can be stored as JSON."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    return value


def summarise(result) -> dict[str, Any]:
    """The plain-JSON record of a run: what M3 shows, what a session stores, what CSV export writes."""
    from plasma_twin.stage1.profile1d import axial_profile
    x = result.inputs
    volume_mean = axial_profile(result).bulk_average_m3
    densities = {"Ar (ground)": result.mixture.get("argon_density_m3", result.gas_density_m3),
                 "Ar metastables (1s5, 1s3, lumped)": result.metastable_density_m3,
                 "Ar resonant (1s4, 1s2, lumped)": result.resonant_density_m3,
                 "Ar 4p (lumped)": result.p4_density_m3}
    for ion, density in result.mixture.get("ion_densities_m3", {"Ar+": result.ne_center_m3}).items():
        densities[ion] = density
    for label, key in (("O-", "negative_ion_density_m3"), ("O atoms", "o_atom_density_m3"),
                       ("O2(a1Delta)", "o2a_density_m3"), ("N2", "n2_density_m3"), ("O2", "o2_density_m3")):
        if result.mixture.get(key):
            densities[label] = result.mixture[key]
    return _plain({
        "te_ev": result.te_ev, "ne_center_m3": result.ne_center_m3, "ne_volume_mean_m3": volume_mean,
        "gas_temperature_k": x.gas_temperature_k, "ion_flux_electrode_m2_s": result.ion_flux_electrode_m2_s,
        "sheath_width_m": result.sheath_width_m, "rf_voltage_amplitude_v": result.rf_voltage_amplitude_v,
        "dc_sheath_voltage_v": result.dc_sheath_voltage_v, "absorbed_power_w": result.absorbed_power_w,
        "densities_m3": densities, "loss_shares_percent": result.shares_percent("losses"),
        "heating_shares_percent": result.shares_percent("heating"), "ionization_routes": result.ionization_routes,
        "electronegativity": result.mixture.get("electronegativity", 0.0),
        "max_residual": max(result.residuals.values()),
    })


def assumptions(result) -> list[str]:
    """FR3.6: the regime assumptions of the run, written from the settings actually used."""
    x = result.inputs
    out = [
        f"0D global model; {x.eedf} electron energy distribution",
        "collisional RF sheath (Lieberman 2015 high-pressure capacitive model); edge factors with length 2 s_m",
        f"ion mean free path {1e3 * result.ion_mean_free_path_m:.3f} mm: diffusion-limited transport to the walls",
        "argon excited atoms (1s, 4p) and two-step ionization included",
        "gas temperature from a conduction heat balance" if x.gas_heating else f"gas temperature fixed at {x.gas_temperature_k:.0f} K",
        "RF power taken as power absorbed by the plasma (SUPERVISOR_QUESTIONS.md, Q3)",
        "symmetric parallel-plate electrodes; no secondary-electron (gamma-mode) heating",
    ]
    if x.o2_percent_of_ar:
        out.append("O2 present: electronegative transport (Kemaneci et al. 2016, sheath-edge electronegativity)")
    return out


def export_header(session_id: str | None, **extra: Any) -> str:
    """FR3.10, FR4.7: '#' comment lines naming the session and software version (and any settings given)."""
    from plasma_twin import __version__
    lines = [f"# session: {session_id or 'not saved'}", f"# software version: {__version__}"]
    lines += [f"# {key}: {value}" for key, value in extra.items()]
    return "\n".join(lines) + "\n"


def results_csv(summary: dict[str, Any], config: dict[str, Any], session_id: str | None = None) -> str:
    """FR3.10: a header with session ID and software version, then one quantity per row with its unit,
    after the configuration it came from."""
    buffer = io.StringIO()
    buffer.write(export_header(session_id))
    writer = csv.writer(buffer)
    writer.writerow(["section", "quantity", "value", "unit"])
    for key, value in config.items():
        writer.writerow(["configuration", key, value, ""])
    units = {"te_ev": "eV", "ne_center_m3": "m^-3", "ne_volume_mean_m3": "m^-3", "gas_temperature_k": "K",
             "ion_flux_electrode_m2_s": "m^-2 s^-1", "sheath_width_m": "m", "rf_voltage_amplitude_v": "V",
             "dc_sheath_voltage_v": "V", "absorbed_power_w": "W", "electronegativity": "", "max_residual": ""}
    for key, unit in units.items():
        writer.writerow(["result", key, summary[key], unit])
    for name, value in summary["densities_m3"].items():
        writer.writerow(["density", name, value, "m^-3"])
    for name, value in summary["loss_shares_percent"].items():
        writer.writerow(["power loss share", name, value, "%"])
    return buffer.getvalue()


def downsample_peaks(x: np.ndarray, y: np.ndarray, bins: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a long trace for drawing, keeping each bin's highest point so no line peak disappears."""
    if len(x) <= 2 * bins:
        return x, y
    edges = np.linspace(0, len(x), bins + 1).astype(int)
    keep = np.array([lo + int(np.argmax(y[lo:hi])) for lo, hi in zip(edges[:-1], edges[1:]) if hi > lo])
    return x[keep], y[keep]


def inputs_record(result) -> dict[str, Any]:
    """The model inputs of a run, as plain JSON (stored with each session)."""
    return _plain(asdict(result.inputs))
