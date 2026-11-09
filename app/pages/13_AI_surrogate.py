"""M15 AI surrogate and explainability (FR15.1-FR15.6, FR17.22, E27): fast maps, SHAP, and a check with the twin."""
from common import PAGES, axis, page_setup, range_help, sci, status  # noqa: I001

import json
import time

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.ai import surrogate as sg
from plasma_twin.ai.registry import ModelUnavailable, Registry

page_setup("AI surrogate")
st.title("AI surrogate and explanations")
status("info", "The surrogate is a fast learned copy of the twin, for exploring many settings at once. Every value it gives is "
               "labelled \"surrogate\". Any point you want to rely on can be re-run through the twin; if the two differ by more "
               f"than {sg.tolerance():.0%}, the twin value is the one shown (E27).")


@st.cache_resource(max_entries=4)
def load_model(model_id: str):
    return Registry().load(model_id)


@st.cache_data(show_spinner="Running the twin...", max_entries=32)
def cached_check(model_id: str, config_text: str):
    model, _ = load_model(model_id)
    return sg.check_with_twin(model, json.loads(config_text))


# ------------------------------------------------------------------ stage, model and output (FR15.1)
c1, c2 = st.columns(2)
stage = c1.radio("Stage", [1, 2], horizontal=True, format_func=lambda s: "Stage 1 (argon CCP)" if s == 1 else "Stage 2 (underwater)")
models = sg.current_models(stage)
if not models:
    status("warn", "No current surrogate for this stage: none has been trained for this twin version, or it is out of date (E22). "
                   "A Researcher can train one on the AI training screen.")
    if st.button("Go to AI training"):
        st.switch_page(PAGES["ai_training"])
    st.stop()
chosen = c2.selectbox("Surrogate", [c.model_id for c in models],
                      format_func=lambda m: f"{m} ({next(c.algorithm for c in models if c.model_id == m)})")
try:
    model, card = load_model(chosen)
except ModelUnavailable as error:
    status("error", str(error))
    st.stop()
outputs = {o.name: o for o in model.outputs}
output = outputs[st.selectbox("Output", list(outputs), format_func=lambda n: f"{outputs[n].label} ({outputs[n].unit})")]
k_out = list(outputs).index(output.name)

open_config = dict(st.session_state["config" if stage == 1 else "config2"])
open_x = sg.features(stage, [open_config])[0]
differs = sg.untrained_settings(stage, open_config)
if differs:
    status("warn", "The surrogate learned only with " + ", ".join(differs) + "; the open configuration differs there, so its "
                   "values are an extrapolation. Check any point you rely on with the twin.")
outside = [sg.INPUT_LABELS[n] for n, v, lo, hi in zip(model.inputs, open_x, model.input_low, model.input_high) if not lo <= v <= hi]
if outside:
    status("warn", "Outside the surrogate's training range: " + ", ".join(outside) + ".")

# ------------------------------------------------------------------ fast map (FR15.2)
st.subheader("Fast map (surrogate)")
choosable = [n for n in model.inputs if n != "water_vapour"]
m1, m2 = st.columns(2)
x_name = m1.selectbox("Across", choosable, index=0, format_func=sg.INPUT_LABELS.get)
y_name = m2.selectbox("Up", [n for n in choosable if n != x_name], index=0, format_func=sg.INPUT_LABELS.get)
ix, iy = model.inputs.index(x_name), model.inputs.index(y_name)
xs = np.linspace(model.input_low[ix], model.input_high[ix], 25)
ys = np.linspace(model.input_low[iy], model.input_high[iy], 25)
grid = np.tile(open_x, (len(xs) * len(ys), 1))
grid[:, ix] = np.tile(xs, len(ys))
grid[:, iy] = np.repeat(ys, len(xs))
started = time.perf_counter()
values = model.predict(grid)[:, k_out].reshape(len(ys), len(xs))
seconds = time.perf_counter() - started
shown = np.log10(values + output.floor) if output.log else values
title = f"log10 {output.label} ({output.unit})" if output.log else f"{output.label} ({output.unit})"
fig = go.Figure(go.Heatmap(x=xs, y=ys, z=shown, colorbar=dict(title="surrogate"), hovertemplate="%{z:.3g}<extra>surrogate</extra>"))
flags = [f for f in st.session_state.get("m15_checks", []) if f["stage"] == stage and f["x"] == x_name and f["y"] == y_name
         and f["output"] == output.name]
for disagrees, symbol, name in ((False, "circle-open", "twin agrees"), (True, "x", "twin disagrees (E27)")):
    picked = [f for f in flags if f["disagrees"] == disagrees]
    if picked:
        fig.add_trace(go.Scatter(x=[f["xv"] for f in picked], y=[f["yv"] for f in picked], mode="markers", name=name,
                                 marker=dict(symbol=symbol, size=14, color="white" if not disagrees else "red", line=dict(width=2))))
fig.add_trace(go.Scatter(x=[open_x[ix]], y=[open_x[iy]], mode="markers", name="open configuration",
                         marker=dict(symbol="star", size=14, color="gold")))
fig = axis(fig, sg.INPUT_LABELS[x_name], sg.INPUT_LABELS[y_name])
fig.update_layout(title=f"Surrogate: {title}", height=460, legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, use_container_width=True)
twin_s = card.metrics.get("random", {}).get("twin_seconds")
st.caption(f"{grid.shape[0]} surrogate points in {seconds * 1000:.0f} ms"
           + (f"; the twin would need about {grid.shape[0] * twin_s:.0f} s." if twin_s else ".")
           + " Every other input is held at the open configuration's value.")

