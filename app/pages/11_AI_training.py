"""M16 AI training and evaluation (FR16.1-FR16.5): datasets, training, evaluation and the model registry."""
from common import axis, is_researcher, page_setup, sci, status  # noqa: I001

from dataclasses import asdict

import plotly.graph_objects as go
import streamlit as st

from plasma_twin import TWIN_VERSION
from plasma_twin.ai import datasets
from plasma_twin.ai.registry import Registry
from plasma_twin.ai.training import ALGORITHMS, TASKS, train

page_setup("AI training")
st.title("AI training and evaluation")
status("info", f"Every model learns only from data the twin generates (never from measured data, AIQ-5) and is stamped "
               f"with the twin version ({TWIN_VERSION}). A model from another twin version is out of date and never used (E22).")
registry = Registry()

# ------------------------------------------------------------------ training data (FR16.1)
st.subheader("Training data")
settings = datasets.load_settings()
built = {c.dataset_id: c for c in datasets.cards()}
rows = []
for stage in (1, 2):
    dataset_id = datasets.dataset_id(stage)
    card = built.get(dataset_id)
    rows.append({"Dataset": dataset_id, "Stage": stage, "Twin version": TWIN_VERSION, "Runs": card.rows if card else "not built",
                 "Runs per fault": ", ".join(f"{k}: {v}" for k, v in card.rows_per_fault.items()) if card and card.rows_per_fault else "-",
                 "Seed": settings[f"stage{stage}"]["seed"], "Settings locked": settings["lock"]["date"]})
st.dataframe(rows, hide_index=True, use_container_width=True)
st.caption("Noise, fault and split settings are locked in plasma_twin/config/ai_datasets.toml before any training (AIQ-5); "
           "a changed setting would give a new dataset ID.")
missing = [r["Stage"] for r in rows if r["Runs"] == "not built"]
if missing and is_researcher():
    if st.button(f"Build the missing dataset(s) for stage {', '.join(map(str, missing))} (several minutes)"):
        bar = st.progress(0.0)
        for stage in missing:
            frame, card = datasets.build(stage, workers=6, progress=lambda done, total: bar.progress(done / total, f"stage {stage}: {done}/{total}"))
            datasets.save(frame, card)
        st.rerun()
elif missing:
    status("info", "A dataset has not been built yet; a Researcher can build it here (or run scripts/build_ai_datasets.py).")

# ------------------------------------------------------------------ train (FR16.2, E23)
st.subheader("Train a model")
if not is_researcher():
    status("info", "Training is for the Researcher role (E23); everyone can see the models and their metrics below.")
elif datasets.dataset_id(1) not in built:
    status("info", "Build the Stage 1 dataset first.")
else:
    c1, c2 = st.columns(2)
    task = c1.selectbox("Task", list(TASKS), format_func=lambda t: TASKS[t])
    algorithm = c2.selectbox("Algorithm", ALGORITHMS[task])
    st.caption("The baseline is trained alongside, and both are evaluated on the random AND the region split (FR16.3).")
    if st.button("Train", type="primary"):
        with st.spinner("Training the model and its baseline..."):
            frame, card = datasets.load(datasets.dataset_id(1))
            model_card = train(task, algorithm, frame, card, registry)
        status("ok", f"Registered {model_card.model_id}.")

# ------------------------------------------------------------------ registry (FR16.4)
st.subheader("Model registry")
cards = registry.cards()
if not cards:
    st.caption("No models yet.")
    st.stop()


def headline(result: dict, who: str) -> str:
    values = (result or {}).get(who) or {}
    r2 = [v for k, v in values.items() if k.endswith("_r2") and not k.startswith(("te_r2", "ne_r2", "tgas_r2"))]
    if r2 and "te_mae" not in values:  # Phase 11 surrogates: the worst output decides
        errors = [v for k, v in values.items() if k.endswith("_median_relative_error")]
        return f"worst R² {min(r2):.3f}, worst median error {max(errors):.1%}"
    if "te_mae" in values:
        text = f"T_e MAE {values['te_mae']:.3f} eV, n_e error {100 * values['ne_median_relative_error']:.0f} %"
        if "te_coverage" in values:  # Phase 10: 90 % conformal intervals
            text += f", coverage T_e {values['te_coverage']:.0%} / n_e {values['ne_coverage']:.0%}"
        return text
    if "recall" in values:
        return f"recall {values['recall']:.0%}, false alarms {values['false_alarm_rate']:.0%}"
    return "-"


