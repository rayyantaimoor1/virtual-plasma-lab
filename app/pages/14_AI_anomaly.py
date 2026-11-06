"""M13 AI physics-relationship anomaly detection (FR13.1-FR13.7, FR17.20, E24)."""
from common import (PAGES, anomaly_log, axis, config_json, is_researcher, measured_store, page_setup,  # noqa: I001
                    probe_settings_text, spectrometer_settings_text, status, store)

import json

import plotly.graph_objects as go
import streamlit as st

from plasma_twin.ai import anomaly
from plasma_twin.ai.registry import ModelUnavailable, Registry
from plasma_twin.oes.spectrum import SpectrometerSettings
from plasma_twin.probe.iv_model import ProbeSettings

page_setup("AI anomaly detection")
st.title("AI anomaly detection")
warning, critical = anomaly.thresholds()
status("info", "The detector compares what the instruments show with what the twin expects at the recorded settings. It flags "
               "a run when the differences (residuals) break the usual physics, even if every value looks normal on its own. "
               f"Normal < {warning:.2f} ≤ Warning < {critical:.2f} ≤ Critical. Stage 1 only: it learned Stage 1 faults.")


@st.cache_resource(max_entries=4)
def load_model(model_id: str):
    return Registry().load(model_id)


@st.cache_data(show_spinner="Comparing with the twin...", max_entries=64)
def check_config(model_id: str, config_text: str, oes_text: str, probe_text: str):
    model, _ = load_model(model_id)
    return anomaly.assess_stage1_config(model, json.loads(config_text), SpectrometerSettings(**json.loads(oes_text)),
                                        ProbeSettings(**json.loads(probe_text)))


models = anomaly.current_models()
if not models:
    status("warn", "No current anomaly detector: none has been trained for this twin version, or it is out of date (E22). "
                   "A Researcher can train one on the AI training screen.")
    if st.button("Go to AI training"):
        st.switch_page(PAGES["ai_training"])
    st.stop()
chosen = st.selectbox("Detector", [c.model_id for c in models])
try:
    model, card = load_model(chosen)
except ModelUnavailable as error:
    status("error", str(error))
    st.stop()

# ------------------------------------------------------------------ what to check (FR13.1)
st.subheader("Check runs")
sessions = [r for r in store().list(stage=1)]
labels = {"open": "the open plasma (with the OES and probe screens' current settings)"}
labels.update({r.session_id: f"session {r.session_id}" + (f": {r.note}" if r.note else "") for r in sessions})
files = measured_store().list(stage=1) if is_researcher() else []
labels.update({f.file_id: f"measured {f.diagnostic.upper()} file {f.file_id}" for f in files})
picked = st.multiselect("Runs to check", list(labels), default=["open"], format_func=labels.get)
st.caption("Saved sessions store no instrument settings, so their diagnostics are regenerated with the default instruments. "
           "A measured file is checked with the OES-only or probe-only detector at its recorded conditions."
           + ("" if is_researcher() else " Measured files are for the Researcher role."))

if st.button("Run anomaly check", type="primary", disabled=not picked):
    results = {}
    for source in picked:
        try:
            if source == "open":
                found = check_config(chosen, config_json(st.session_state["config"]), spectrometer_settings_text(), probe_settings_text())
            elif source.startswith("S-"):
                record = store().get(source)
                defaults = json.dumps(SpectrometerSettings.defaults().__dict__, sort_keys=True)
                found = check_config(chosen, config_json(record.config), defaults, json.dumps(ProbeSettings.defaults().__dict__, sort_keys=True))
            else:
                record = measured_store().get(source)
                found = anomaly.assess_measured(model, measured_store(), record, st.session_state["config"])
        except ValueError as problem:
            status("error", f"{labels[source]}: not checked ({problem}).")
            continue
        results[source] = found
        logged_as = "open plasma" if source == "open" else source
        anomaly_log().add(logged_as, found.detector, chosen, found.score, found.severity, found.likely_cause, found.range_check)
    st.session_state["m13_results"] = results

