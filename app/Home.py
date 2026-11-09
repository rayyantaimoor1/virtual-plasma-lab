"""M1 Home: quick start, recent sessions, roles, reference-data status, guide (FR1.1-FR1.6)."""
from common import PAGES, page_setup, run_and_open_results, status, store, svc  # noqa: I001

import streamlit as st

from plasma_twin.reference.loaders import DataStatus, check_reference_data, load_manifest



def ai_model_status() -> dict:
    """FR1.5: the AI models' state; an out-of-date model is shown as such (E22)."""
    from plasma_twin.ai.registry import Registry
    registry = Registry()
    states = [registry.status(c) for c in registry.cards()]
    if not states:
        text = "no models trained yet"
    else:
        text = f"{states.count('current')} current, {states.count('out of date')} out of date, {states.count('missing')} missing"
    return {"Data set": "AI models", "Status": text, "Source": "trained on twin data (AI training screen)"}


page_setup("Home")
st.title("Plasma Digital Twin")
st.caption("A virtual laboratory for a 13.56 MHz argon capacitively coupled plasma, with a virtual spectrometer "
           "and a virtual Langmuir probe.")

# ------------------------------------------------------------------ quick start (FR1.2, USE-1: one click)
presets = svc.load_presets()
st.subheader("Quick start")
if st.button(f"Run the default experiment: {presets['default']['title']}", type="primary"):
    run_and_open_results(presets["default"]["config"])
with st.expander("Other example experiments"):
    choice = st.selectbox("Example", list(presets), format_func=lambda k: presets[k]["title"])
    st.caption(presets[choice]["description"])
    if st.button("Run this example"):
        run_and_open_results(presets[choice]["config"])

# ------------------------------------------------------------------ entry points (FR1.1)
st.subheader("Stages")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("**Stage 1: low-pressure plasma**")
    if st.button("Configure the chamber"):
        st.switch_page(PAGES["chamber"])
with c2:
    st.markdown("**Stage 2: underwater plasma**")
    if st.button("Configure the disinfection"):
        st.switch_page(PAGES["underwater"])
with c3:
    st.markdown("**Diagnostics & data**")
    if st.button("Virtual OES"):
        st.switch_page(PAGES["oes"])
    if st.button("Langmuir probe (Stage 3)"):
        st.switch_page(PAGES["probe"])
    if st.button("Model vs diagnostics"):
        st.switch_page(PAGES["compare"])
    if st.session_state["role"] == "Researcher" and st.button("Measured data and validation"):
        st.switch_page(PAGES["measured"])
with c4:
    st.markdown("**AI module**")
    if st.button("AI spectrum analysis"):
        st.switch_page(PAGES["ai_spectrum"])
    if st.button("AI surrogate and explanations"):
        st.switch_page(PAGES["ai_surrogate"])
    if st.button("AI anomaly detection"):
        st.switch_page(PAGES["ai_anomaly"])
    if st.button("AI recommendations"):
        st.switch_page(PAGES["ai_recommend"])
    if st.button("AI training and models"):
        st.switch_page(PAGES["ai_training"])

# ------------------------------------------------------------------ recent sessions (FR1.3)
st.subheader("Recent sessions")
recent = store().list(limit=3)  # FR1.3: at most three, newest first
if recent:
    st.dataframe([{"Session": r.session_id, "Stage": r.stage, "Configuration": svc.session_summary(r.stage, r.config),
                   "Saved": r.created_at, "Note": r.note} for r in recent], hide_index=True, use_container_width=True)
    if st.button("View all sessions"):
        st.switch_page(PAGES["sessions"])
else:
    st.caption("No saved sessions yet. Save one from the Results screen.")

# ------------------------------------------------------------------ reference data (FR1.5, E1/E6)
st.subheader("Reference data")
states = check_reference_data()
manifest = load_manifest()
words = {DataStatus.OK: "loaded", DataStatus.MISSING: "MISSING", DataStatus.CORRUPT: "CHANGED (checksum mismatch)"}
st.dataframe([{"Data set": manifest[name]["title"], "Status": words[state], "Source": manifest[name]["source"]}
              for name, state in states.items()]
             + [ai_model_status()],
             hide_index=True, use_container_width=True)
if all(s is DataStatus.OK for s in states.values()):
    status("ok", "All reference data sets are present and match their recorded checksums.")
else:
    status("error", "Some reference data are missing or changed; the features that need them are disabled. "
                    "See data/reference/README.md for how to get them.")

# ------------------------------------------------------------------ guide and glossary (FR1.6)
with st.expander("User guide"):
    st.markdown(
        "1. **Configure** the chamber (power, pressure, gas, geometry, electron distribution), or press the quick-start button.\n"
        "2. **Results** shows the plasma state; save it as a session there.\n"
        "3. **Virtual OES** draws the emission spectrum; **OES analysis** reads temperatures from it.\n"
        "4. **Langmuir probe** simulates and analyses a probe curve.\n"
        "5. **Comparison** puts model, OES and probe side by side (±30 %).\n"
        "6. **Sessions** lists, compares and reopens saved runs.")
with st.expander("Glossary"):
    st.markdown(
        "- **T_e** (eV): electron temperature, two-thirds of the mean electron energy.\n"
        "- **n_e** (m⁻³): electron density. **T_gas** (K): gas temperature.\n"
        "- **EEDF**: electron energy distribution function (Maxwellian or Druyvesteyn).\n"
        "- **EEPF**: the EEDF divided by √ε; a straight line on a log scale for a Maxwellian.\n"
        "- **T_exc** (eV): excitation temperature from a Boltzmann plot. Not an electron temperature.\n"
        "- **V_f, V_p** (V): floating and plasma potential of the probe. **λ_D** (m): Debye length.\n"
        "- **OML**: orbital-motion-limited probe theory. **CR model**: collisional-radiative model of excited levels.\n"
        "- **Metastable**: an excited atom that cannot radiate (Ar 1s5, 1s3).\n"
        "- **P_abs** (W): power absorbed by the plasma. **s_m** (m): sheath width. **Γ** (m⁻² s⁻¹): ion flux to a surface.\n"
        "- **E_k** (eV): energy of the upper level k of a line. **g_k** (-): its statistical weight. "
        "**A_ki** (s⁻¹): its transition probability (Einstein coefficient). **n_k** (m⁻³): population of level k.\n"
        "- **r_p** (mm): probe tip radius. **T_eff** (eV): effective electron temperature from the probe's EEPF "
        "(two-thirds of the mean energy).")
