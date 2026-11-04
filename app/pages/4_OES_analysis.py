"""M5 OES analysis (FR5.1-FR5.10): Boltzmann plot, excitation temperature and line-ratio T_e."""
from common import (PAGES, axis, cached_probe, cached_spectrum, config_json, is_researcher, measured_spectrum,  # noqa: I001
                    measured_store, need_result, page_setup, probe_settings_text, sci, spectrometer_settings_text, status)

import csv
import io
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.oes.boltzmann import EQUILIBRIUM_FACTOR, fit, integrated_intensities, populations_vs_boltzmann
from plasma_twin.oes.gas_temp import DOPPLER_LINE_NM, doppler_temperature, n2_rotational_temperature
from plasma_twin.oes.spectrum import SpectrometerSettings
from plasma_twin.oes.line_ratio import fit_spectrum_points

page_setup("OES analysis")
st.title("OES analysis")
result = need_result()
config_text = config_json(st.session_state["config"])
spectrum, cr = cached_spectrum(config_text, spectrometer_settings_text())
source = "synthetic"
if is_researcher():
    oes_files = [f.file_id for f in measured_store().list(diagnostic="oes", stage=1)]
    source = st.selectbox("Spectrum to analyse (FR5.1)", ["synthetic"] + oes_files,
                          format_func=lambda s: "synthetic spectrum of the open plasma" if s == "synthetic" else f"measured file {s}")
if source == "synthetic":
    st.caption("Analysing the synthetic spectrum of the open plasma (FR5.1).")
else:
    spectrum, record = measured_spectrum(source, result.inputs.gas_temperature_k)
    status("info", f"Analysing measured file {source} with the CR-model lines and the open plasma's known quantities "
                   f"(gas density, geometry); its own conditions: {record.metadata.get('conditions')}.")

points = [p for p in integrated_intensities(spectrum, cr.lines) if p.intensity > 0]
if not points:
    status("error", "No argon lines lie inside the spectrometer's wavelength range; widen it on the OES screen.")
    st.stop()

# ------------------------------------------------------------------ line choice (FR5.8)
labels = {f"{p.wavelength_nm:.3f} nm": p for p in points}
chosen = st.multiselect("Lines in the fit (FR5.8)", list(labels), default=list(labels))
used = [labels[k] for k in chosen]
excluded = [k for k in labels if k not in chosen]
st.session_state["oes_excluded_nm"] = [round(labels[k].wavelength_nm, 3) for k in excluded]  # shown on M4 (FR4.5)

# ------------------------------------------------------------------ Boltzmann plot (FR5.2, FR5.3)
st.subheader("Boltzmann plot")
if len(used) >= 2:
    bfit = fit(used)
    x = np.array([p.upper_energy_ev for p in used])
    y = np.array([p.y for p in used])
    fig = go.Figure(go.Scatter(x=x, y=y, mode="markers", name="lines", text=[f"{p.wavelength_nm:.2f} nm" for p in used]))
    if np.isfinite(bfit.excitation_temperature_ev):
        xs = np.linspace(x.min(), x.max(), 2)
        slope = -1 / bfit.excitation_temperature_ev
        fig.add_trace(go.Scatter(x=xs, y=y.mean() + slope * (xs - x.mean()), mode="lines", name="fit"))
    st.plotly_chart(axis(fig, "Upper-level energy E_k (eV)", "ln(I λ / g_k A_ki) (dimensionless)"), use_container_width=True)
    if np.isfinite(bfit.excitation_temperature_ev):
        st.metric("Excitation temperature T_exc", f"{bfit.excitation_temperature_ev:.3f} ± {bfit.excitation_temperature_uncertainty_ev:.3f} eV",
                  help="Not the electron temperature: the 2p levels are not in equilibrium with the electrons.")
    st.caption(f"R² = {bfit.r_squared:.3f}; {bfit.n_lines} lines spanning {bfit.energy_span_ev:.2f} eV.")
    if bfit.reliable:
        status("ok", "The Boltzmann fit meets the reliability rules.")
    else:
        status("warn", "Unreliable fit (E9): " + "; ".join(bfit.reasons) + ". The argon 2p levels span only about 0.6 eV.")
else:
    status("error", "Choose at least two lines.")

# ------------------------------------------------------------------ level populations (FR5.4)
st.subheader("Level populations against a Boltzmann distribution")
ground = result.mixture.get("argon_density_m3", result.gas_density_m3)
levels, in_equilibrium = populations_vs_boltzmann(cr, ground, result.te_ev)
energies = np.array([0.0] + [r.energy_ev for r in levels])
fig = go.Figure(go.Scatter(x=energies, y=[ground] + [r.density_m3 / r.weight for r in levels], mode="markers",
                           text=["ground"] + [r.level for r in levels], name="CR model"))
grid = np.linspace(0.0, energies.max(), 50)
fig.add_trace(go.Scatter(x=grid, y=ground * np.exp(-grid / result.te_ev), mode="lines", line=dict(dash="dot"),
                         name=f"Boltzmann at T_e = {result.te_ev:.2f} eV"))
st.plotly_chart(axis(fig, "Level energy E_k (eV)", "Density per state n_k / g_k (m⁻³)", log_y=True), use_container_width=True)
if in_equilibrium:
    status("ok", f"Every level is within a factor {EQUILIBRIUM_FACTOR:g} of Boltzmann equilibrium at T_e.")
