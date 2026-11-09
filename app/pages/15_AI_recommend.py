"""M14 AI recommendations (FR14.1-FR14.8, FR17.21, E25, E26): settings for a goal, every candidate verified by the twin."""
from common import PAGES, axis, config_json, page_setup, range_help, status  # noqa: I001

import json

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.ai import recommend as rc
from plasma_twin.ai import surrogate as sg
from plasma_twin.ai.registry import ModelUnavailable
from plasma_twin.config.loader import load_envelope

page_setup("AI recommendations")
st.title("AI recommendations (inverse design)")
status("info", "State a goal and the AI proposes settings to reach it. The search runs on the fast surrogate, then the best "
               "three candidates are re-run through the digital twin. Only twin-verified outcomes are shown and ranked (CON-12).")


@st.cache_resource(max_entries=4)
def load_model(model_id: str):
    from plasma_twin.ai.registry import Registry
    return Registry().load(model_id)[0]


@st.cache_data(show_spinner="Running the twin for the open configuration...", max_entries=16)
def twin_of(stage: int, config_text: str):
    return rc.twin_outcome(stage, json.loads(config_text))


def fmt(output: str, value: float) -> str:
    return f"{value:.3g}" if output.startswith(("ne_", "line_")) else f"{value:.2f}"


def setting_text(name: str, value: float) -> str:
    if name == "water_vapour":
        return "yes" if value >= 0.5 else "no"
    if name == "gap_mm":
        return f"{value:.0f}"
    return f"{value:.3g}"


# ------------------------------------------------------------------ goal (FR14.1)
stage = st.radio("Stage", [1, 2], horizontal=True, key="m14_stage",
                 format_func=lambda s: "Stage 1 (argon CCP)" if s == 1 else "Stage 2 (underwater disinfection)")
cards = sg.current_models(stage)  # the current XGBoost surrogate first (Phase 11 default)
if not cards:
    status("warn", "No current surrogate for this stage: none has been trained for this twin version, or it is out of date (E22). "
                   "The recommender searches on the Phase 11 surrogate, so a Researcher must train one on the AI training screen.")
    if st.button("Go to AI training"):
        st.switch_page(PAGES["ai_training"])
    st.stop()
model_id = cards[0].model_id
try:
    model = load_model(model_id)
except ModelUnavailable as error:
    status("error", str(error))
    st.stop()
st.caption(f"Searching on surrogate {model_id} ({model.algorithm}).")
open_config = dict(st.session_state["config" if stage == 1 else "config2"])
cost_label, cost_unit = rc.COST_LABEL[stage]

objectives = [k for k, o in rc.OBJECTIVES.items() if o.stage == stage]
g1, g2 = st.columns([3, 2])
objective = g1.selectbox("Objective", objectives, format_func=lambda k: rc.OBJECTIVES[k].label)
if objective == "ne_target":
    goal = rc.Goal(objective, target=g2.number_input("Target n_e (10¹⁶ m⁻³)", 0.01, 1000.0, 3.0, 0.5, help=range_help(0.01, 1000, "× 10¹⁶ m⁻³")) * 1e16)
elif objective == "tgas_target":
    goal = rc.Goal(objective, target=g2.number_input("Target T_gas (K)", 250.0, 600.0, 303.0, 0.5, help=range_help(250, 600, "K")))
elif objective == "line_max":
    lines = [o for o in sg.OUTPUTS[1] if o.name.startswith("line_")]
    goal = rc.Goal(objective, line=g2.selectbox("Line", [o.name for o in lines], format_func=lambda n: rc.surrogate_label(n)))
elif objective == "lr_least_energy":
    goal = rc.Goal(objective, target=g2.number_input(f"Target log reduction ({open_config.get('organism', 'E. coli')})",
                                                     0.1, 15.0, 3.0, 0.5, help=range_help(0.1, 15, "log")))
else:
    goal = rc.Goal(objective, budget_kj_l=g2.number_input("Energy budget (kJ/L)", 0.001, 10000.0, 1.0, 0.5, format="%.3f", help=range_help(0.001, 10000, "kJ/L")))

# ------------------------------------------------------------------ fixed settings (FR14.2)
allowed = rc.searchable(stage, open_config)
fixed = set(st.multiselect("Keep fixed at the open configuration's value", allowed,
                           default=[n for n in allowed if n in rc.default_fixed(stage)], format_func=sg.INPUT_LABELS.get))
always = (f"gas mixture {open_config.get('mixture')}" if stage == 1
          else f"power share {open_config.get('power_share'):.3g} (the model's uncertainty, not a knob) and the voltage, "
               "water chemistry, organism and initial count")
st.caption(f"Always kept: {always}. Every other setting is searched inside the operating envelope, narrowed to the "
           "surrogate's training range" + (" (pulse width 2–40 µs, so the duty cycle stays below 40 %)." if stage == 2 else "."))

