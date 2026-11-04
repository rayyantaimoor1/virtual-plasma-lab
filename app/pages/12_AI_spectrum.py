"""M12 AI spectrum analysis (Core Module 2.1): T_e, n_e and T_gas from a spectrum, next to the physics fit."""
from common import (PAGES, cached_spectrum, config_json, is_researcher, measured_spectrum, measured_store,  # noqa: I001
                    need_result, page_setup, sci, spectrometer_settings_text, status)

import json

import streamlit as st

from plasma_twin.ai import inference
from plasma_twin.ai.registry import ModelUnavailable, Registry
from plasma_twin.oes.boltzmann import integrated_intensities
from plasma_twin.oes.line_ratio import fit_spectrum_points
from plasma_twin.oes.spectrum import SpectrometerSettings

page_setup("AI spectrum analysis")
st.title("AI spectrum analysis")
status("info", "The AI reads T_e, n_e and T_gas from the argon line pattern. It learned only from spectra the twin made "
               "(never from measured data, AIQ-5). Every AI value is an estimate with a 90 % interval, shown next to the physics fit.")
result = need_result()
config_text = config_json(st.session_state["config"])


@st.cache_resource(max_entries=4)
def load_model(model_id: str):
    return Registry().load(model_id)


# ------------------------------------------------------------------ which model (E22)
models = inference.current_models()
model, card = None, None
if not models:
    status("warn", "No current AI model: none has been trained for this twin version, or the trained one is out of date (E22). "
                   "Only the physics analysis is shown. A Researcher can train one on the AI training screen.")
    if st.button("Go to AI training"):
        st.switch_page(PAGES["ai_training"])
else:
    chosen = st.selectbox("AI model", [c.model_id for c in models],
                          format_func=lambda m: f"{m} ({next(c.algorithm for c in models if c.model_id == m)})")
    try:
        model, card = load_model(chosen)
    except ModelUnavailable as error:
        status("error", str(error))

# ------------------------------------------------------------------ which spectrum
source = "synthetic"
if is_researcher():
    oes_files = [f.file_id for f in measured_store().list(diagnostic="oes", stage=1)]
    source = st.selectbox("Spectrum", ["synthetic"] + oes_files,
                          format_func=lambda s: "synthetic spectrum of the open plasma" if s == "synthetic" else f"measured file {s}")
instrument = SpectrometerSettings(**json.loads(spectrometer_settings_text()))
if source == "synthetic":
    low, high = (min(model.wavelengths_nm) - 2, max(model.wavelengths_nm) + 2) if model else (690.0, 860.0)
    acquisition = SpectrometerSettings(instrument.fwhm_nm, max(low, 200.0), high, instrument.noise_percent, instrument.seed)
    spectrum, cr = cached_spectrum(config_text, json.dumps(acquisition.__dict__, sort_keys=True))
    st.caption(f"Synthetic spectrum of the open plasma over {acquisition.start_nm:.0f}-{acquisition.end_nm:.0f} nm (the model's lines), "
               f"with the OES screen's instrument: FWHM {acquisition.fwhm_nm:g} nm, noise {acquisition.noise_percent:g} % of the peak.")
else:
    _, cr = cached_spectrum(config_text, spectrometer_settings_text())
    spectrum, record = measured_spectrum(source, result.inputs.gas_temperature_k)
    status("info", f"Measured file {source}, read with its own instrument width ({record.metadata.get('instrument_fwhm_nm')} nm). "
                   f"Its recorded conditions: {record.metadata.get('conditions')}. The physics fit uses the open plasma's gas and geometry.")