# ------------------------------------------------------------------ check with twin (FR15.3, FR17.22, E27)
st.subheader("Check a point with the twin")
p1, p2, p3 = st.columns([2, 2, 1])
xv = p1.number_input(sg.INPUT_LABELS[x_name], float(model.input_low[ix]), float(model.input_high[ix]), float(np.clip(open_x[ix], model.input_low[ix], model.input_high[ix])),
                     help=range_help(model.input_low[ix], model.input_high[ix], extra="The surrogate's training range."))
yv = p2.number_input(sg.INPUT_LABELS[y_name], float(model.input_low[iy]), float(model.input_high[iy]), float(np.clip(open_x[iy], model.input_low[iy], model.input_high[iy])),
                     help=range_help(model.input_low[iy], model.input_high[iy], extra="The surrogate's training range."))
if p3.button("Check with twin", type="primary"):
    point = open_x.copy()
    point[ix], point[iy] = xv, yv
    config = sg.config_from_features(stage, point, base=open_config)
    checks = cached_check(chosen, json.dumps(config, sort_keys=True, default=str))
    st.session_state["m15_last"] = (stage, chosen, checks)
    this = next(c for c in checks if c.output == output.name)
    st.session_state.setdefault("m15_checks", []).append({"stage": stage, "x": x_name, "y": y_name, "output": output.name,
                                                          "xv": xv, "yv": yv, "disagrees": this.disagrees})
    st.rerun()
last = st.session_state.get("m15_last")
if last and last[0] == stage and last[1] == chosen:
    checks = last[2]
    this = next(c for c in checks if c.output == output.name)
    if this.disagrees:
        status("warn", f"Surrogate and twin differ by {this.relative_difference:.1%} for {this.label} (more than {sg.tolerance():.0%}, E27). "
                       f"The twin value is shown: {sci(this.twin)} {this.unit}. The point is flagged on the map.")
    else:
        status("ok", f"Surrogate and twin agree within {sg.tolerance():.0%} for {this.label} ({this.relative_difference:.1%}).")
    st.dataframe([{"Output": c.label, "Unit": c.unit, "Surrogate": sci(c.surrogate), "Twin": sci(c.twin),
                   "Difference": f"{c.relative_difference:.1%}" if np.isfinite(c.relative_difference) else "twin is 0",
                   "Value shown": sci(c.shown) + (" (twin, E27)" if c.disagrees else " (surrogate)")} for c in checks],
                 hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ SHAP (FR15.4, FR15.5)
scale = f"log10 {output.label}" if output.log else f"{output.label} ({output.unit})"
g, loc = st.columns(2)
with g:
    st.subheader("Global importance (SHAP)")
    importance = card.metrics.get("random", {}).get("shap_importance", {}).get(output.name, {})
    if importance:
        order = sorted(importance, key=importance.get)
        bars = go.Figure(go.Bar(x=[importance[n] for n in order], y=[sg.INPUT_LABELS[n] for n in order], orientation="h"))
        st.plotly_chart(axis(bars, f"Mean |SHAP| on {scale}", "Input"), use_container_width=True)
        st.caption("Average size of each input's contribution over the held-out twin runs (random split).")
with loc:
    st.subheader("Why this value? (open configuration)")
    contributions, expected = model.shap(open_x[None, :])
    contribution = contributions[0, :, k_out]
    order = np.argsort(np.abs(contribution))
    bars = go.Figure(go.Bar(x=contribution[order], y=[sg.INPUT_LABELS[model.inputs[j]] for j in order], orientation="h"))
    st.plotly_chart(axis(bars, f"SHAP contribution to {scale}", "Input"), use_container_width=True)
    learned = model.predict_learned(open_x[None, :])[0, k_out]
    st.caption(f"Average prediction {expected[k_out]:.4g} + contributions {contribution.sum():+.4g} = surrogate {learned:.4g} "
               f"({'on the log10 scale' if output.log else 'in ' + output.unit}; the contributions add up exactly).")
    st.metric(f"{output.label} (surrogate)", f"{sci(model.predict(open_x[None, :])[0, k_out])} {output.unit}")

# ------------------------------------------------------------------ accuracy (FR15.6, AIQ-3)
with st.expander("Surrogate accuracy and speed (held-out twin runs)", expanded=False):
    rows = []
    for o in model.outputs:
        row = {"Output": f"{o.label} ({o.unit})"}
        for split in ("random", "region"):
            m = card.metrics.get(split, {}).get("model", {})
            if m:
                row[f"R² {split}"] = f"{m[f'{o.name}_r2']:.4f}"
                row[f"Median error {split}"] = f"{m[f'{o.name}_median_relative_error']:.2%}"
        base = card.metrics.get("random", {}).get("baseline", {})
        if base:
            row["R² ridge baseline (random)"] = f"{base[f'{o.name}_r2']:.3f}"
        rows.append(row)
    st.dataframe(rows, hide_index=True, use_container_width=True)
    r = card.metrics.get("random", {})
    if "speedup_map" in r:
        st.caption(f"Twin: {r['twin_seconds']:.3f} s per run. Surrogate: {r['surrogate_seconds_per_map_point'] * 1e6:.0f} µs per point in a "
                   f"{sg.MAP_POINTS}-point map ({r['speedup_map']:,.0f}× faster) and {r['surrogate_seconds_single_call'] * 1000:.1f} ms for one "
                   f"configuration on its own ({r['speedup_single_call']:,.0f}× faster). Target: R² ≥ 0.98, median error ≤ 5 %, ≥ 100× (AIQ-3). "
                   "R² is on the learned scale (log10 for wide-range outputs).")
    if stage == 2:
        st.caption("Every Stage 2 training run reaches the one-cell cap, so log reduction follows the water volume only: its score "
                   "says nothing about kill kinetics.")