st.dataframe([{"Model": c.model_id, "Task": c.task, "Algorithm": c.algorithm, "Dataset": c.dataset_id, "Twin version": c.twin_version,
               "Held-out (random)": headline(c.metrics.get("random"), "model"), "Held-out (region)": headline(c.metrics.get("region"), "model"),
               "Baseline (random)": headline(c.metrics.get("random"), "baseline"), "Status": registry.status(c)} for c in cards],
             hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ evaluation and model card (FR16.3, FR16.5)
st.subheader("Evaluation and model card")
chosen = st.selectbox("Model", [c.model_id for c in cards])
card = next(c for c in cards if c.model_id == chosen)
predictions = registry.predictions(chosen)
if predictions:
    split = st.radio("Split", list(predictions), horizontal=True, help="Random: interpolation. Region: the held-out corner (extrapolation).")
    p = predictions[split]
    left, right = st.columns(2)
    for column, key, label, unit in ((left, "te", "Electron temperature T_e", "eV"), (right, "ne", "Electron density n_e", "m⁻³")):
        fig = go.Figure()
        bars = None
        if f"{key}_low" in p:  # Phase 10: the 90 % interval of each estimate
            bars = dict(type="data", symmetric=False, array=[h - m for h, m in zip(p[f"{key}_high"], p[f"{key}_model"])],
                        arrayminus=[m - lo for m, lo in zip(p[f"{key}_model"], p[f"{key}_low"])], thickness=1)
        fig.add_trace(go.Scatter(x=p[f"{key}_twin"], y=p[f"{key}_model"], mode="markers", name="model (90 % interval)" if bars else "model",
                                 error_y=bars))
        fig.add_trace(go.Scatter(x=p[f"{key}_twin"], y=p[f"{key}_baseline"], mode="markers", name="ridge baseline", marker_symbol="x"))
        if f"{key}_physics" in p:
            fig.add_trace(go.Scatter(x=p[f"{key}_twin"], y=p[f"{key}_physics"], mode="markers", name="physics line-ratio fit",
                                     marker_symbol="triangle-up", visible="legendonly"))  # its outliers would squash the plot
        low, high = min(p[f"{key}_twin"]), max(p[f"{key}_twin"])
        fig.add_trace(go.Scatter(x=[low, high], y=[low, high], mode="lines", name="perfect", line=dict(dash="dot")))
        fig = axis(fig, f"{label} from the twin ({unit})", f"Predicted {label} ({unit})", log_y=key == "ne")
        if key == "ne":
            fig.update_xaxes(type="log")
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), margin=dict(t=60), height=440)
        column.plotly_chart(fig, use_container_width=True)
    if any(k.endswith("_physics") for k in p):
        st.caption("Click 'physics line-ratio fit' in a legend to show the physics points; some of its fits run away to 6-9 eV "
                   "at low pressure, which squashes the plot.")
    result = card.metrics.get(split, {})
    p_value = result.get("p_value")
    if p_value is not None:
        st.caption(f"Paired bootstrap of T_e absolute errors against the ridge baseline: p = {sci(p_value, 2)} "
                   + ("(significantly better)" if p_value < 0.05 else "(not significantly better)") + ".")
    comparisons = [(name, label) for name, label in (("te_vs_ridge", "T_e vs ridge"), ("ne_vs_ridge", "n_e vs ridge"),
                                                     ("te_vs_physics", "T_e vs physics fit"), ("ne_vs_physics", "n_e vs physics fit"),
                                                     ("tgas_vs_mean", "T_gas vs training mean")) if f"p_value_{name}" in result]
    if comparisons:
        st.dataframe([{"Comparison": label, "p (model better)": sci(result[f"p_value_{name}"], 2),
                       "95 % interval of mean error difference": f"{sci(result[f'ci_{name}_low'], 2)} to {sci(result[f'ci_{name}_high'], 2)}",
                       "Verdict": "significantly better" if result[f"p_value_{name}"] < 0.05 else "not significantly better"}
                      for name, label in comparisons], hide_index=True, use_container_width=True)
        st.caption("Errors: T_e in eV, n_e as |Δ log10 n_e|, T_gas in K. A negative interval means the model's errors are smaller "
                   "(scipy.stats.bootstrap, paired). The physics fit is given the known pressure and mixture.")
with st.expander("Model card"):
    st.json(asdict(card))
with st.expander("Compare logged training runs (MLflow)"):
    runs = registry.runs()
    keep = [c for c in runs.columns if c.startswith(("tags.model_id", "tags.algorithm", "tags.twin_version", "metrics.random.model",
                                                      "metrics.region.model", "metrics.random.p_value", "metrics.region.p_value"))]
    st.dataframe(runs[["start_time"] + keep], hide_index=True, use_container_width=True)