results = st.session_state.get("m13_results", {})
if results:
    # ------------------------------------------------------------------ checked runs (FR13.3, E24)
    st.dataframe([{"Run": labels.get(s, s), "Detector": a.detector, "Score": round(a.score, 3), "Severity": a.severity,
                   "Likely cause": a.likely_cause, "Range check": a.range_check} for s, a in results.items()],
                 hide_index=True, use_container_width=True)
    flagged = [s for s, a in results.items() if a.severity != "Normal"]
    if flagged:
        status("warn", f"{len(flagged)} run(s) flagged (E24): " + ", ".join(labels.get(s, s) for s in flagged)
               + ". Each is in the anomaly log for review.")
    else:
        status("ok", "Every checked run is Normal.")

    # ------------------------------------------------------------------ explanation (FR13.5)
    st.subheader("Why this score?")
    which = st.selectbox("Run", list(results), format_func=lambda s: labels.get(s, s))
    a = results[which]
    order = sorted(a.contributions, key=a.contributions.get)
    bars = go.Figure(go.Bar(x=[a.contributions[f] for f in order], y=order, orientation="h"))
    st.plotly_chart(axis(bars, "Contribution to the anomaly (shorter isolation path, SHAP)", "Residual"), use_container_width=True)
    st.caption(f"Likely cause: {a.likely_cause}. Residuals: "
               + ", ".join(f"{f} = {v:+.3g}" for f, v in a.residuals.items())
               + ". A residual is the observation minus the twin's expectation (log10 ratios for intensities, volts for the knee position).")

# ------------------------------------------------------------------ score history (FR13.4)
st.subheader("Score history")
entries = anomaly_log().list()
if entries:
    colours = {"Normal": "seagreen", "Warning": "orange", "Critical": "crimson"}
    history = go.Figure(go.Scatter(x=list(range(1, len(entries) + 1)), y=[e.score for e in entries], mode="markers+lines",
                                   marker=dict(color=[colours[e.severity] for e in entries], size=9),
                                   text=[f"{e.source} ({e.severity})" for e in entries], name="anomaly score"))
    for level, name in ((warning, "Warning"), (critical, "Critical")):
        history.add_hline(y=level, line_dash="dot", annotation_text=name)
    st.plotly_chart(axis(history, "Check number (oldest first)", "Anomaly score (-)"), use_container_width=True)
else:
    st.caption("No checks yet.")

# ------------------------------------------------------------------ review and export (FR13.7)
st.subheader("Anomaly log")
if entries:
    st.dataframe([{"#": e.id, "Checked at (UTC)": e.checked_at, "Run": e.source, "Detector": e.detector, "Score": round(e.score, 3),
                   "Severity": e.severity, "Likely cause": e.likely_cause, "Range check": e.range_check,
                   "Reviewed": "yes" if e.reviewed else "no"} for e in reversed(entries)], hide_index=True, use_container_width=True)
    open_flags = [e for e in entries if e.severity != "Normal" and not e.reviewed]
    if open_flags:
        r1, r2 = st.columns([3, 1])
        entry = r1.selectbox("Flagged run to mark as reviewed", [e.id for e in open_flags],
                             format_func=lambda i: next(f"#{e.id} {e.source} ({e.severity})" for e in open_flags if e.id == i))
        if r2.button("Mark reviewed"):
            anomaly_log().mark_reviewed(entry)
            st.rerun()
    st.download_button("Export the anomaly log (CSV)", anomaly_log().to_csv(), "anomaly_log.csv", "text/csv")

# ------------------------------------------------------------------ detector quality (FR13.6, AIQ-2)
with st.expander("How good is this detector? (held-out injected faults)"):
    rows = []
    for split in ("random", "region"):
        m = card.metrics.get(split, {})
        if "model" not in m:
            continue
        for who, label in (("model", "residual detector"), ("baseline", "range check"), ("oes_only", "OES-only detector"),
                           ("probe_only", "probe-only detector")):
            v = m[who]
            rows.append({"Split": split, "Detector": label, "Recall": f"{v['recall']:.0%}", "False alarms": f"{v['false_alarm_rate']:.0%}",
                         **{k.replace("recall_", "").replace("_", " "): f"{v[k]:.0%}" for k in v if k.startswith("recall_")}})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    for split in ("random", "region"):
        p = card.metrics.get(split, {}).get("p_value_vs_range_check")
        if p is not None:
            st.caption(f"{split}: exact McNemar test, residual detector against the range check, p = {p:.2g} "
                       + ("(significantly better)." if p < 0.05 else "(not significantly better)."))
    st.caption("Target (AIQ-2): recall ≥ 90 % at a false-alarm rate ≤ 5 %, significantly above the range check.")
