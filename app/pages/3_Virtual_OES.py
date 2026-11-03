"""M4 Virtual OES (FR4.1-FR4.8): the emission spectrum of the open plasma."""
from common import PAGES, axis, cached_spectrum, config_json, need_result, page_setup, sci, status, svc  # noqa: I001

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
    c = st.columns(4)
    fwhm = c[0].number_input("Resolution FWHM (nm)", float(env["resolution_fwhm_nm"]["min"]), float(env["resolution_fwhm_nm"]["max"]),
                             float(st.session_state.get("oes_fwhm", env["resolution_fwhm_nm"]["default"])), format="%.3f")
    start = c[1].number_input("From λ (nm)", float(env["wavelength_start_nm"]["min"]), float(env["wavelength_start_nm"]["max"]),
                              float(st.session_state.get("oes_start", env["wavelength_start_nm"]["default"])))
    end = c[2].number_input("To λ (nm)", float(env["wavelength_end_nm"]["min"]), float(env["wavelength_end_nm"]["max"]),
                            float(st.session_state.get("oes_end", env["wavelength_end_nm"]["default"])))
    noise = c[3].number_input("Noise (% of peak)", float(env["noise_percent_of_peak"]["min"]), float(env["noise_percent_of_peak"]["max"]),
                              float(st.session_state.get("oes_noise", env["noise_percent_of_peak"]["default"])))
    st.caption("Integration time: the model gives power per volume, so a longer integration only scales the counts; "
               "the noise setting stands for the signal-to-noise it would give.")
    if st.form_submit_button("Recompute spectrum"):
        st.session_state.update(oes_fwhm=fwhm, oes_start=start, oes_end=end, oes_noise=noise)
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
has_n2 = result.mixture.get("n2c_excitation_m3_s", 0.0) > 0
show = st.multiselect("Show contributions (FR4.2)", ["Ar I", "N₂ second positive"] if has_n2 else ["Ar I"],
                      default=["Ar I", "N₂ second positive"] if has_n2 else ["Ar I"])
status("info", "O I lines (777, 844 nm) are added with the oxygen data in Phase 7.")
x, y = svc.downsample_peaks(spectrum.wavelength_nm, spectrum.intensity)
fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", name="spectrum"))
if "Ar I" in show:
    shown = [w for w in argon_lines if spectrum.settings.start_nm <= w <= spectrum.settings.end_nm]
    fig.add_trace(go.Scatter(x=shown, y=[0] * len(shown), mode="markers", marker_symbol="line-ns-open", marker_size=12,
                             name="Ar I line positions"))
st.plotly_chart(axis(fig, "Wavelength λ (nm)", "Spectral intensity I (W m⁻³ nm⁻¹)"), use_container_width=True)
st.caption(f"Drawn from {len(spectrum.wavelength_nm):,} points, reduced to {len(x):,} for display (each bin keeps its peak).")

# ------------------------------------------------------------------ identified lines (FR4.5)
st.subheader("Identified Ar I lines")
rows = [{"λ (nm)": f"{line.wavelength_nm:.3f}", "Species": "Ar I", "Transition": f"{line.upper} → {line.lower}",
         "A (s⁻¹)": sci(line.a_per_s), "Escape factor": f"{cr.escape_factors[line.wavelength_nm]:.3f}",
         "Power (W m⁻³)": sci(cr.line_emission_w_m3[line.wavelength_nm])}
        for line in cr.lines if spectrum.settings.start_nm <= line.wavelength_nm <= spectrum.settings.end_nm]
st.dataframe(rows, hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ overlay, export, next (FR4.6-FR4.8)
if st.session_state["role"] == "Researcher":
    status("info", "Overlaying an imported measured spectrum (FR4.6) comes with data import in Phase 8.")
text = "wavelength_nm\tintensity_W_m3_nm\n" + "\n".join(f"{a:.5f}\t{b:.6e}" for a, b in zip(spectrum.wavelength_nm, spectrum.intensity))
c1, c2 = st.columns(2)
c1.download_button("Download spectrum (two-column text, FR4.7)", text, file_name="synthetic_spectrum.txt")
if c2.button("Analyse this spectrum (M5)"):
    st.switch_page(PAGES["oes_analysis"])
