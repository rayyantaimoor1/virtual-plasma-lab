"""M2 Chamber configuration (FR2.1-FR2.13): every input checked live against envelope.toml."""
from common import PAGES, page_setup, run_and_open_results, status, store, svc  # noqa: I001

import numpy as np
import streamlit as st

from plasma_twin.config.loader import load_envelope

page_setup("Chamber configuration")
st.title("Chamber configuration (Stage 1)")
env = load_envelope()["stage1"]
config = dict(st.session_state["config"])


def linked(field: str, label: str, low: float, high: float, step: float, help_text: str = "") -> None:
    """FR2.1, FR2.4: a slider and a number box that always show the same value."""
    def from_slider() -> None:
        st.session_state[f"n_{field}"] = st.session_state[f"s_{field}"]
        config[field] = st.session_state[f"s_{field}"]

    def from_box() -> None:
        st.session_state[f"s_{field}"] = min(max(st.session_state[f"n_{field}"], low), high)
        config[field] = st.session_state[f"n_{field}"]

    st.session_state.setdefault(f"s_{field}", float(min(max(config[field], low), high)))
    st.session_state.setdefault(f"n_{field}", float(config[field]))
    left, right = st.columns([3, 1])
    left.slider(label, float(low), float(high), step=float(step), key=f"s_{field}", on_change=from_slider, help=help_text)
    right.number_input(label, step=float(step), key=f"n_{field}", on_change=from_box, label_visibility="hidden")
    config[field] = float(st.session_state[f"n_{field}"])


# ------------------------------------------------------------------ presets and reset (FR2.9)
presets = svc.load_presets()
named = store().named_configurations(1)
p1, p2, p3 = st.columns([3, 1, 1])
options = [f"preset: {k}" for k in presets] + [f"saved: {k}" for k in named]
choice = p1.selectbox("Load a preset or a saved configuration", options,
                      format_func=lambda o: presets[o[8:]]["title"] if o.startswith("preset: ") else o[7:])
if p2.button("Load", use_container_width=True):
    loaded = presets[choice[8:]]["config"] if choice.startswith("preset: ") else named[choice[7:]]
    st.session_state["config"] = dict(loaded)
    for key in [k for k in st.session_state if k.startswith(("s_", "n_", "w_"))]:
        del st.session_state[key]
    st.rerun()
if p3.button("Reset to defaults", use_container_width=True):
    st.session_state["config"] = svc.default_config()
    for key in [k for k in st.session_state if k.startswith(("s_", "n_", "w_"))]:
        del st.session_state[key]
    st.rerun()

# ------------------------------------------------------------------ operating parameters
st.subheader("Operating parameters")
linked("rf_power_w", "RF power P (W)", env["rf_power_w"]["min"], env["rf_power_w"]["max"], env["rf_power_w"]["step"])
linked("pressure_mbar", "Pressure p (mbar)", env["pressure_mbar"]["min"], env["pressure_mbar"]["max"], 0.01)
units = svc.pressure_units(config["pressure_mbar"])
st.caption(f"= {units['Pa']:.1f} Pa = {units['mTorr']:.0f} mTorr (FR2.2)")
st.text_input("RF frequency f (MHz)", value=f"{env['fixed']['rf_frequency_mhz']}", disabled=True,
              help="Fixed at 13.56 MHz (FR2.3).")
linked("ar_flow_sccm", "Argon flow Q (sccm)", env["ar_flow_sccm"]["min"], env["ar_flow_sccm"]["max"], 1.0)

st.subheader("Gas mixture")
mixtures = env["options"]["gas_mixtures"]
config["mixture"] = st.radio("Mixture mode (FR2.5)", mixtures, index=mixtures.index(config["mixture"]), horizontal=True,
                             key="w_mixture")
mix = env["admixture_percent_of_ar"]
m1, m2 = st.columns(2)
if "N2" in config["mixture"]:
    config["n2_percent"] = m1.number_input("N₂ flow (% of Ar flow)", float(mix["min"]), float(mix["max"]),
                                          float(config["n2_percent"]), 0.5, key="w_n2")
if "O2" in config["mixture"]:
    config["o2_percent"] = m2.number_input("O₂ flow (% of Ar flow)", float(mix["min"]), float(mix["max"]),
                                          float(config["o2_percent"]), 0.5, key="w_o2")
if config["mixture"] == "Ar+N2+O2":
    status("info", "The supervisor has not yet confirmed whether N₂ and O₂ are added in the same run (Q5).")

st.subheader("Geometry (cm) (FR2.6)")
g1, g2, g3, g4 = st.columns(4)
config["chamber_diameter_cm"] = g1.number_input("Chamber diameter", value=float(config["chamber_diameter_cm"]), step=1.0, key="w_cd")
config["chamber_height_cm"] = g2.number_input("Chamber height", value=float(config["chamber_height_cm"]), step=1.0, key="w_ch")
config["electrode_diameter_cm"] = g3.number_input("Electrode diameter", value=float(config["electrode_diameter_cm"]), step=0.5, key="w_ed")
config["electrode_gap_cm"] = g4.number_input("Electrode gap", value=float(config["electrode_gap_cm"]), step=0.1, key="w_eg")

st.subheader("Model options")
o1, o2 = st.columns(2)
eedfs, spatial = env["options"]["eedf"], env["options"]["spatial"]
config["eedf"] = o1.radio("Electron energy distribution (FR2.7)", eedfs, index=eedfs.index(config["eedf"]), key="w_eedf",
                          help="Druyvesteyn is the supervisor's choice for the low-pressure plasma.")
config["spatial"] = o2.radio("Spatial model (FR2.8)", spatial, index=spatial.index(config["spatial"]), key="w_spatial")

st.session_state["config"] = config

# ------------------------------------------------------------------ live validation (FR2.10)
problems = svc.validate_config(config)
if problems:
    for field, message in problems.items():
        status("error", f"{field}: {message}")
else:
    status("ok", "Every parameter is inside the operating envelope.")

# ------------------------------------------------------------------ run, save, sweep
r1, r2 = st.columns([1, 2])
if r1.button("Run simulation (FR2.11)", type="primary", disabled=bool(problems)):
    run_and_open_results(config)
with r2.form("save_config"):
    name = st.text_input("Save this configuration as (FR2.13)")
    if st.form_submit_button("Save configuration") and not problems:
        try:
            store().save_named_configuration(name, 1, config, svc.config_hash(config))
            status("ok", f"Saved as '{name.strip()}'.")
        except Exception as problem:  # SessionError: empty or duplicate name
            status("error", str(problem))

with st.expander("Parameter sweep (FR2.12)"):
    sweepable = {"rf_power_w": ("RF power P (W)", env["rf_power_w"]), "pressure_mbar": ("Pressure p (mbar)", env["pressure_mbar"]),
                 "ar_flow_sccm": ("Argon flow Q (sccm)", env["ar_flow_sccm"])}
    parameter = st.selectbox("Parameter to sweep", list(sweepable), format_func=lambda k: sweepable[k][0])
    rng = sweepable[parameter][1]
    s1, s2, s3 = st.columns(3)
    start = s1.number_input("From", value=float(rng["min"]))
    end = s2.number_input("To", value=float(rng["max"]))
    points = s3.number_input("Points", 2, env["options"]["sweep_max_points"], 10)
    if st.button("Run sweep", disabled=bool(problems)):
        st.session_state["sweep"] = {"parameter": parameter, "values": np.linspace(start, end, int(points)).tolist()}
        run_and_open_results(config)
