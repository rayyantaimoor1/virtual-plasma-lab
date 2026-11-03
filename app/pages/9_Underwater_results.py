"""M9 Underwater plasma and disinfection results (FR9.1-FR9.6)."""
from common import (PAGES, __version__, axis, cached_power_share, cached_stage2, config_json, metric_grid,  # noqa: I001
                    page_setup, sci, spectrometer_settings_text, status, store, svc, svc2)

import plotly.graph_objects as go
import streamlit as st

page_setup("Underwater results")
st.title("Underwater plasma and disinfection results (Stage 2)")
if not st.session_state.get("has_run2"):
    status("info", "No underwater run yet. Configure one on the underwater configuration screen.")
    if st.button("Go to underwater configuration"):
        st.switch_page(PAGES["underwater"])
    st.stop()
config = st.session_state["config2"]
problems, _ = svc2.validate_config(config)
if problems:
    status("error", "The configuration has errors; fix them on the configuration screen.")
    st.stop()
result = cached_stage2(config_json(config), spectrometer_settings_text())
summary = svc2.summarise(result)
b, w, s = result.bubble, result.liquid, result.survival

# ------------------------------------------------------------------ key results (FR9.1)
metric_grid([
    ("Log reduction at the treatment time" + (" (capped)" if s.capped else ""), f"{s.log_reduction:.2f}",
     "log10(N0/N); capped when fewer than one cell is left in the whole volume"),
    ("D-value", f"{s.d_value_min:.3g} min per log" if s.d_value_min else "no inactivation", "treatment time / log reduction"),
    ("Energy yield", f"{s.energy_yield_log_per_kj_l:.3g} log per kJ/L", "log reduction / (energy / volume)"),
    ("Bubble plasma T_e", f"{b.te_ev:.2f} eV", "ionization = attachment balance, Maxwellian"),
    ("n_e in the channel (model)", f"{sci(b.ne_m3)} m⁻³", f"channel {1e3 * b.channel_diameter_m:.2f} mm across (Briels et al. 2008)"),
    ("n_e from the H-alpha Stark width", f"{sci(result.stark.ne_m3)} m⁻³" if result.stark else "not available",
     result.stark_reason or "fitted on its own 650-663 nm acquisition"),
])
for flag in s.flags:
    status("warn", flag)
for warning in b.warnings:
    status("warn", warning)
status("info", "The end-to-end check against measured survival is open: no published experiment matches this device, "
               "so the supervisor's time-resolved data are awaited (SUPERVISOR_QUESTIONS.md, Q13).")

# ------------------------------------------------------------------ reactive species (FR9.2)
left, right = st.columns(2)
with left:
    st.subheader("Reactive species in the water")
    minutes = w.time_s / 60
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=minutes, y=w.ozone_mg_l, name="O₃ (mg/L)"))
    fig.add_trace(go.Scatter(x=minutes, y=w.h2o2_mmol_l, name="H₂O₂ (mmol/L)"))
    fig.add_trace(go.Scatter(x=minutes, y=w.oh_mol_l * 1e9, name="OH (nmol/L)"))
    st.plotly_chart(axis(fig, "Treatment time t (min)", "Concentration c (see legend)", log_y=True), use_container_width=True)
    st.caption(f"k_La = {w.kla_per_s:.2e} s⁻¹ (Gao et al. 2005, a different contactor); ozone saturation "
               f"{w.ozone_saturation_mg_l:.3g} mg/L; ozone yield of the bubbles {b.ozone_yield_g_per_kwh:.2g} g/kWh.")
# ------------------------------------------------------------------ survival (FR9.3)
with right:
    st.subheader("Survival curve (Hom model)")
    fig = go.Figure(go.Scatter(x=minutes, y=s.log_survival, name="model"))
    st.plotly_chart(axis(fig, "Treatment time t (min)", "log₁₀(N/N₀) (dimensionless)"), use_container_width=True)
    st.caption(f"Hunt & Mariñas (1997): first order in dissolved O₃, k = {s.rate_constant_l_mg_s:.1f} L mg⁻¹ s⁻¹ at "
               f"{config['water_temperature_c']:g} °C (n = m = 1). No published time-resolved points exist for this device.")

