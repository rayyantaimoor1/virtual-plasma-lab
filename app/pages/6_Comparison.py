"""M7 Diagnostics comparison (FR7.1-FR7.6): model vs OES vs probe within ±30 %."""
from common import axis, cached_run, config_json, need_result, page_setup, probe_settings_text, sci, spectrometer_settings_text, status  # noqa: I001

import json

import plotly.graph_objects as go
import streamlit as st

from plasma_twin.compare.diagnostics import compare, tolerance
from plasma_twin.oes.spectrum import SpectrometerSettings
from plasma_twin.probe.iv_model import ProbeSettings

page_setup("Comparison")
st.title("Diagnostics comparison")
need_result()
config_text = config_json(st.session_state["config"])
fit_both = st.checkbox("Fit OES n_e from the spectrum instead of taking it from the probe",
                       help="The supervisor proposed taking n_e from the probe (Q2); then the OES n_e is dependent.")


@st.cache_data(show_spinner="Running both virtual instruments...", max_entries=16)
def cached_report(config_text: str, probe_text: str, spectrometer_text: str, fit_oes_ne: bool):
    return compare(cached_run(config_text), ProbeSettings(**json.loads(probe_text)),
                   SpectrometerSettings(**json.loads(spectrometer_text)), fit_oes_ne)


report = cached_report(config_text, probe_settings_text(), spectrometer_settings_text(), fit_both)

# ------------------------------------------------------------------ verdict (FR7.3)
judged = [q for q in report.quantities if q.passes is not None]
if judged and all(q.passes for q in judged):
    status("ok", report.verdict + ".")
elif judged:
    status("warn", report.verdict + ".")
else:
    status("info", "No independent, reliable diagnostic value to compare.")
if report.approximate:
    status("warn", "O₂ is present: probe and OES values are approximate and are not counted (LI-4).")

# ------------------------------------------------------------------ side by side (FR7.1, FR7.2)
rows = []
for q in report.quantities:
    rows.append({"Quantity": f"{q.quantity} ({q.unit})", "Method": "model", "Value": sci(q.model), "Deviation": "",
                 "Counted": "", "Result": ""})
    for e in q.entries:
        rows.append({"Quantity": "", "Method": e.method, "Value": sci(e.value), "Deviation": f"{100 * e.deviation:+.1f} %",
                     "Counted": "yes" if e.counted else "no", "Result": ("PASS" if e.passes else "FAIL") + f": {e.note}"})
    if not q.entries:
        rows.append({"Quantity": "", "Method": "(none)", "Value": "", "Deviation": "", "Counted": "",
                     "Result": "no diagnostic measures this here"})
st.dataframe(rows, hide_index=True, use_container_width=True)
if report.probe_slope_te_ev is not None:
    st.caption(f"Shown, not counted: probe slope T_e = {report.probe_slope_te_ev:.2f} eV; "
               f"probe saturation n_e = {sci(report.probe_saturation_ne_m3)} m⁻³.")

# ------------------------------------------------------------------ deviation chart (FR7.4)
labels, values, colours = [], [], []
for q in report.quantities:
    for e in q.entries:
        labels.append(f"{q.quantity} ({e.method})")
        values.append(100 * e.deviation)
        colours.append("#2e7d32" if e.passes else "#c62828")
fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colours, text=[f"{v:+.0f} %" for v in values]))
band = 100 * tolerance()
fig.add_hrect(y0=-band, y1=band, fillcolor="green", opacity=0.08, line_width=0)
st.plotly_chart(axis(fig, "Quantity and diagnostic", "Deviation from model (%)"), use_container_width=True)
st.caption(f"Shaded band: ±{band:.0f} %. Bars are labelled with their value, so colour is not needed to read them (USE-5).")

# ------------------------------------------------------------------ excitation temperature and assumptions (FR7.5, FR7.6)
t_exc = report.excitation_temperature_ev
st.markdown(f"**Excitation temperature:** {f'{t_exc:.3f} eV' if t_exc is not None else 'not readable (slope not negative)'}: "
            f"{report.excitation_note}.")
with st.expander("Assumptions of each method (FR7.6)"):
    for method, items in report.assumptions.items():
        st.markdown(f"**{method}**")
        for item in items:
            st.markdown(f"- {item}")
for warning in report.warnings:
    status("warn", warning)
