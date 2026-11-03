"""M11 Sessions, basic (FR11.1-FR11.4): list, search, open, compare and delete saved runs."""
from common import PAGES, __version__, axis, page_setup, sci, status, store, svc  # noqa: I001

import csv
import io

import plotly.graph_objects as go
import streamlit as st

from plasma_twin.storage.sessions import SessionError

page_setup("Sessions")
st.title("Saved sessions")

f1, f2 = st.columns([1, 3])
stage = f1.selectbox("Stage", ["All", 1, 2])
search = f2.text_input("Search notes and configurations")
records = store().list(stage=None if stage == "All" else stage, search=search)

if not records:
    status("info", "No sessions match. Save a run from the Results screen.")
    st.stop()


def row(r):
    state = r.results.get("plasma_state", {})
    return {"Session": r.session_id, "Stage": r.stage,
            "Configuration": f"{r.config.get('mixture', '')}, {r.config.get('rf_power_w', '')} W, {r.config.get('pressure_mbar', '')} mbar",
            "T_e (eV)": f"{state.get('te_ev', float('nan')):.2f}", "n_e (m⁻³)": sci(state.get("ne_center_m3", float("nan"))),
            "Saved": r.created_at, "Note": r.note, "Model version": r.model_version}


st.dataframe([row(r) for r in records], hide_index=True, use_container_width=True)
ids = [r.session_id for r in records]
chosen = st.multiselect("Select sessions", ids)
c1, c2, c3 = st.columns(3)

# ------------------------------------------------------------------ open (FR11.3)
if c1.button("Open selected", disabled=len(chosen) != 1):
    record = store().get(chosen[0])
    if record.model_version != __version__:
        status("warn", f"{record.session_id} was saved with model version {record.model_version}; this is {__version__}. "
                       "Its configuration is reopened and re-run with the current model.")
    st.session_state["config"] = {**svc.default_config(), **record.config}
    st.session_state["has_run"] = True
    st.session_state["session_id"] = record.session_id
    for key in [k for k in st.session_state if k.startswith(("s_", "n_", "w_"))]:
        del st.session_state[key]
    st.switch_page(PAGES["results"])

# ------------------------------------------------------------------ compare (FR11.2)
if c2.button("Compare selected", disabled=not 2 <= len(chosen) <= 5):
    try:
        group = store().compare(chosen)
        fig = go.Figure()
        for r in group:
            state = r.results.get("plasma_state", {})
            fig.add_trace(go.Bar(name=r.session_id, x=["T_e (eV)"], y=[state.get("te_ev")]))
        st.plotly_chart(axis(fig, "Quantity", "Electron temperature T_e (eV)"), use_container_width=True)
        fig = go.Figure([go.Bar(name=r.session_id, x=["n₀"], y=[r.results.get("plasma_state", {}).get("ne_center_m3")])
                         for r in group])
        st.plotly_chart(axis(fig, "Quantity", "Centre electron density n₀ (m⁻³)"), use_container_width=True)
    except SessionError as problem:
        status("error", str(problem))

# ------------------------------------------------------------------ delete with confirmation (FR11.4)
if c3.button("Delete selected", disabled=not chosen):
    st.session_state["confirm_delete"] = list(chosen)
pending = st.session_state.get("confirm_delete")
if pending:
    status("warn", f"Delete {', '.join(pending)} permanently? This cannot be undone.")
    y, n = st.columns(2)
    if y.button("Yes, delete permanently", type="primary"):
        count = store().delete(pending, confirmed=True)
        del st.session_state["confirm_delete"]
        status("ok", f"Deleted {count} session(s).")
        st.rerun()
    if n.button("Cancel"):
        del st.session_state["confirm_delete"]
        st.rerun()

# ------------------------------------------------------------------ export (FR11.5, CSV only here)
buffer = io.StringIO()
fields = list(row(records[0]))
writer = csv.DictWriter(buffer, fieldnames=fields)
writer.writeheader()
writer.writerows(row(r) for r in records if not chosen or r.session_id in chosen)
st.download_button("Download the listed (or selected) sessions (CSV)", buffer.getvalue(), file_name="sessions.csv", mime="text/csv")
st.caption("PDF reports and the rule for non-citable measured data come with data import in Phase 8.")