if st.button("Find settings", type="primary"):
    try:
        with st.status("Finding settings...", expanded=True) as box:
            found = rc.recommend(goal, model, open_config, fixed, model_id, progress=box.write)
            box.update(label=f"Done in {found.seconds:.1f} s", state="complete", expanded=False)
        st.session_state["m14_result"] = found
    except ValueError as problem:
        status("error", str(problem))

found = st.session_state.get("m14_result")
if found is not None and found.stage == stage:
    goal_now = found.goal
    st.subheader("Ranked candidates (every outcome re-simulated by the twin)")
    st.caption(f"Goal: {goal_now.describe()}. Searched {found.evaluated:,} settings on the surrogate; the top "
               f"{len(found.candidates) + len(found.dropped)} were re-simulated by the digital twin "
               f"({found.seconds:.1f} s in all, E25).")
    for warning in found.warnings:
        status("warn", f"Outside what the surrogate learned: {warning}. Its search may be off there; the twin values are still exact.")
    if found.dropped:
        status("warn", f"{len(found.dropped)} candidate(s) dropped because the twin run failed (never shown as advice): "
               + "; ".join(d["reason"] for d in found.dropped))
    if not found.candidates:
        status("error", "No candidate could be verified by the twin, so there is no recommendation.")
    else:
        met = sum(c.met for c in found.candidates)
        if found.reachable:
            status("ok", f"The twin confirms the goal for {met} of {len(found.candidates)} candidates.")
        else:
            hint = ""
            if goal_now.objective == "lr_least_energy":
                cap = float(np.log10(open_config["initial_count_cfu_ml"] * open_config["water_volume_ml"]))
                hint = (f" In {open_config['water_volume_ml']:g} mL at most {cap:.2f} log is possible: one live cell left in the "
                        "whole volume." if "water_volume_ml" in fixed else "")
            status("warn", "No setting was found inside the envelope that reaches this goal (E26). The closest twin-verified "
                           "option is listed first." + hint)
        output = goal_now.output
        label = rc.surrogate_label(output)
        rows = []
        for n, c in enumerate(found.candidates, start=1):
            row = {"#": n, **{sg.INPUT_LABELS[k]: setting_text(k, v) for k, v in c.searched.items()},
                   f"{label}, surrogate": fmt(output, c.surrogate_value), f"{label}, twin-verified": fmt(output, c.value),
                   f"{cost_label} ({cost_unit})": f"{c.cost:.3g}", "Goal met (twin)": "yes" if c.met else "no",
                   "Note": f"repaired by the twin ({c.repair_runs} twin runs)" if c.repair_runs else ""}
            rows.append(row)
        st.dataframe(rows, hide_index=True, use_container_width=True)

        current = None
        try:
            current = twin_of(stage, config_json(open_config))
        except Exception as problem:  # noqa: BLE001 - the open configuration may be invalid; the candidates stand alone
            st.caption(f"The open configuration could not be run for comparison ({problem}).")
        best = found.best
        if current is not None and best.met and goal_now.objective in ("lr_least_energy", "ne_target", "tgas_target"):
            saving = 1 - best.cost / current["cost"] if current["cost"] else 0.0
            compared = f"{saving:.0%} less than" if saving > 0 else "against"
            st.caption(f"Candidate 1 uses {best.cost:.3g} {cost_unit}, {compared} the open configuration's {current['cost']:.3g} "
                       f"{cost_unit} (the twin gives the open configuration {label.lower()} {fmt(output, current[output])}).")

        # ------------------------------------------------------------------ energy chart (FR14.5)
        chart = go.Figure()
        chart.add_trace(go.Scatter(x=[c.cost for c in found.candidates], y=[c.value for c in found.candidates],
                                   mode="markers+text", text=[f"#{n}" for n in range(1, len(found.candidates) + 1)],
                                   textposition="top center", marker=dict(size=12, color="seagreen"), name="candidates (twin)"))
        if current is not None:
            chart.add_trace(go.Scatter(x=[current["cost"]], y=[current[output]], mode="markers", name="open configuration (twin)",
                                       marker=dict(size=12, symbol="diamond", color="steelblue")))
        if goal_now.target is not None:
            chart.add_hline(y=goal_now.target, line_dash="dot", annotation_text="target")
        if goal_now.budget_kj_l is not None:
            chart.add_vline(x=goal_now.budget_kj_l, line_dash="dot", annotation_text="budget")
        chart.update_xaxes(type="log" if stage == 2 else "linear")
        chart.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
        unit = next(o.unit for o in sg.OUTPUTS[stage] if o.name == output)
        st.plotly_chart(axis(chart, f"{cost_label} ({cost_unit})", f"{label} ({unit})", log_y=output.startswith(("ne_", "line_"))),
                        use_container_width=True)

        # ------------------------------------------------------------------ apply or save (FR14.7)
        a1, a2 = st.columns([2, 1])
        pick = a1.selectbox("Candidate to apply", list(range(1, len(found.candidates) + 1)), format_func=lambda n: f"candidate {n}")
        if a1.button("Apply to the configuration screen"):
            chosen = dict(found.candidates[pick - 1].config)
            if stage == 1:
                st.session_state["config"] = chosen
                st.session_state["has_run"] = False
                prefixes, page = ("s_", "n_", "w_"), PAGES["chamber"]
            else:
                st.session_state["config2"] = chosen
                st.session_state["has_run2"] = False
                prefixes, page = ("u_",), PAGES["underwater"]
            for key in [k for k in st.session_state if k.startswith(prefixes)]:
                del st.session_state[key]
            st.switch_page(page)
        a2.download_button("Save the recommendation (JSON)", found.to_json(), "recommendation.json", "application/json")
        st.caption("Applying fills the configuration screen; nothing runs until you press Run there.")

