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
    if "te_mae" in values:
        return f"T_e MAE {values['te_mae']:.3f} eV, n_e error {100 * values['ne_median_relative_error']:.0f} %"
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
        fig.add_trace(go.Scatter(x=p[f"{key}_twin"], y=p[f"{key}_model"], mode="markers", name="model"))
        fig.add_trace(go.Scatter(x=p[f"{key}_twin"], y=p[f"{key}_baseline"], mode="markers", name="ridge baseline", marker_symbol="x"))
        low, high = min(p[f"{key}_twin"]), max(p[f"{key}_twin"])
        fig.add_trace(go.Scatter(x=[low, high], y=[low, high], mode="lines", name="perfect", line=dict(dash="dot")))
        column.plotly_chart(axis(fig, f"{label} from the twin ({unit})", f"Predicted {label} ({unit})"), use_container_width=True)
    p_value = card.metrics.get(split, {}).get("p_value")
    if p_value is not None:
        st.caption(f"Paired bootstrap of T_e absolute errors against the ridge baseline: p = {sci(p_value, 2)} "
                   + ("(significantly better)" if p_value < 0.05 else "(not significantly better)") + ".")
with st.expander("Model card"):
    st.json(asdict(card))
with st.expander("Compare logged training runs (MLflow)"):
    runs = registry.runs()
    keep = [c for c in runs.columns if c.startswith(("tags.model_id", "tags.algorithm", "tags.twin_version", "metrics.random.model",
                                                      "metrics.region.model", "metrics.random.p_value", "metrics.region.p_value"))]
    st.dataframe(runs[["start_time"] + keep], hide_index=True, use_container_width=True)
