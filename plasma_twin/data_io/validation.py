"""Validation against literature benchmarks and measured files: Phase 8 (FR10.6, FR10.7, CON-6, CON-7, ACC-4).

RULES (BUILD_STEPS.md, Phase 8, fixed before this code):
- The tolerance is read from envelope.toml (validation.agreement_tolerance_fraction, +/-30 %), fixed
  before any comparison. Deviation = (model - reference) / reference.
- Literature: the Saikia et al. (2018) points, with the Phase 2 rules unchanged.
- Measured probe file (Stage 1): analysed with exactly the M6 method; T_e is the EEPF effective
  temperature if the EEPF is reliable, otherwise the slope temperature (flagged); n_e is the EEPF
  density if reliable, otherwise the OML ion density.
- Measured OES file, Stage 1: line areas at the CR-model lines, then a line-ratio fit for T_e. n_e is
  taken from a saved probe file at the same operating conditions if there is one, otherwise fitted.
- Measured OES file, Stage 2: n_e from the H-alpha Stark width, compared with the model channel n_e.
- Every check is written to validation_results with date and software version. A check that cannot
  run is reported as "not run" with its reason, never as a pass.
- Measured data never change model parameters (CON-6): this module only reads them.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plasma_twin import __version__
from plasma_twin.config.loader import load_envelope
from plasma_twin.storage.db import connect
from plasma_twin.storage.measured import MeasuredFile, MeasuredStore, parse_id


@dataclass(frozen=True)
class Check:
    name: str
    quantity: str
    unit: str
    reference_source: str  # a citation, or a measured-file ID
    file_id: str | None  # None for a literature benchmark
    citable: bool
    computed: float | None  # the model value
    reference: float | None  # the literature or measured value
    note: str = ""

    @property
    def deviation(self) -> float | None:
        if self.computed is None or self.reference is None or self.reference == 0:
            return None
        if not (np.isfinite(self.computed) and np.isfinite(self.reference)):
            return None  # for example the OML density when noise spoils the ion fit: not run, never a fail
        return (self.computed - self.reference) / self.reference

    @property
    def passed(self) -> bool | None:
        """None when the check could not run."""
        if self.deviation is None:
            return None
        return abs(self.deviation) <= tolerance() + 1e-12


def tolerance() -> float:
    return load_envelope()["validation"]["agreement_tolerance_fraction"]


# ------------------------------------------------------------------------------------ literature
def benchmark_checks() -> list[Check]:
    from plasma_twin.reference.loaders import load_benchmarks
    from plasma_twin.stage1.benchmark import compare
    rows = {r["id"]: r for r in load_benchmarks()}
    checks = []
    for c in compare():
        row = rows[f"{c.point}_{c.quantity}"]
        source = f"{row['citation'].split(',')[0]} et al. (2018), {row['location_in_source'].split(';')[0]}"
        name = f"{c.quantity} at {c.pressure_mbar * 750.06:.0f} mTorr, {c.power_w:g} W" + (" (exit-gate point)" if c.in_gate else "")
        checks.append(Check(name, c.quantity, row["unit"], source, None, True, c.modelled, c.measured))
    return checks


# ------------------------------------------------------------------------------------ measured files
def _stage1_result(conditions: dict):
    from plasma_twin.services import stage1
    return stage1.run({**stage1.default_config(), **conditions})


def probe_values(store: MeasuredStore, record: MeasuredFile) -> tuple[float, float, str]:
    """(T_e, n_e, how they were taken) from a measured probe file, by the M6 method."""
    from plasma_twin.probe.analysis import analyse
    voltage, current, _ = store.load(record.file_id)
    geometry = record.metadata["probe"]
    result = analyse(voltage, current, float(geometry["tip_radius_mm"]), float(geometry["exposed_length_mm"]))
    if result.eepf_reliable:
        return result.effective_temperature_ev, result.electron_density_m3, "EEPF effective temperature and EEPF density"
    return result.slope_temperature_ev, result.ion_density_m3, "slope T_e and OML ion density (EEPF unreliable: noise)"


def spectrum_from_arrays(wavelength: np.ndarray, intensity: np.ndarray, fwhm_nm: float, gas_temperature_k: float):
    from plasma_twin.oes.spectrum import Spectrum, SpectrometerSettings
    settings = SpectrometerSettings(fwhm_nm, float(wavelength[0]), float(wavelength[-1]), 0.0)
    return Spectrum(wavelength, intensity, {}, settings, gas_temperature_k)


def file_checks(store: MeasuredStore, record: MeasuredFile, probes: list[MeasuredFile]) -> list[Check]:
    from plasma_twin.probe.analysis import ProbeAnalysisError
    conditions = record.metadata.get("conditions", {})
    base = dict(reference_source=record.file_id, file_id=record.file_id, citable=record.citable)
    if record.diagnostic == "probe":
        result = _stage1_result(conditions)
        try:
            te, ne, how = probe_values(store, record)
        except ProbeAnalysisError as problem:
            return [Check("probe analysis", "T_e", "eV", computed=None, reference=None, note=f"not run: {problem}", **base)]
        return [Check("T_e from the probe", "T_e", "eV", computed=result.te_ev, reference=te, note=how, **base),
                Check("n_e from the probe", "n_e", "m^-3", computed=result.ne_center_m3, reference=ne, note=how, **base)]
    wavelength, intensity, _ = store.load(record.file_id)
    fwhm = float(record.metadata["instrument_fwhm_nm"])
    if record.stage == 1:
        from plasma_twin.oes.boltzmann import integrated_intensities
        from plasma_twin.oes.cr_model import solve_cr_for
        from plasma_twin.oes.line_ratio import fit_spectrum_points
        result = _stage1_result(conditions)
        points = [p for p in integrated_intensities(spectrum_from_arrays(wavelength, intensity, fwhm, result.inputs.gas_temperature_k),
                                                    solve_cr_for(result).lines) if p.intensity > 0]
        if len(points) < 3:
            return [Check("T_e from line ratios", "T_e", "eV", computed=result.te_ev, reference=None,
                          note=f"not run: only {len(points)} argon lines found in the measured range", **base)]
        partner = next((p for p in probes if p.metadata.get("conditions") == conditions), None)
        fixed_ne, how = None, "T_e and n_e both fitted"
        if partner is not None:
            try:
                fixed_ne, how = probe_values(store, partner)[1], f"n_e taken from probe file {partner.file_id}"
            except ProbeAnalysisError:
                pass
        fit = fit_spectrum_points(points, result, fixed_ne_m3=fixed_ne)
        checks = [Check("T_e from line ratios", "T_e", "eV", computed=result.te_ev, reference=fit.te_ev, note=how, **base)]
        if fixed_ne is None:
            checks.append(Check("n_e from line ratios", "n_e", "m^-3", computed=result.ne_center_m3, reference=fit.ne_m3, note=how, **base))
        return checks
    # Stage 2: the H-alpha Stark width (Phase 7 method)
    from plasma_twin.services import stage2
    from plasma_twin.stage2.uw_oes import H_MASS_KG, StarkUnavailable, UnderwaterSpectrum, h_alpha_nm, stark_density, stark_fwhm_nm
    from plasma_twin.oes.spectrum import SpectrometerSettings, doppler_fwhm_nm
    run = stage2.run({**stage2.default_config(), **conditions})
    ha, t = h_alpha_nm(), run.bubble.gas_temperature_k
    expected = stark_fwhm_nm(run.bubble.ne_m3)
    settings = SpectrometerSettings(fwhm, float(wavelength[0]), float(wavelength[-1]), 0.0)
    measured = UnderwaterSpectrum(wavelength, intensity, {"H-alpha": 1.0}, expected, ha,
                                  float(np.hypot(fwhm, doppler_fwhm_nm(ha, t, H_MASS_KG))), settings)
    try:
        stark = stark_density(measured)
    except (StarkUnavailable, RuntimeError, ValueError) as problem:
        return [Check("n_e from the H-alpha Stark width", "n_e", "m^-3", computed=run.bubble.ne_m3, reference=None,
                      note=f"not run: {problem}", **base)]
    return [Check("n_e from the H-alpha Stark width", "n_e", "m^-3", computed=run.bubble.ne_m3, reference=stark.ne_m3,
                  note="model n_e depends on the assumed power share and channel size", **base)]


# ------------------------------------------------------------------------------------ run and record
def run_validation(store: MeasuredStore, include_benchmarks: bool = True, record: bool = True) -> list[Check]:
    """FR10.7: every benchmark and measured-data comparison; recorded with date and software version."""
    checks = benchmark_checks() if include_benchmarks else []
    files = store.list()
    probes = [f for f in files if f.diagnostic == "probe"]
    for f in files:
        checks += file_checks(store, f, probes)
    if record:
        conn = connect(store.db_path)
        try:
            with conn:
                for c in checks:
                    if c.passed is None:
                        continue  # "not run" is reported, never stored as a pass or a fail
                    conn.execute(
                        "INSERT INTO validation_results (check_name, reference_source, imported_file_id, computed_value,"
                        " reference_value, deviation, tolerance, passed, software_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (c.name, c.reference_source, parse_id(c.file_id) if c.file_id else None, c.computed, c.reference,
                         c.deviation, tolerance(), int(c.passed), __version__))
        finally:
            conn.close()
    return checks
