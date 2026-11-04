"""M6 Virtual Langmuir probe (FR6.1-FR6.10): simulate and analyse an I-V curve."""
from common import (PAGES, axis, cached_probe, config_json, is_researcher, measured_store, metric_grid, need_result,  # noqa: I001
                    page_setup, sci, status, svc)

import csv
import io
import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.config.loader import load_envelope
from plasma_twin.probe.eepf import SAVGOL_ORDER, SAVGOL_WINDOW
from plasma_twin.probe.iv_model import ProbeSettings, ProbeSettingsOutOfRange
from plasma_twin.stage1.eedf import EEDF, MAXWELLIAN_SHAPE

page_setup("Langmuir probe")
st.title("Virtual Langmuir probe (Stage 3)")
result = need_result()
env = load_envelope()["probe"]
saved = json.loads(st.session_state["probe_settings"]) if st.session_state.get("probe_settings") else ProbeSettings.defaults().__dict__

# ------------------------------------------------------------------ settings (FR6.1-FR6.4)
with st.form("probe"):
    t1, t2 = st.columns(2)
    t1.selectbox("Probe type (FR6.1)", ["Single cylindrical probe"], help="The COMSATS laboratory probe; the only type modelled.")
    t2.text_input("Tip material", "Tungsten", disabled=True)
    c = st.columns(5)
    radius = c[0].number_input("Tip radius r_p (mm)", float(env["tip_radius_mm"]["min"]), float(env["tip_radius_mm"]["max"]), float(saved["tip_radius_mm"]), format="%.3f")
    length = c[1].number_input("Exposed length L (mm)", float(env["exposed_length_mm"]["min"]), float(env["exposed_length_mm"]["max"]), float(saved["exposed_length_mm"]))
    start = c[2].number_input("Sweep from (V)", float(env["sweep_start_v"]["min"]), float(env["sweep_start_v"]["max"]), float(saved["sweep_start_v"]))
    end = c[3].number_input("Sweep to (V)", float(env["sweep_end_v"]["min"]), float(env["sweep_end_v"]["max"]), float(saved["sweep_end_v"]))
    step = c[4].number_input("Step (V)", float(env["sweep_step_v"]["min"]), float(env["sweep_step_v"]["max"]), float(saved["sweep_step_v"]))
    d = st.columns(3)
    noise = d[0].number_input("Noise (% of electron current at V_p)", float(env["noise_percent_of_saturation"]["min"]),
                              float(env["noise_percent_of_saturation"]["max"]), float(saved["noise_percent"]))
    rf_on = d[1].checkbox("RF distortion (FR6.3)", value=saved["rf_amplitude_v"] > 0)
    rf = d[2].number_input("RF amplitude left after compensation Ṽ (V)", float(env["rf_amplitude_v"]["min"]), float(env["rf_amplitude_v"]["max"]),
                           float(saved["rf_amplitude_v"]) or 5.0)
    if st.form_submit_button("Generate I-V curve (FR6.5)"):
        candidate = ProbeSettings(radius, length, start, end, step, noise, rf if rf_on else 0.0)
        try:
            candidate.validate()
            st.session_state["probe_settings"] = json.dumps(candidate.__dict__, sort_keys=True)
        except ProbeSettingsOutOfRange as problem:
            status("error", str(problem))

settings_text = st.session_state.get("probe_settings") or json.dumps(ProbeSettings.defaults().__dict__, sort_keys=True)
curve, analysis, error = cached_probe(config_json(st.session_state["config"]), settings_text)

fig = go.Figure(go.Scatter(x=curve.voltage_v, y=1e3 * curve.current_a, mode="lines+markers", marker_size=3, name="I(V)"))
st.plotly_chart(axis(fig, "Probe voltage V (V)", "Probe current I (mA)"), use_container_width=True)
if is_researcher():
    probe_files = [f.file_id for f in measured_store().list(diagnostic="probe")]
    chosen = st.selectbox("Analyse a measured I-V curve instead (FR6.9)", ["none"] + probe_files)
    if chosen != "none":
        from types import SimpleNamespace

        from plasma_twin.probe.analysis import ProbeAnalysisError, analyse
        voltage, current, record = measured_store().load(chosen)
        geometry = record.metadata["probe"]
        curve = SimpleNamespace(voltage_v=voltage, current_a=current)
        fig.add_trace(go.Scatter(x=voltage, y=1e3 * current, mode="lines", name=f"measured {chosen}"))
        st.plotly_chart(axis(fig, "Probe voltage V (V)", "Probe current I (mA)"), use_container_width=True, key="measured_iv")
        try:
            analysis, error = analyse(voltage, current, float(geometry["tip_radius_mm"]), float(geometry["exposed_length_mm"])), None
        except ProbeAnalysisError as problem:
            analysis, error = None, str(problem)
        status("info", f"Analysing measured file {chosen} with the same method (probe r_p = {geometry['tip_radius_mm']} mm, "
                       f"L = {geometry['exposed_length_mm']} mm).")

