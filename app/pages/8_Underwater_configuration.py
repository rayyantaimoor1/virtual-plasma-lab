"""M8 Underwater plasma configuration (FR8.1-FR8.13): Stage 2 inputs, checked live against envelope.toml."""
from common import page_setup, run_stage2_and_open, status, store, svc2  # noqa: I001

import streamlit as st

from plasma_twin.config.loader import load_envelope
from plasma_twin.stage2.hom import ORGANISMS_WITH_PARAMETERS

page_setup("Underwater configuration")
st.title("Underwater plasma disinfection (Stage 2)")
env = load_envelope()["stage2"]
config = dict(st.session_state["config2"])


def number(column, label: str, field: str, key: str | None = None, step: float | None = None, fmt: str | None = None, help_text: str = ""):
    """A number box bounded by the envelope range `key` (or unbounded below zero)."""
    rng = env.get(key or field)
    low, high = (float(rng["min"]), float(rng["max"])) if rng else (0.0, None)
    config[field] = column.number_input(label, low, high, float(config[field]), step, format=fmt, key=f"u_{field}",
                                        help=help_text or None)


# ------------------------------------------------------------------ supply (FR8.1-FR8.5)
st.subheader("Pulsed DC supply")
s = st.columns(4)
s[0].text_input("Supply (FR8.1)", env["fixed"]["supply"], disabled=True)
number(s[1], "Pulse voltage (kV)", "voltage_kv", "pulse_voltage_kv", 0.5,
       help_text="Recorded; the model works from the average power, so the voltage does not change the result.")
number(s[2], "Repetition frequency (kHz)", "frequency_khz", "pulse_frequency_khz", 0.5)
config["width_us"] = s[3].number_input("Pulse width (µs)", 0.1, 1000.0, float(config["width_us"]), 1.0, key="u_width_us",
                                       help="Default 10 µs (SUPERVISOR_QUESTIONS.md, Q11).")
p1, p2 = st.columns(2)
number(p1, "Average power P (W)", "power_w", "average_power_w", 5.0)
pulse = svc2.pulse_of(config)
p2.metric("Energy per pulse (FR8.5)", f"{1e3 * pulse.energy_per_pulse_j:.1f} mJ", help="P / f")
st.caption(f"Duty cycle = width × frequency = {pulse.duty_cycle:.1%} (FR8.4).")

# ------------------------------------------------------------------ discharge (FR8.6-FR8.10)
st.subheader("Discharge in the bubbles")
d = st.columns(4)
d[0].text_input("Electrodes (FR8.6)", env["fixed"]["electrode_geometry"], disabled=True)
gaps = env["options"]["electrode_gap_mm"]
config["gap_mm"] = float(d[1].selectbox("Electrode gap (mm)", gaps, index=gaps.index(int(config["gap_mm"])), key="u_gap"))
d[2].text_input("Pressure (FR8.7)", f"{env['fixed']['pressure_atm']:g} atm", disabled=True)
d[3].text_input("Electron distribution (FR8.10)", env["fixed"]["eedf"], disabled=True)
g = st.columns(3)
number(g[0], "O₂ flow (sccm)", "o2_flow_sccm", step=10.0)
gases = env["options"]["bubble_gas"]
config["bubble_gas"] = g[1].radio("Bubble gas (FR8.9)", gases, index=gases.index(config["bubble_gas"]), key="u_gas",
                                  help="Water vapour is needed for OH, H₂O₂ and H-alpha; O₂ only disables the Stark n_e.")
number(g[2], "Share of power reaching the bubble gas", "power_share", step=0.005, fmt="%.3f",
       help_text="Not measured for this device. The default is the largest share that splits at most 10 % of the O₂ "
                 "per pulse, the limit of the model's chemistry (BUILD_STEPS.md, Phase 7). See the sensitivity plot on M9.")

# ------------------------------------------------------------------ water and organism (FR8.11, FR8.12)
st.subheader("Water and organism")
w = st.columns(3)
number(w[0], "Water volume (mL)", "water_volume_ml", step=50.0)
number(w[1], "Initial pH", "water_ph", step=0.1)
number(w[2], "Water temperature (°C)", "water_temperature_c", step=1.0)
v = st.columns(3)
number(v[0], "Conductivity (µS/cm)", "conductivity_us_cm", step=10.0)
number(v[1], "COD (mg/L)", "cod_mg_l", step=10.0)
config["waste_type"] = v[2].selectbox("Waste type", svc2.WASTE_TYPES, index=svc2.WASTE_TYPES.index(config["waste_type"]), key="u_waste")
o = st.columns(3)
organisms = env["options"]["organisms"]
config["organism"] = o[0].selectbox("Target organism (FR8.12)", organisms, index=organisms.index(config["organism"]), key="u_org",
                                    format_func=lambda x: x if x in ORGANISMS_WITH_PARAMETERS else f"{x} (no published parameters)")
config["initial_count_cfu_ml"] = o[1].number_input("Initial count (CFU/mL)", 1.0, 1e10, float(config["initial_count_cfu_ml"]),
                                                   format="%.3g", key="u_count")
number(o[2], "Treatment time (min)", "treatment_time_min", step=0.5)
st.session_state["config2"] = config

# ------------------------------------------------------------------ checks (E5, LI-6)
problems, warnings = svc2.validate_config(config)
for field, message in problems.items():
    status("error", f"{field}: {message}")
for warning in warnings:
    status("warn", warning)
if not problems:
    status("ok", "Every parameter is inside the operating envelope.")
status("info", "Model regime: 0D plasma in O₂ bubbles at 1 atm (Maxwellian), afterglow chemistry from JPL 19-5, ozone "
               "transfer into the water, and the ozone kinetics of Hunt & Mariñas (1997) for E. coli.")

# ------------------------------------------------------------------ run, reset, save (FR8.13)
r1, r2, r3 = st.columns([1, 1, 2])
if r1.button("Run disinfection simulation", type="primary", disabled=bool(problems)):
    run_stage2_and_open(config)
if r2.button("Reset to defaults"):
    st.session_state["config2"] = svc2.default_config()
    for key in [k for k in st.session_state if k.startswith("u_")]:
        del st.session_state[key]
    st.rerun()
with r3.form("save_config2"):
    name = st.text_input("Save this configuration as")
    if st.form_submit_button("Save configuration") and not problems:
        try:
            store().save_named_configuration(name, 2, config, svc2.config_hash(config))
            status("ok", f"Saved as '{name.strip()}'.")
        except Exception as problem:  # SessionError: empty or duplicate name
            status("error", str(problem))