# ------------------------------------------------------------------ what-if (FR14.6)
st.subheader("What-if: change one setting of the open configuration")
names = [n for n in allowed if n != "water_vapour"] if stage == 2 else allowed
w1, w2 = st.columns(2)
setting = w1.selectbox("Setting", names, format_func=sg.INPUT_LABELS.get, key=f"m14_whatif_{stage}")
if setting == "gap_mm":
    value = float(w2.selectbox("New value", load_envelope()["stage2"]["options"]["electrode_gap_mm"]))
else:
    low, high = rc.bounds(stage)[setting]
    if stage == 2 and setting == "width_us":
        high = 1000.0  # the run rule (E5), not the training range, limits a what-if
    current_value = float(open_config.get(setting, low))
    value = w2.number_input(f"New {sg.INPUT_LABELS[setting]}", float(low), float(high), min(max(current_value, float(low)), float(high)),
                            key=f"m14_value_{stage}_{setting}", help=range_help(low, high))
if st.button("Re-simulate with the twin"):
    try:
        st.session_state["m14_whatif"] = (stage, setting, value, rc.what_if(stage, open_config, setting, value))
    except ValueError as problem:
        status("error", f"This change cannot run: {problem}")
whatif = st.session_state.get("m14_whatif")
if whatif and whatif[0] == stage:
    _, name, new, rows = whatif
    shown = (lambda r, v: f"{v:.2f}" if r["unit"] == "K" else f"{v:.3g}")  # three significant figures; tiny OH stays visible
    st.dataframe([{"Output": r["output"], "Unit": r["unit"], "Open configuration": shown(r, r["current"]),
                   f"{sg.INPUT_LABELS[name]} = {setting_text(name, new)}": shown(r, r["changed"])}
                  for r in rows], hide_index=True, use_container_width=True)
    st.caption("Both columns are re-simulated by the digital twin (not an estimate).")

# ------------------------------------------------------------------ benchmark (AIQ-4)
with st.expander("How good is the recommender? (benchmark of 30 reachable goals)"):
    bench = rc.load_benchmark()
    if bench is None:
        st.caption("The benchmark has not been run here (scripts/benchmark_recommendations.py).")
    else:
        s = bench["summary"]
        st.markdown(f"The twin confirmed **{s['met']} of {s['goals']}** goals ({s['success_rate']:.0%}); "
                    f"{s['met_without_repair']} without the twin repair. Longest recommendation: {s['longest_seconds']:.1f} s.")
        st.dataframe([{"Goal": r["goal"], "Stage": r["stage"], "Objective": rc.OBJECTIVES[r["objective"]].label,
                       "Target": f"{r['target']:.4g}", "Twin value": f"{r['twin_value']:.4g}" if r["twin_value"] is not None else "",
                       "Cost": f"{r['cost']:.3g}" if r["cost"] is not None else "", "Met": "yes" if r["met"] else "no",
                       "Met without repair": "yes" if r["met_without_repair"] else "no", "Seconds": round(r["seconds"], 1)}
                      for r in bench["rows"]], hide_index=True, use_container_width=True)
        st.caption("Targets are the twin's own values at settings drawn with a fixed seed, so every goal is reachable. "
                   "Target (AIQ-4): the twin confirms ≥ 90 % of them.")
        energy = s.get("stage2_energy_not_above_drawn")
        if energy:
            st.caption(f"Energy check (reported, not a pass mark): {energy} Stage 2 recommendations use no more energy than "
                       "the settings that defined their target. The search aim is capped just below the one-cell limit "
                       "(dated amendment, BUILD_STEPS.md, Phase 13).")
