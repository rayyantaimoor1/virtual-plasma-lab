"""Application services for the Stage 2 screens (M8, M9): Phase 7.

Same layering as Stage 1 (services/stage1.py): the screens only display; this layer turns screen
values into model inputs, checks them field by field (FR8.x, E5), runs pulse -> bubble plasma ->
water -> Hom model -> underwater OES, and turns the results into plain JSON for sessions and CSV.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from plasma_twin.config.loader import load_envelope
from plasma_twin.oes.spectrum import SpectrometerSettings
from plasma_twin.stage2.bubble_model import BubbleInputs, BubbleResult, solve
from plasma_twin.stage2.hom import ORGANISMS_WITH_PARAMETERS, SurvivalResult, survival
from plasma_twin.stage2.liquid import LiquidResult, WaterInputs, solve_liquid
from plasma_twin.stage2.pulse import PulseBlocked, PulseSettings
from plasma_twin.stage2.uw_oes import StarkResult, StarkUnavailable, UnderwaterSpectrum, build, stark_density

# The H-alpha line gets its own acquisition window, as the N2 band does in Stage 1: on the full range the
# spectrum's peak (OH at 309 nm) sets the noise and buries H-alpha.
H_ALPHA_WINDOW_NM = (650.0, 663.0)
WASTE_TYPES = ("Municipal waste water", "Distilled water")


def default_config() -> dict[str, Any]:
    """Every Stage 2 field at its envelope default, in the screen's units."""
    env = load_envelope()["stage2"]
    d = env["defaults"]
    return {
        "voltage_kv": float(env["pulse_voltage_kv"]["default"]), "frequency_khz": float(env["pulse_frequency_khz"]["default"]),
        "width_us": float(env["pulse_rules"]["default_width_us"]), "power_w": float(env["average_power_w"]["default"]),
        "gap_mm": float(env["options"]["default_gap_mm"]), "o2_flow_sccm": float(env["o2_flow_sccm"]["default"]),
        "bubble_gas": env["options"]["bubble_gas"][0], "power_share": float(env["power_share"]["default"]),
        "water_volume_ml": float(env["water_volume_ml"]["default"]), "water_ph": float(env["water_ph"]["default"]),
        "water_temperature_c": float(env["water_temperature_c"]["default"]),
        "conductivity_us_cm": float(d["conductivity_us_per_cm"]), "cod_mg_l": float(d["cod_mg_per_l"]),
        "waste_type": WASTE_TYPES[0], "organism": env["options"]["organisms"][0],
        "initial_count_cfu_ml": float(d["initial_count_cfu_per_ml"]),
        "treatment_time_min": float(env["treatment_time_min"]["default"]),
    }


def pulse_of(config: dict[str, Any]) -> PulseSettings:
    """The pulsed-DC supply settings of a configuration."""
    return PulseSettings(config["voltage_kv"], config["frequency_khz"], config["width_us"], config["power_w"])