# ------------------------------------------------------------------ AI estimate and physics, side by side
left, right = st.columns(2)
with left:
    st.subheader("AI estimate")
    if model is None:
        st.caption("No AI estimate (no current model).")
    else:
        found = inference.estimate(spectrum, model)
        differs = inference.untrained_settings(st.session_state["config"])
        if source == "synthetic" and differs:
            status("warn", "The model learned only from plasmas with " + ", ".join(differs) + "; this plasma differs there, "
                           "so the line-ratio range check may not notice it is extrapolating. Read the AI estimate with care.")
        if found.withheld:
            status("warn", "AI estimate withheld: " + "; ".join(found.reasons) + ".")
        else:
            st.metric("T_e (AI estimate)", f"{found.te_ev:.2f} eV",
                      help="90 % interval from split-conformal prediction (MAPIE).")
            st.caption(f"90 % interval: {found.te_interval_ev[0]:.2f} to {found.te_interval_ev[1]:.2f} eV")
            st.metric("n_e (AI estimate)", f"{sci(found.ne_m3)} m⁻³")
            st.caption(f"90 % interval: {sci(found.ne_interval_m3[0])} to {sci(found.ne_interval_m3[1])} m⁻³")
            if found.tgas_k is not None:
                st.metric("T_gas (AI estimate)", f"{found.tgas_k:.0f} K")
                st.caption(f"90 % interval: {found.tgas_interval_k[0]:.0f} to {found.tgas_interval_k[1]:.0f} K. Learned from how the "
                           "twin's gas heating goes with the line pattern, not from a line width.")
            else:
                status("info", "T_gas " + found.tgas_note + ".")
            st.caption(f"Model {card.model_id} ({card.algorithm}), trained on {card.dataset_id}; "
                       f"inference took {found.seconds * 1000:.0f} ms.")
with right:
    st.subheader("Physics analysis (line ratios)")
    points = [p for p in integrated_intensities(spectrum, cr.lines) if p.intensity > 0]
    if len(points) >= 3:
        lr = fit_spectrum_points(points, result)
        st.metric("T_e (CR-model line-ratio fit)", f"{lr.te_ev:.2f} eV")
        st.metric("n_e (CR-model line-ratio fit)", f"{sci(lr.ne_m3)} m⁻³")
        st.caption(f"Both fitted from the spectrum with the open plasma's gas density, T_gas, EEDF and geometry taken as known "
                   f"(Phase 4). {len(points)} lines; fit RMS of ln(intensity share) {lr.rms_log_residual:.2e}.")
    else:
        status("error", "The line-ratio fit needs at least three lines in the spectrum.")
    if source == "synthetic":
        st.caption(f"The twin's own values for this plasma: T_e {result.te_ev:.2f} eV, n_e {sci(result.ne_center_m3)} m⁻³, "
                   f"T_gas {result.inputs.gas_temperature_k:.0f} K.")

# ------------------------------------------------------------------ how good is the model
if card is not None:
    with st.expander("How accurate is this model? (held-out twin spectra)"):
        rows = []
        for split in ("random", "region"):
            m = card.metrics.get(split, {})
            if "model" not in m:
                continue
            ai, ridge, physics = m["model"], m["baseline"], m.get("physics", {})
            rows.append({"Split": split, "Held-out runs": m["test_rows"],
                         "T_e MAE AI / ridge / physics (eV)": f"{ai['te_mae']:.3f} / {ridge['te_mae']:.3f} / "
                                                              + (f"{physics['te_mae']:.3f}" if physics else "-"),
                         "n_e median error AI / ridge / physics": f"{ai['ne_median_relative_error']:.0%} / {ridge['ne_median_relative_error']:.0%} / "
                                                                  + (f"{physics['ne_median_relative_error']:.0%}" if physics else "-"),
                         "90 % interval coverage T_e / n_e": f"{ai['te_coverage']:.0%} / {ai['ne_coverage']:.0%}",
                         "p (T_e, AI better than ridge)": sci(m["p_value_te_vs_ridge"], 2),
                         "p (T_e, AI better than physics)": sci(m["p_value_te_vs_physics"], 2) if "p_value_te_vs_physics" in m else "-"})
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption("p < 0.05 means the AI's errors are significantly smaller (paired bootstrap). The physics fit is given the known "
                   "pressure and mixture; the AI sees only the spectrum. Region: the held-out corner P ≥ 80 W, p ≥ 0.4 mbar.")
