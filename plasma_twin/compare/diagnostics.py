"""Model vs OES vs Langmuir probe, side by side: Phase 5 (FR7.1-FR7.6, ACC-2, LI-4).

WHY: the supervisor asked for OES-derived and probe-derived T_e and n_e to be compared side by side
with the model (D8). Each diagnostic has its own assumptions; agreement within +/-30 % between
independent methods is the evidence that the twin and its virtual instruments are consistent.

RULES (BUILD_STEPS.md, Phase 5, fixed before this code):
- Each diagnostic value's deviation is measured from the model; it passes if |deviation| <= 30 %.
  A quantity passes when every INDEPENDENT, RELIABLE diagnostic value passes.
- T_e: the probe's EEPF effective temperature (same definition as the model) is compared; the slope
  T_e is shown only. OES T_e comes from the line-ratio fit.
- n_e: by default OES takes n_e from the probe (supervisor, Q2), so the OES n_e is DEPENDENT and is
  excluded from the agreement count (FR7.2). With fit_oes_ne=True both are fitted from the spectrum.
- T_gas: OES from the N2 rotational temperature (when N2 is present, on its own UV acquisition) or
  from Doppler (when E8 allows).
- T_exc is shown but excluded, because the 2p levels are not in equilibrium with the electrons (FR7.5).
- With O2 present, probe and OES values are flagged approximate (LI-4).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import dataclass, field

from plasma_twin.config.loader import load_envelope

if TYPE_CHECKING:  # used in annotations only (MNT-3): nothing extra is imported at run time
    from plasma_twin.oes.spectrum import SpectrometerSettings
    from plasma_twin.probe.iv_model import ProbeSettings
    from plasma_twin.stage1.global_model import Stage1Result


def tolerance() -> float:
    """The agreement tolerance (30 %) from envelope.toml, fixed before any comparison (ACC-4)."""
    return load_envelope()["validation"]["agreement_tolerance_fraction"]


def within_tolerance(deviation: float) -> bool:
    """|deviation| <= 30 % (the tolerance in envelope.toml). Exactly 30 % passes."""
    return abs(deviation) <= tolerance() + 1e-12


@dataclass(frozen=True)
class Entry:
    method: str  # "OES" or "probe"
    value: float
    deviation: float  # (value - model) / model
    passes: bool
    independent: bool
    reliable: bool
    note: str = ""

    @property
    def counted(self) -> bool:
        """Only independent, reliable diagnostics count towards agreement (FR7.3)."""
        return self.independent and self.reliable


@dataclass(frozen=True)
class QuantityComparison:
    quantity: str
    unit: str
    model: float
    entries: tuple[Entry, ...]

    @property
    def compared(self) -> tuple[Entry, ...]:
        """The entries that count towards the verdict."""
        return tuple(e for e in self.entries if e.counted)

    @property
    def max_deviation(self) -> float | None:
        """The largest relative deviation among the counted entries, or None."""
        return max((abs(e.deviation) for e in self.compared), default=None)

    @property
    def passes(self) -> bool | None:
        """None when no independent, reliable diagnostic measured this quantity."""
        return all(e.passes for e in self.compared) if self.compared else None


@dataclass(frozen=True)
class DiagnosticsReport:
    quantities: tuple[QuantityComparison, ...]
    excitation_temperature_ev: float | None
    excitation_note: str
    approximate: bool  # LI-4: O2 present
    assumptions: dict[str, tuple[str, ...]]
    probe_slope_te_ev: float | None = None
    probe_saturation_ne_m3: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verdict(self) -> str:
        """A one-line summary of how many quantities agree within the tolerance (FR7.4)."""
        judged = [q for q in self.quantities if q.passes is not None]
        agree = sum(1 for q in judged if q.passes)
        return f"{agree} of {len(judged)} comparable quantities agree within ±{tolerance():.0%}"


def entry(method: str, value: float, model: float, independent: bool = True, reliable: bool = True, note: str = "") -> Entry:
    """One diagnostic value against the model, with its relative deviation and tolerance check."""
    deviation = (value - model) / model
    return Entry(method, value, deviation, within_tolerance(deviation), independent, reliable, note)


def compare(result: Stage1Result, probe_settings: ProbeSettings | None = None,
            spectrometer_settings: SpectrometerSettings | None = None, fit_oes_ne: bool = False) -> DiagnosticsReport:
    """Run both virtual instruments on a solved global-model point and compare them with the model."""
    from plasma_twin.oes.boltzmann import fit as boltzmann_fit
    from plasma_twin.oes.boltzmann import integrated_intensities
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.oes.gas_temp import doppler_temperature, n2_rotational_temperature
    from plasma_twin.oes.line_ratio import fit_spectrum_points
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.analysis import ProbeAnalysisError, analyse_curve
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from

    x = result.inputs
    approximate = x.o2_percent_of_ar > 0
    warnings: list[str] = []
    if approximate:
        warnings.append("O2 present: negative ions change the probe's ion current and the argon CR model ignores O2 "
                        "chemistry beyond metastable quenching, so probe and OES values are approximate (LI-4)")

    # ---------------------------------------------------------------- probe
    probe = None
    try:
        probe = analyse_curve(generate(plasma_from(result), probe_settings or ProbeSettings.defaults()))
        warnings.extend(probe.warnings)
    except ProbeAnalysisError as problem:
        warnings.append(str(problem))

    # ---------------------------------------------------------------- OES
    cr = solve_cr_for(result)
    spectrum = spectrum_for(result, spectrometer_settings or SpectrometerSettings.defaults())
    points = [p for p in integrated_intensities(spectrum, cr.lines) if p.intensity > 0]
    boltzmann = boltzmann_fit(points)
    oes_ne_from_probe = not fit_oes_ne and probe is not None
    fixed_ne = None
    if oes_ne_from_probe:
        fixed_ne = probe.electron_density_m3 if probe.eepf_reliable else probe.saturation_density_m3
    oes = fit_spectrum_points(points, result, fixed_ne_m3=fixed_ne)

    # ---------------------------------------------------------------- the three quantities
    te_entries = [entry("OES", oes.te_ev, result.te_ev, reliable=not approximate,
                        note="line-ratio fit of the CR model" + (" with n_e from the probe" if oes_ne_from_probe else ""))]
    ne_entries = [entry("OES", oes.ne_m3, result.ne_center_m3, independent=not oes_ne_from_probe, reliable=not approximate,
                        note="taken from the probe (dependent, not counted)" if oes_ne_from_probe else "line-ratio fit")]
    if probe is not None:
        te_entries.append(entry("probe", probe.effective_temperature_ev, result.te_ev,
                                reliable=probe.eepf_reliable and not approximate,
                                note="EEPF effective temperature" + ("" if probe.eepf_reliable else " (EEPF unreliable: noise)")))
        ne_entries.append(entry("probe", probe.electron_density_m3, result.ne_center_m3,
                                reliable=probe.eepf_reliable and not approximate,
                                note="EEPF integral" + ("" if probe.eepf_reliable else " (EEPF unreliable: noise)")))

    gas_entries = []
    if result.mixture.get("n2c_excitation_m3_s", 0.0) > 0:
        uv = SpectrometerSettings.defaults(start_nm=305, end_nm=340,
                                           noise_percent=(spectrometer_settings or SpectrometerSettings.defaults()).noise_percent)
        rotational = n2_rotational_temperature(spectrum_for(result, uv))
        gas_entries.append(entry("OES", rotational.rotational_temperature_k, x.gas_temperature_k,
                                 reliable=not rotational.nh_overlap_flagged,
                                 note="N2 (1,0) rotational temperature, UV acquisition"))
    doppler = doppler_temperature(spectrum)
    if doppler.enabled:
        gas_entries.append(entry("OES", doppler.gas_temperature_k, x.gas_temperature_k, note="Doppler width of 750.4 nm"))
    elif not gas_entries:
        warnings.append(f"no OES gas temperature: {doppler.reason}; and no N2 band without nitrogen")

    quantities = (
        QuantityComparison("T_e", "eV", result.te_ev, tuple(te_entries)),
        QuantityComparison("n_e", "m^-3", result.ne_center_m3, tuple(ne_entries)),
        QuantityComparison("T_gas", "K", x.gas_temperature_k, tuple(gas_entries)),
    )
    assumptions = {
        "model": (f"0D global model, {x.eedf} EEDF, symmetric electrodes", "RF power taken as absorbed power",
                  "gas temperature from a conduction heat balance" if x.gas_heating else "fixed gas temperature"),
        "OES": ("argon CR model (1s, 2p) with BSR rates; escape factors over half the gap",
                f"spectrometer FWHM {spectrum.settings.fwhm_nm} nm, noise {spectrum.settings.noise_percent} % of peak",
                "n_e taken from the probe (supervisor Q2)" if oes_ne_from_probe else "T_e and n_e both fitted"),
        "probe": ("cylindrical probe at the centre; OML ion current; Druyvesteyn EEPF",
                  f"r_p/lambda_D = {probe.radius_over_debye:.1f} (OML needs <= 1)" if probe else "analysis failed"),
    }
    t_exc = boltzmann.excitation_temperature_ev if boltzmann.excitation_temperature_ev != float("inf") else None
    return DiagnosticsReport(quantities, t_exc,
                             "the 2p levels are not in Boltzmann equilibrium with the electrons, so "
                             "it is not an electron temperature and is excluded (FR7.5)",
                             approximate, assumptions,
                             probe.slope_temperature_ev if probe else None,
                             probe.saturation_density_m3 if probe else None, tuple(warnings))