else:
    low = min(r.ratio for r in levels if r.level.startswith("2p"))
    high = max(r.ratio for r in levels if r.level.startswith("2p"))
    status("warn", f"Not in equilibrium: the 2p levels hold only {low:.1e} to {high:.1e} of their Boltzmann population at T_e "
                   "(they are filled by electron impact and emptied by radiation). So T_exc from the Boltzmann plot is "
                   "not the electron temperature.")

# ------------------------------------------------------------------ gas temperature (FR5.6)
st.subheader("Gas temperature")
# the N2 method fits a separate synthetic UV acquisition, so it is offered only for the synthetic spectrum
has_n2 = source == "synthetic" and result.mixture.get("n2c_excitation_m3_s", 0.0) > 0
methods = [f"Doppler width of Ar I {DOPPLER_LINE_NM:.1f} nm"] + (["N₂ rotational temperature, (1,0) band at 315.9 nm"] if has_n2 else [])
method = st.radio("Method", methods, horizontal=True)
if not has_n2:
    st.caption("The N₂ rotational method needs nitrogen in the mixture.")
if method.startswith("Doppler"):
    doppler = doppler_temperature(spectrum)
    if doppler.enabled:
        st.metric("T_gas (Doppler)", f"{doppler.gas_temperature_k:.0f} K")
    else:
        status("warn", f"Doppler method not available: {doppler.reason}. Lower the FWHM on the OES screen.")
    st.caption(f"The {DOPPLER_LINE_NM:.1f} nm line (2p1 → 1s2) is used, not 811.5 nm: 811.5 nm ends on the metastable 1s5, "
               "so self-absorption could widen it (BUILD_STEPS.md, Phase 4e).")
else:
    uv = SpectrometerSettings.defaults(fwhm_nm=spectrum.settings.fwhm_nm, start_nm=305, end_nm=340,
                                       noise_percent=spectrum.settings.noise_percent)
    uv_spectrum, _ = cached_spectrum(config_text, json.dumps(uv.__dict__, sort_keys=True))
    rotational = n2_rotational_temperature(uv_spectrum)
    st.metric("T_gas (N₂ rotational)", f"{rotational.rotational_temperature_k:.0f} K")
    st.caption("Fitted on a separate UV acquisition (305-340 nm), the way the band is measured.")
    if rotational.nh_overlap_flagged:
        status("warn", f"NH (A-X) emission near 336 nm: {rotational.nh_excess_fraction:.0%} beyond the N₂ prediction.")
    else:
        status("ok", "No NH (A-X) overlap near 336 nm.")
st.caption(f"Model gas temperature: {result.inputs.gas_temperature_k:.0f} K.")

# ------------------------------------------------------------------ line-ratio T_e with n_e from the probe (FR5.5, FR5.7)
st.subheader("Electron temperature from line ratios")
_, probe, probe_error = cached_probe(config_text, probe_settings_text())
fixed_ne, source = None, "fitted from the spectrum (no probe value available)"
if probe is not None:
    fixed_ne = probe.electron_density_m3 if probe.eepf_reliable else probe.saturation_density_m3
    source = ("simulated Langmuir probe, EEPF integral" if probe.eepf_reliable
              else "simulated Langmuir probe, saturation current (the EEPF is too noisy)")
if len(used) >= 3:
    lr = fit_spectrum_points(used, result, fixed_ne_m3=fixed_ne)
    c1, c2 = st.columns(2)
    c1.metric("T_e from line ratios", f"{lr.te_ev:.2f} eV")
    c2.metric("n_e used", f"{sci(lr.ne_m3)} m⁻³")
    st.caption(f"Source of n_e (FR5.7): {source}. Fit RMS of ln(intensity share): {lr.rms_log_residual:.2e}.")
    status("info", "When n_e comes from the probe, a 10 % error in it moves this T_e by about 30 % "
                   "(BUILD_STEPS.md, Phase 5; asked of the supervisor in Q9).")
else:
    lr = None
    status("error", "The line-ratio fit needs at least three lines.")

# ------------------------------------------------------------------ export and next (FR5.9, FR5.10)
buffer = io.StringIO()
writer = csv.writer(buffer)
writer.writerow(["quantity", "value", "uncertainty", "method"])
if len(used) >= 2:
    writer.writerow(["T_exc (eV)", bfit.excitation_temperature_ev, bfit.excitation_temperature_uncertainty_ev,
                     "Boltzmann plot; not an electron temperature"])
    writer.writerow(["R2", bfit.r_squared, "", "Boltzmann plot"])
if lr is not None:
    writer.writerow(["T_e (eV)", lr.te_ev, "", f"CR-model line ratios; n_e from {source}"])
writer.writerow([])
writer.writerow(["wavelength_nm", "intensity", "g_k", "A_ki", "E_k_eV", "used"])
for key, p in labels.items():
    writer.writerow([p.wavelength_nm, p.intensity, p.g_upper, p.a_per_s, p.upper_energy_ev, key not in excluded])
c1, c2 = st.columns(2)
c1.download_button("Download analysis and line list (CSV)", buffer.getvalue(), file_name="oes_analysis.csv", mime="text/csv")
if c2.button("Open the comparison (M7)"):
    st.switch_page(PAGES["compare"])
