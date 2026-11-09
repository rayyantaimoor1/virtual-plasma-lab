"""M2 Chamber configuration (FR2.1-FR2.13): every input checked live against envelope.toml."""
from common import PAGES, page_setup, range_help, run_and_open_results, status, store, svc  # noqa: I001

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
# FR2.5: a gas not in the mixture keeps its field, disabled and showing 0; its stored value comes back if re-added.
for column, gas, field, label in ((m1, "N2", "n2_percent", "N₂ flow (% of Ar flow)"), (m2, "O2", "o2_percent", "O₂ flow (% of Ar flow)")):
    if gas in config["mixture"]:
        config[field] = column.number_input(label, float(mix["min"]), float(mix["max"]), float(config[field]), 0.5, key=f"w_{gas}",
                                            help=range_help(mix["min"], mix["max"], "% of the Ar flow"))
    else:
        column.number_input(label, value=0.0, disabled=True, key=f"w_{gas}_off",
                            help=range_help(mix["min"], mix["max"], "% of the Ar flow", "Choose a mixture with this gas to set it."))
flows = svc.admixture_flows_sccm(config)
st.caption(f"Resulting admixture flows: N₂ {flows['N2']:.1f} sccm, O₂ {flows['O2']:.1f} sccm (FR2.5)")
if config["mixture"] == "Ar+N2+O2":
    status("info", "The supervisor has not yet confirmed whether N₂ and O₂ are added in the same run (Q5).")

st.subheader("Geometry (cm) (FR2.6)")
g1, g2, g3, g4 = st.columns(4)
config["chamber_diameter_cm"] = g1.number_input("Chamber diameter (cm)", value=float(config["chamber_diameter_cm"]), step=1.0, key="w_cd",
                                                  help="Allowed: greater than 0 cm, and larger than the electrode diameter.")
config["chamber_height_cm"] = g2.number_input("Chamber height (cm)", value=float(config["chamber_height_cm"]), step=1.0, key="w_ch",
                                                help="Allowed: greater than 0 cm, and larger than the electrode gap.")
config["electrode_diameter_cm"] = g3.number_input("Electrode diameter (cm)", value=float(config["electrode_diameter_cm"]), step=0.5, key="w_ed",
                                                    help="Allowed: greater than 0 cm, and smaller than the chamber diameter.")
config["electrode_gap_cm"] = g4.number_input("Electrode gap (cm)", value=float(config["electrode_gap_cm"]), step=0.1, key="w_eg",
                                               help="Allowed: greater than 0 cm, and smaller than the chamber height.")

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
    labels = {"rf_power_w": "RF power", "pressure_mbar": "Pressure", "ar_flow_sccm": "Argon flow", "mixture": "Mixture",
              "n2_percent": "N₂ flow", "o2_percent": "O₂ flow", "chamber_diameter_cm": "Chamber diameter",
              "chamber_height_cm": "Chamber height", "electrode_diameter_cm": "Electrode diameter", "electrode_gap_cm": "Electrode gap",
              "eedf": "EEDF", "spatial": "Spatial model"}  # USE-3: the screen's names, not the code's
    for field, message in problems.items():
        status("error", f"{labels.get(field, field)}: {message}. Change it to run.")
else:
    status("ok", "Every parameter is inside the operating envelope.")
    for note in svc.regime_notes(config):
        status("info", f"Model regime: {note}.")

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
    if "N2" in config["mixture"]:
        sweepable["n2_percent_of_ar"] = ("N₂ admixture (% of Ar flow)", mix)
    if "O2" in config["mixture"]:
        sweepable["o2_percent_of_ar"] = ("O₂ admixture (% of Ar flow)", mix)
    parameter = st.selectbox("Parameter to sweep", list(sweepable), format_func=lambda k: sweepable[k][0])
    rng = sweepable[parameter][1]
    s1, s2, s3 = st.columns(3)
    unit = sweepable[parameter][0].rsplit("(", 1)[1].rstrip(")")
    start = s1.number_input(f"From ({unit})", value=float(rng["min"]), help=range_help(rng["min"], rng["max"], unit, "Start must be below end."))
    end = s2.number_input(f"To ({unit})", value=float(rng["max"]), help=range_help(rng["min"], rng["max"], unit))
    points = s3.number_input("Points", 2, env["options"]["sweep_max_points"], 10, help=range_help(2, env["options"]["sweep_max_points"], "points"))
    sweep_ok = float(rng["min"]) <= start < end <= float(rng["max"])
    if not sweep_ok:
        status("error", f"The sweep must start below its end, both within {rng['min']}-{rng['max']}.")
    if st.button("Run sweep", disabled=bool(problems) or not sweep_ok):
        st.session_state["sweep"] = {"parameter": parameter, "label": sweepable[parameter][0],
                                     "values": np.linspace(start, end, int(points)).tolist()}
        run_and_open_results(config)
