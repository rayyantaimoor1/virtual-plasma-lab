"""M3 Results (FR3.1-FR3.10): the plasma state of the open configuration."""
from common import PAGES, __version__, axis, config_json, metric_grid, need_result, page_setup, sci, status, store, svc  # noqa: I001

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.stage1.eedf import EEDF, SHAPES
from plasma_twin.stage1.profile1d import axial_profile
from plasma_twin.stage1.sweep import sweep

page_setup("Results")
st.title("Results (Stage 1)")
result = need_result()
config = st.session_state["config"]
summary = svc.summarise(result)

# ------------------------------------------------------------------ headline values (FR3.1)
metric_grid([
    ("Electron temperature T_e", f"{summary['te_ev']:.2f} eV", ""),
    ("Volume-averaged n_e", f"{sci(summary['ne_volume_mean_m3'])} m⁻³", f"Centre density n₀ = {sci(summary['ne_center_m3'])} m⁻³"),
    ("Gas temperature T_gas", f"{summary['gas_temperature_k']:.1f} K", ""),
    ("Ion flux to electrode Γ_i", f"{sci(summary['ion_flux_electrode_m2_s'])} m⁻² s⁻¹", ""),
    ("RF voltage amplitude", f"{summary['rf_voltage_amplitude_v']:.0f} V", ""),
    ("Sheath width s_m", f"{1e3 * summary['sheath_width_m']:.2f} mm", ""),
    ("DC sheath voltage", f"{summary['dc_sheath_voltage_v']:.0f} V", ""),
    ("Largest balance residual", f"{summary['max_residual']:.1e}", ""),
])
if summary["max_residual"] < 1e-8:
    status("ok", "Every balance closes to better than 1e-8 (ACC-3).")
else:
    status("warn", "A balance did not close to 1e-8; treat this run with care.")

left, right = st.columns(2)
# ------------------------------------------------------------------ densities (FR3.2)
with left:
    st.subheader("Densities")
    st.dataframe([{"Species": k, "Density (m⁻³)": sci(v)} for k, v in summary["densities_m3"].items()],
                 hide_index=True, use_container_width=True)
    if summary["electronegativity"]:
        st.caption(f"Electronegativity α = n₋/n_e = {summary['electronegativity']:.3f}")
# ------------------------------------------------------------------ power shares (FR3.5)
with right:
    st.subheader("Where the absorbed power goes")
    shares = summary["loss_shares_percent"]
    fig = go.Figure(go.Bar(x=list(shares.values()), y=[k.replace("_", " ") for k in shares], orientation="h"))
    st.plotly_chart(axis(fig, "Share of absorbed power P_abs (%)", "Loss channel"), use_container_width=True)

left, right = st.columns(2)
# ------------------------------------------------------------------ EEDF (FR3.3)
with left:
    st.subheader("Electron energy distribution")
    energy = np.linspace(0.01, 25, 400)
    fig = go.Figure()
    for name, shape in SHAPES.items():
        style = None if name == result.inputs.eedf else dict(dash="dot")
        fig.add_trace(go.Scatter(x=energy, y=EEDF(result.te_ev, shape)(energy), name=f"{name}{' (used)' if style is None else ''}",
                                 line=style))
    st.plotly_chart(axis(fig, "Electron energy ε (eV)", "EEDF f(ε) (eV⁻¹)", log_y=True), use_container_width=True)
# ------------------------------------------------------------------ axial profile (FR3.4)
with right:
    st.subheader("Axial electron density profile")
    if config["spatial"] == "0D+1D":
        profile = axial_profile(result)
        fig = go.Figure(go.Scatter(x=1e3 * profile.position_m, y=profile.ne_m3, name="n_e(x)"))
        st.plotly_chart(axis(fig, "Position from mid-gap x (mm)", "Electron density n_e (m⁻³)"), use_container_width=True)
    else:
        status("info", "Choose the 0D+1D spatial model on the chamber screen to see the axial profile.")

# ------------------------------------------------------------------ assumptions (FR3.6)
with st.expander("Regime assumptions of this run (FR3.6)"):
    for line in svc.assumptions(result):
        st.markdown(f"- {line}")

# ------------------------------------------------------------------ sweep (FR3.7)
plan = st.session_state.get("sweep")
if plan:
    st.subheader(f"Sweep over {plan['parameter']}")

    @st.cache_data(show_spinner="Running the sweep...")
    def run_sweep(config_text: str, plan_text: str) -> list[dict]:
        p = json.loads(plan_text)
        points = sweep(svc.to_inputs(json.loads(config_text)), p["parameter"], p["values"])
        return [{"value": pt.value, "te": pt.result.te_ev if pt.solved else None,
                 "ne": pt.result.ne_center_m3 if pt.solved else None, "error": pt.error} for pt in points]

    rows = run_sweep(config_json(config), json.dumps(plan, sort_keys=True))
    ok = [r for r in rows if r["te"] is not None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[r["value"] for r in ok], y=[r["ne"] for r in ok], name="n_e (m⁻³)", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=[r["value"] for r in ok], y=[r["te"] for r in ok], name="T_e (eV)", yaxis="y2", mode="lines+markers"))
    fig.update_layout(yaxis2=dict(title="Electron temperature T_e (eV)", overlaying="y", side="right"))
    st.plotly_chart(axis(fig, plan["parameter"], "Centre electron density n₀ (m⁻³)"), use_container_width=True)
    failed = [r for r in rows if r["te"] is None]
    if failed:
        status("warn", f"{len(failed)} sweep point(s) could not be solved; the others are shown.")
    if st.button("Clear sweep"):
        del st.session_state["sweep"]
        st.rerun()

# ------------------------------------------------------------------ save, export, next (FR3.8-FR3.10)
st.subheader("Save and export")
s1, s2 = st.columns(2)
with s1.form("save_session"):
    note = st.text_input("Note for this session")
    if st.form_submit_button("Save as session (FR3.9)"):
        session_id = store().save(1, config, svc.config_hash(config), {"plasma_state": summary}, note, __version__)
        st.session_state["session_id"] = session_id
        status("ok", f"Saved as {session_id}.")
s2.download_button("Download results (CSV)", svc.results_csv(summary, config), file_name="stage1_results.csv",
                   mime="text/csv")
n1, n2 = st.columns(2)
if n1.button("Open the virtual OES (M4)"):
    st.switch_page(PAGES["oes"])
if n2.button("Open the Langmuir probe (M6)"):
    st.switch_page(PAGES["probe"])
