"""M4 Virtual OES (FR4.1-FR4.8): the emission spectrum of the open plasma."""
from common import (PAGES, axis, cached_contributions, cached_spectrum, config_json, need_result, page_setup,  # noqa: I001
                    sci, status, svc)

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.config.loader import load_envelope
from plasma_twin.oes.spectrum import SpectrometerSettings, SpectrumSettingsOutOfRange

page_setup("Virtual OES")
st.title("Virtual optical emission spectroscopy")
result = need_result()
env = load_envelope()["oes"]

# ------------------------------------------------------------------ instrument settings (FR4.3, FR4.4)
with st.form("instrument"):
    c = st.columns(5)
    fwhm = c[0].number_input("Resolution FWHM (nm)", float(env["resolution_fwhm_nm"]["min"]), float(env["resolution_fwhm_nm"]["max"]),
                             float(st.session_state.get("oes_fwhm", env["resolution_fwhm_nm"]["default"])), format="%.3f")
    start = c[1].number_input("From λ (nm)", float(env["wavelength_start_nm"]["min"]), float(env["wavelength_start_nm"]["max"]),
                              float(st.session_state.get("oes_start", env["wavelength_start_nm"]["default"])))
    end = c[2].number_input("To λ (nm)", float(env["wavelength_end_nm"]["min"]), float(env["wavelength_end_nm"]["max"]),
                            float(st.session_state.get("oes_end", env["wavelength_end_nm"]["default"])))
    noise = c[3].number_input("Noise (% of peak)", float(env["noise_percent_of_peak"]["min"]), float(env["noise_percent_of_peak"]["max"]),
                              float(st.session_state.get("oes_noise", env["noise_percent_of_peak"]["default"])))
    integration = c[4].number_input("Integration time (ms)", 1.0, 60000.0, float(st.session_state.get("oes_integration_ms", 100.0)))
    st.caption("The model gives emitted power per volume, so the integration time only scales the counts: it is recorded "
               "with the export, and the noise setting stands for the signal-to-noise it would give.")
    if st.form_submit_button("Recompute spectrum"):
        st.session_state.update(oes_fwhm=fwhm, oes_start=start, oes_end=end, oes_noise=noise, oes_integration_ms=integration)
settings = SpectrometerSettings.defaults(fwhm_nm=st.session_state.get("oes_fwhm", fwhm),
                                         start_nm=st.session_state.get("oes_start", start),
                                         end_nm=st.session_state.get("oes_end", end),
                                         noise_percent=st.session_state.get("oes_noise", noise))
try:
    settings.validate()
except SpectrumSettingsOutOfRange as problem:
    status("error", str(problem))
    st.stop()


settings_text = json.dumps(settings.__dict__, sort_keys=True)
spectrum, cr = cached_spectrum(config_json(st.session_state["config"]), settings_text)
st.session_state["oes_settings"] = settings_text

# ------------------------------------------------------------------ the spectrum (FR4.1, FR4.2)
argon_lines = {line.wavelength_nm for line in cr.lines}
parts = cached_contributions(config_json(st.session_state["config"]), settings_text)
st.markdown("**Show contributions (FR4.2)**")
t = st.columns(3)
show = {"Ar I": t[0].checkbox("Ar I", value=True),
        "N2 second positive": t[1].checkbox("N₂ second positive", value="N2 second positive" in parts,
                                            disabled="N2 second positive" not in parts),
        "O I": t[2].checkbox("O I", value=False, disabled=True, help="O I lines (777, 844 nm) come with the oxygen data in Phase 7.")}
# Hiding a species subtracts its noise-free part, so the noise stays as it was.
shown_intensity = spectrum.intensity - sum((part for name, part in parts.items() if not show[name]), np.zeros_like(spectrum.intensity))
x, y = svc.downsample_peaks(spectrum.wavelength_nm, shown_intensity)
fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", name="spectrum"))
if show["Ar I"]:
    shown = [w for w in argon_lines if spectrum.settings.start_nm <= w <= spectrum.settings.end_nm]
    fig.add_trace(go.Scatter(x=shown, y=[0] * len(shown), mode="markers", marker_symbol="line-ns-open", marker_size=12,
                             name="Ar I line positions"))
st.plotly_chart(axis(fig, "Wavelength λ (nm)", "Spectral intensity I (W m⁻³ nm⁻¹)"), use_container_width=True)
st.caption(f"Drawn from {len(spectrum.wavelength_nm):,} points, reduced to {len(x):,} for display (each bin keeps its peak).")

# ------------------------------------------------------------------ identified lines (FR4.5)
st.subheader("Identified Ar I lines")
in_range = [line for line in cr.lines if spectrum.settings.start_nm <= line.wavelength_nm <= spectrum.settings.end_nm]
brightest = max((cr.line_emission_w_m3[line.wavelength_nm] for line in in_range), default=0.0) or 1.0
excluded = set(st.session_state.get("oes_excluded_nm", []))  # chosen on the OES analysis screen (FR5.8)
rows = [{"λ (nm)": f"{line.wavelength_nm:.3f}", "Species": "Ar I", "Transition": f"{line.upper} → {line.lower}",
         "E_k (eV)": f"{line.upper_energy_ev:.3f}", "g_k A_ki (s⁻¹)": sci(line.g_upper * line.a_per_s),
         "Relative intensity": f"{cr.line_emission_w_m3[line.wavelength_nm] / brightest:.3g}",
         "Escape factor": f"{cr.escape_factors[line.wavelength_nm]:.3f}",
         "In Boltzmann plot": "yes" if cr.line_emission_w_m3[line.wavelength_nm] > 0
         and round(line.wavelength_nm, 3) not in excluded else "no"}
        for line in in_range]
n2 = parts.get("N2 second positive")
if n2 is not None and n2.max() > 0:
    band = spectrum.wavelength_nm[n2 > 1e-3 * n2.max()]
    rows.append({"λ (nm)": f"{band.min():.0f}-{band.max():.0f}", "Species": "N₂", "Transition": "C³Πu → B³Πg (second positive bands)",
                 "E_k (eV)": "-", "g_k A_ki (s⁻¹)": "-", "Relative intensity": "-", "Escape factor": "-",
                 "In Boltzmann plot": "no (molecular band)"})
st.dataframe(rows, hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ overlay, export, next (FR4.6-FR4.8)
if st.session_state["role"] == "Researcher":
    status("info", "Overlaying an imported measured spectrum (FR4.6) comes with data import in Phase 8.")
header = svc.export_header(st.session_state.get("session_id"), resolution_fwhm_nm=settings.fwhm_nm,
                           wavelength_range_nm=f"{settings.start_nm}-{settings.end_nm}", noise_percent_of_peak=settings.noise_percent,
                           integration_time_ms=st.session_state.get("oes_integration_ms", 100.0), noise_seed=settings.seed)
text = header + "wavelength_nm\tintensity_W_m3_nm\n" + "\n".join(f"{a:.5f}\t{b:.6e}" for a, b in zip(spectrum.wavelength_nm, spectrum.intensity))
c1, c2 = st.columns(2)
c1.download_button("Download spectrum (two-column text, FR4.7)", text, file_name="synthetic_spectrum.txt")
if c2.button("Analyse this spectrum (M5)"):
    st.switch_page(PAGES["oes_analysis"])