def validate_config(config: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Problems by field (the run is blocked) and warnings (it may run). FR8.x, E5."""
    env = load_envelope()["stage2"]
    problems: dict[str, str] = {}
    warnings: list[str] = []
    try:
        warnings += pulse_of(config).check()
    except PulseBlocked as problem:
        problems["pulse"] = str(problem)
    for field, key, unit in (("o2_flow_sccm", "o2_flow_sccm", "sccm"), ("water_volume_ml", "water_volume_ml", "mL"),
                             ("water_ph", "water_ph", ""), ("water_temperature_c", "water_temperature_c", "°C"),
                             ("treatment_time_min", "treatment_time_min", "min"), ("power_share", "power_share", "")):
        low, high = env[key]["min"], env[key]["max"]
        if not low <= config[field] <= high:
            problems[field] = f"must be between {low} and {high} {unit} (envelope)".replace("  ", " ")
    if config["gap_mm"] not in env["options"]["electrode_gap_mm"]:
        problems["gap_mm"] = f"must be one of {env['options']['electrode_gap_mm']} mm"
    if config["bubble_gas"] not in env["options"]["bubble_gas"]:
        problems["bubble_gas"] = f"must be one of {env['options']['bubble_gas']}"
    if config["organism"] not in ORGANISMS_WITH_PARAMETERS:
        problems["organism"] = "no published Hom parameters for this organism are used yet (LI-6)"
    if not config["initial_count_cfu_ml"] > 0:
        problems["initial_count_cfu_ml"] = "must be greater than zero"
    for field in ("conductivity_us_cm", "cod_mg_l"):
        if config[field] < 0:
            problems[field] = "cannot be negative"
    return problems, warnings


def config_hash(config: dict[str, Any]) -> str:
    """A hash of the configuration, used to cache and identify runs (PER-1)."""
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Stage2Run:
    config: dict[str, Any]
    bubble: BubbleResult
    liquid: LiquidResult
    survival: SurvivalResult
    spectrum: UnderwaterSpectrum
    stark: StarkResult | None
    stark_reason: str | None


def bubble_inputs(config: dict[str, Any], power_share: float | None = None) -> BubbleInputs:
    """The bubble-plasma model's inputs for a configuration (optionally with another power share)."""
    return BubbleInputs(pulse_of(config), config["water_temperature_c"], config["gap_mm"], config["o2_flow_sccm"],
                        config["bubble_gas"] == "O2 + water vapour",
                        config["power_share"] if power_share is None else power_share)


def water_inputs(config: dict[str, Any]) -> WaterInputs:
    """The water model's inputs for a configuration."""
    return WaterInputs(config["water_volume_ml"], config["water_ph"], config["water_temperature_c"],
                       config["conductivity_us_cm"], config["cod_mg_l"], config["treatment_time_min"])


def run(config: dict[str, Any], spectrometer: SpectrometerSettings | None = None) -> Stage2Run:
    """Pulse -> bubble plasma -> water -> survival -> underwater spectrum (raises if the configuration is invalid)."""
    problems, _ = validate_config(config)
    if problems:
        raise PulseBlocked("; ".join(f"{k}: {v}" for k, v in problems.items()))
    bubble = solve(bubble_inputs(config))
    liquid = solve_liquid(bubble, water_inputs(config))
    kill = survival(liquid.time_s, liquid.ozone_mg_l, liquid.ozone_ct_mg_s_l, config["organism"],
                    config["initial_count_cfu_ml"], config["water_volume_ml"], config["water_temperature_c"], config["power_w"])
    settings = spectrometer or SpectrometerSettings.defaults()
    spectrum = build(bubble, settings)
    stark, reason = None, None
    try:
        stark = stark_density(build(bubble, SpectrometerSettings(settings.fwhm_nm, *H_ALPHA_WINDOW_NM, settings.noise_percent,
                                                                 settings.seed)))
    except StarkUnavailable as problem:
        reason = str(problem)
    return Stage2Run(config, bubble, liquid, kill, spectrum, stark, reason)


def power_share_sensitivity(config: dict[str, Any], points: int = 9) -> list[dict[str, float]]:
    """Log reduction and dissolved ozone against the power share (the model's main uncertainty)."""
    env = load_envelope()["stage2"]["power_share"]
    rows = []
    for share in np.geomspace(env["min"], env["max"], points):
        bubble = solve(bubble_inputs(config, float(share)))
        liquid = solve_liquid(bubble, water_inputs(config))
        kill = survival(liquid.time_s, liquid.ozone_mg_l, liquid.ozone_ct_mg_s_l, config["organism"],
                        config["initial_count_cfu_ml"], config["water_volume_ml"], config["water_temperature_c"], config["power_w"])
        rows.append({"power_share": float(share), "log_reduction": kill.log_reduction, "ozone_mg_l": float(liquid.ozone_mg_l[-1]),
                     "o2_split": bubble.dissociated_o2_fraction})
    return rows


def summarise(result: Stage2Run) -> dict[str, Any]:
    """The headline numbers as plain JSON (sessions, CSV)."""
    b, w, s = result.bubble, result.liquid, result.survival
    return {
        "log_reduction": s.log_reduction, "log_reduction_capped": s.capped, "d_value_min": s.d_value_min,
        "energy_yield_log_per_kj_l": s.energy_yield_log_per_kj_l, "te_ev": b.te_ev, "ne_channel_m3": b.ne_m3,
        "ne_stark_m3": result.stark.ne_m3 if result.stark else None, "water_fraction": b.water_fraction,
        "o2_split_per_pulse": b.dissociated_o2_fraction, "ozone_yield_g_per_kwh": b.ozone_yield_g_per_kwh,
        "ozone_end_mg_l": float(w.ozone_mg_l[-1]), "h2o2_end_mmol_l": float(w.h2o2_mmol_l[-1]), "oh_end_mol_l": float(w.oh_mol_l[-1]),
        "temperature_before_c": w.temperature_before_c, "temperature_after_c": w.temperature_after_c,
        "ph_before": w.ph_before, "ph_after": w.ph_after, "conductivity_before_us_cm": w.conductivity_before_us_cm,
        "conductivity_after_us_cm": w.conductivity_after_us_cm, "orp_after_v": w.orp_after_v,
        "warnings": list(b.warnings) + list(s.flags) + list(w.notes),
    }


def results_csv(summary: dict[str, Any], config: dict[str, Any], run_result: Stage2Run, session_id: str | None = None) -> str:
    """FR9.6: header (session, version), configuration, headline results, then the time series."""
    from plasma_twin.services.stage1 import export_header
    buffer = io.StringIO()
    buffer.write(export_header(session_id))
    writer = csv.writer(buffer)
    writer.writerow(["section", "quantity", "value"])
    for key, value in config.items():
        writer.writerow(["configuration", key, value])
    for key, value in summary.items():
        if key != "warnings":
            writer.writerow(["result", key, value])
    for text in summary["warnings"]:
        writer.writerow(["note", "", text])
    writer.writerow([])
    writer.writerow(["time_s", "ozone_mg_l", "h2o2_mmol_l", "oh_mol_l", "log10_survival"])
    w, s = run_result.liquid, run_result.survival
    writer.writerows(zip(w.time_s, w.ozone_mg_l, w.h2o2_mmol_l, w.oh_mol_l, s.log_survival))
    return buffer.getvalue()
