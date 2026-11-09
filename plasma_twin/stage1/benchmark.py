"""Compare the argon global model with the published measurements in benchmarks.csv (ACC-1).

The rules were fixed in BUILD_STEPS.md (Phase 2, "Benchmark comparison rules") and committed with
the model before this comparison was first run, so nothing here was chosen after seeing a result.
"""
from __future__ import annotations

from dataclasses import dataclass

from plasma_twin.config.loader import load_envelope
from plasma_twin.probe.retardation import probe_style_te
from plasma_twin.reference.loaders import load_benchmarks
from plasma_twin.stage1.eedf import SHAPES
from plasma_twin.stage1.global_model import Stage1Inputs, solve

# Saikia et al. (2018): asymmetric electrodes 8 cm and 10 cm across, 7.5 cm apart. The model is
# symmetric, so it uses the mean radius (4.5 cm), as the comparison rules state.
SAIKIA_RADIUS_M = (0.08 + 0.10) / 4
SAIKIA_GAP_M = 0.075
GATE_POINTS = ("saikia2018_p100", "saikia2018_p200", "saikia2018_p300")


@dataclass(frozen=True)
class Comparison:
    point: str
    quantity: str  # "n_e" or "T_e"
    pressure_mbar: float
    power_w: float
    measured: float
    modelled: float
    in_gate: bool  # one of the three pre-registered points

    @property
    def difference(self) -> float:
        """(model - measured) / measured."""
        return (self.modelled - self.measured) / self.measured

    @property
    def within_tolerance(self) -> bool:
        """True when the model is within the 30 % tolerance of the measurement (ACC-1)."""
        return abs(self.difference) <= load_envelope()["validation"]["agreement_tolerance_fraction"]


def compare(eedf: str = "Druyvesteyn", edge_length: str = "sheath", te_definition: str = "probe",
            probe_window: str = "full") -> list[Comparison]:
    """Run the model at every Saikia point and pair each result with the measurement.

    te_definition "probe" (run 3 onwards): the model T_e is converted to what Saikia et al.'s slope
    method would read from the model's EEDF (probe/retardation.py). "mean_energy" is the definition
    used in runs 1 and 2, kept so those runs can be reproduced.
    """
    if te_definition not in ("probe", "mean_energy"):
        raise ValueError("te_definition must be 'probe' or 'mean_energy'")
    rows = [r for r in load_benchmarks() if r["id"].startswith("saikia2018_")]
    gas_temperature = load_envelope()["stage1"]["fixed"]["gas_temperature_k"]
    out: list[Comparison] = []
    for point in sorted({r["id"].rsplit("_", 2)[0] for r in rows}):
        measured = {r["quantity"]: r for r in rows if r["id"].startswith(point + "_")}
        any_row = next(iter(measured.values()))
        inputs = Stage1Inputs(
            rf_power_w=float(any_row["power_w"]), pressure_mbar=float(any_row["pressure_mbar"]),
            electrode_radius_m=SAIKIA_RADIUS_M, electrode_gap_m=SAIKIA_GAP_M, eedf=eedf,
            gas_temperature_k=gas_temperature, edge_length=edge_length,
        )
        # Points outside our envelope are still run, for information; the envelope check is off
        # only here, and only those inside it can count for the exit gate.
        result = solve(inputs, check_envelope=False)
        te = (probe_style_te(result.te_ev, SHAPES[eedf], probe_window) if te_definition == "probe"
              else result.te_ev)
        modelled = {"n_e": result.ne_center_m3, "T_e": te}
        for quantity, row in measured.items():
            out.append(Comparison(point, quantity, inputs.pressure_mbar, inputs.rf_power_w,
                                  float(row["value"]), modelled[quantity], point in GATE_POINTS))
    return out