# ------------------------------------------------------------------ analysis (FR6.6, FR6.7)
if analysis is None:
    status("error", f"The analysis stopped (E11): {error}")
    st.stop()
st.subheader("Analysis")
flag = "" if analysis.eepf_reliable else " - UNRELIABLE (noise)"
o2 = result.inputs.o2_percent_of_ar > 0
oml_text = f"{sci(analysis.ion_density_m3)} m⁻³" if np.isfinite(analysis.ion_density_m3) else "not available"
metric_grid([
    ("Floating potential V_f", f"{analysis.floating_potential_v:.2f} V", ""),
    ("Plasma potential V_p", f"{analysis.plasma_potential_v:.2f} V", ""),
    ("T_eff (EEPF)" + flag, f"{analysis.effective_temperature_ev:.2f} eV", "Two-thirds of the mean energy: the model's definition of T_e"),
    ("n_e (EEPF)" + flag, f"{sci(analysis.electron_density_m3)} m⁻³", ""),
    ("Slope T_e", f"{analysis.slope_temperature_ev:.2f} eV", "Inverse slope of ln I_e between V_f and V_p"),
    ("n_e (OML ion current)" + (" - approximate (O₂)" if o2 else ""), oml_text,
     "n_i from the slope of I_i² (Chen Eq. 22), = n_e by quasi-neutrality; not available when noise spoils the I² fit"),
    ("n_e (saturation)", f"{sci(analysis.saturation_density_m3)} m⁻³", "Robust to noise"),
    ("Debye length λ_D", f"{1e3 * analysis.debye_length_m:.3f} mm", ""),
    ("r_p / λ_D", f"{analysis.radius_over_debye:.2f}", "OML needs at most 1"),
])
st.caption(f"Model values for comparison: T_e = {result.te_ev:.2f} eV, n₀ = {sci(result.ne_center_m3)} m⁻³.")
if analysis.oml_valid:
    status("ok", "r_p/λ_D ≤ 1: OML theory applies (FR6.7).")
for warning in analysis.warnings:
    status("warn", warning)
if o2:
    status("warn", "O₂ is present: negative ions change the ion current, so the probe values are approximate (LI-4).")

# ------------------------------------------------------------------ EEPF (FR6.8)
st.subheader("Electron energy probability function")
e = analysis.eepf
if analysis.eepf_reliable and len(e.energy_ev):
    mean_te = analysis.effective_temperature_ev
    fig = go.Figure(go.Scatter(x=e.energy_ev, y=np.where(e.eepf > 0, e.eepf, np.nan), mode="lines", name="from the probe"))
    energies = e.energy_ev[e.energy_ev > 0]
    reference = EEDF(mean_te, MAXWELLIAN_SHAPE)(energies) / np.sqrt(energies)
    fig.add_trace(go.Scatter(x=energies, y=reference, mode="lines", line=dict(dash="dot"), name="Maxwellian, same mean energy"))
    st.plotly_chart(axis(fig, "Electron energy ε (eV)", "EEPF g_p(ε) (eV⁻³ᐟ²)", log_y=True), use_container_width=True)
else:
    status("warn", "The EEPF is not drawn: noise makes the second derivative untrustworthy. Lower the noise to see it.")
step_v = float(curve.voltage_v[1] - curve.voltage_v[0])
st.caption(f"Druyvesteyn method. Smoothing window: Savitzky-Golay, {SAVGOL_WINDOW} points ({SAVGOL_WINDOW * step_v:g} V), "
           f"polynomial order {SAVGOL_ORDER} (FR6.8).")

# ------------------------------------------------------------------ export and next (FR6.10)
buffer = io.StringIO()
buffer.write(svc.export_header(st.session_state.get("session_id"), probe_settings=settings_text,
                                smoothing=f"Savitzky-Golay {SAVGOL_WINDOW} points, order {SAVGOL_ORDER}"))
writer = csv.writer(buffer)
writer.writerow(["V_volt", "I_ampere"])
writer.writerows(zip(curve.voltage_v, curve.current_a))
writer.writerow([])
writer.writerow(["quantity", "value", "unit"])
for name, value, unit in (("V_f", analysis.floating_potential_v, "V"), ("V_p", analysis.plasma_potential_v, "V"),
                          ("T_eff", analysis.effective_temperature_ev, "eV"), ("T_slope", analysis.slope_temperature_ev, "eV"),
                          ("n_e_EEPF", analysis.electron_density_m3, "m^-3"), ("n_e_OML_ion", analysis.ion_density_m3, "m^-3"),
                          ("n_e_saturation", analysis.saturation_density_m3, "m^-3"),
                          ("lambda_D", analysis.debye_length_m, "m"), ("EEPF_reliable", analysis.eepf_reliable, "")):
    writer.writerow([name, value, unit])
c1, c2 = st.columns(2)
c1.download_button("Download I-V curve and results (CSV)", buffer.getvalue(), file_name="probe_iv.csv", mime="text/csv")
if c2.button("Open the comparison (M7)"):
    st.switch_page(PAGES["compare"])