# ------------------------------------------------------------------ underwater OES (FR9.4)
st.subheader("Underwater emission spectrum")
x, y = svc.downsample_peaks(result.spectrum.wavelength_nm, result.spectrum.intensity)
fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", name="spectrum"))
st.plotly_chart(axis(fig, "Wavelength λ (nm)", "Spectral intensity I (W m⁻³ nm⁻¹)"), use_container_width=True)
st.dataframe([{"Emitter": k, "Power in the channel (W m⁻³)": sci(v)} for k, v in result.spectrum.line_power_w_m3.items()],
             hide_index=True, use_container_width=True)
for note in result.spectrum.notes:
    st.caption(note)
if result.stark:
    st.caption(f"Stark n_e: Lorentzian FWHM {result.stark.lorentzian_fwhm_nm:.4f} nm fitted on {result.stark.window_nm[0]:.1f}-"
               f"{result.stark.window_nm[1]:.1f} nm; relation of van der Horst et al. (2012) from Gigosos et al. (2003).")
else:
    status("warn", f"Stark n_e not available: {result.stark_reason}.")

# ------------------------------------------------------------------ water chemistry (FR9.5)
st.subheader("Water before and after treatment")
st.dataframe([
    {"Quantity": "Temperature (°C)", "Before": f"{w.temperature_before_c:.2f}", "After": f"{w.temperature_after_c:.2f}"},
    {"Quantity": "pH", "Before": f"{w.ph_before:.2f}", "After": f"{w.ph_after:.2f}"},
    {"Quantity": "Conductivity (µS/cm)", "Before": f"{w.conductivity_before_us_cm:g}", "After": f"{w.conductivity_after_us_cm:g}"},
    {"Quantity": "ORP, Nernst estimate (V)", "Before": "-", "After": f"{w.orp_after_v:.2f}" if w.orp_after_v else "-"},
], hide_index=True, use_container_width=True)
for note in w.notes:
    st.caption(note)

# ------------------------------------------------------------------ the main uncertainty
with st.expander("Sensitivity to the share of power reaching the bubble gas"):
    rows = cached_power_share(config_json(config))
    fig = go.Figure(go.Scatter(x=[r["power_share"] for r in rows], y=[r["log_reduction"] for r in rows], mode="lines+markers",
                               name="log reduction"))
    fig.add_trace(go.Scatter(x=[r["power_share"] for r in rows], y=[r["ozone_mg_l"] for r in rows], mode="lines+markers",
                             name="O₃ at the end (mg/L)", yaxis="y2"))
    fig.update_layout(xaxis_type="log", yaxis2=dict(title="Dissolved ozone c (mg/L)", overlaying="y", side="right"))
    st.plotly_chart(axis(fig, "Power share η (dimensionless)", "Log reduction (dimensionless)"), use_container_width=True)
    st.caption("Above about 0.1, one pulse splits more than 10 % of the O₂ and the model's chemistry is outside its range.")

# ------------------------------------------------------------------ save and export (FR9.6)
st.subheader("Save and export")
c1, c2 = st.columns(2)
with c1.form("save_session2"):
    note = st.text_input("Note for this session")
    if st.form_submit_button("Save as session"):
        plain = {k: (float(v) if hasattr(v, "dtype") else v) for k, v in summary.items()}
        session_id = store().save(2, config, svc2.config_hash(config), {"stage2": plain}, note, __version__)
        st.session_state["session_id2"] = session_id
        status("ok", f"Saved as {session_id}.")
c2.download_button("Download results (CSV)", svc2.results_csv(summary, config, result, st.session_state.get("session_id2")),
                   file_name="stage2_results.csv", mime="text/csv")
