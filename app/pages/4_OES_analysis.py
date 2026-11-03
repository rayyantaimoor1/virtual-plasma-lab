"""M5 OES analysis (FR5.1-FR5.10): Boltzmann plot, excitation temperature and line-ratio T_e."""
from common import (PAGES, axis, cached_probe, cached_spectrum, config_json, need_result, page_setup,  # noqa: I001
                    probe_settings_text, sci, spectrometer_settings_text, status)

import csv
import io

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from plasma_twin.oes.boltzmann import fit, integrated_intensities
from plasma_twin.oes.line_ratio import fit_spectrum_points

page_setup("OES analysis")
st.title("OES analysis")
result = need_result()
config_text = config_json(st.session_state["config"])
spectrum, cr = cached_spectrum(config_text, spectrometer_settings_text())
st.caption("Analysing the synthetic spectrum of the open plasma (FR5.1).")
if st.session_state["role"] == "Researcher":
    status("info", "Analysing an imported measured spectrum comes with data import in Phase 8.")

points = [p for p in integrated_intensities(spectrum, cr.lines) if p.intensity > 0]
if not points:
    status("error", "No argon lines lie inside the spectrometer's wavelength range; widen it on the OES screen.")
    st.stop()

# ------------------------------------------------------------------ line choice (FR5.8)
labels = {f"{p.wavelength_nm:.3f} nm": p for p in points}
chosen = st.multiselect("Lines in the fit (FR5.8)", list(labels), default=list(labels))
used = [labels[k] for k in chosen]
excluded = [k for k in labels if k not in chosen]

# ------------------------------------------------------------------ Boltzmann plot (FR5.2, FR5.3)
st.subheader("Boltzmann plot")
if len(used) >= 2:
    bfit = fit(used)
    x = np.array([p.upper_energy_ev for p in used])
    y = np.array([p.y for p in used])
    fig = go.Figure(go.Scatter(x=x, y=y, mode="markers", name="lines", text=[f"{p.wavelength_nm:.2f} nm" for p in used]))
    if np.isfinite(bfit.excitation_temperature_ev):
        xs = np.linspace(x.min(), x.max(), 2)
        slope = -1 / bfit.excitation_temperature_ev
        fig.add_trace(go.Scatter(x=xs, y=y.mean() + slope * (xs - x.mean()), mode="lines", name="fit"))
    st.plotly_chart(axis(fig, "Upper-level energy E_k (eV)", "ln(I λ / g_k A_ki) (dimensionless)"), use_container_width=True)
    if np.isfinite(bfit.excitation_temperature_ev):
        st.metric("Excitation temperature T_exc", f"{bfit.excitation_temperature_ev:.3f} ± {bfit.excitation_temperature_uncertainty_ev:.3f} eV",
                  help="Not the electron temperature: the 2p levels are not in equilibrium with the electrons.")
    st.caption(f"R² = {bfit.r_squared:.3f}; {bfit.n_lines} lines spanning {bfit.energy_span_ev:.2f} eV.")
    if bfit.reliable:
        status("ok", "The Boltzmann fit meets the reliability rules.")
    else:
        status("warn", "Unreliable fit (E9): " + "; ".join(bfit.reasons) + ". The argon 2p levels span only about 0.6 eV.")
else:
    status("error", "Choose at least two lines.")

# ------------------------------------------------------------------ line-ratio T_e with n_e from the probe (FR5.5, FR5.7)
st.subheader("Electron temperature from line ratios")
_, probe, probe_error = cached_probe(config_text, probe_settings_text())
fixed_ne, source = None, "fitted from the spectrum (no probe value available)"
if probe is not None:
    fixed_ne = probe.electron_density_m3 if probe.eepf_reliable else probe.saturation_density_m3
    source = ("simulated Langmuir probe, EEPF integral" if probe.eepf_reliable
              else "simulated Langmuir probe, saturation current (the EEPF is too noisy)")
if len(used) >= 3:
    lr = fit_spectrum_points(used, result, fixed_ne_m3=fixed_ne)
    c1, c2 = st.columns(2)
    c1.metric("T_e from line ratios", f"{lr.te_ev:.2f} eV")
    c2.metric("n_e used", f"{sci(lr.ne_m3)} m⁻³")
    st.caption(f"Source of n_e (FR5.7): {source}. Fit RMS of ln(intensity share): {lr.rms_log_residual:.2e}.")
    status("info", "When n_e comes from the probe, a 10 % error in it moves this T_e by about 30 % "
                   "(BUILD_STEPS.md, Phase 5; asked of the supervisor in Q9).")
else:
    lr = None
    status("error", "The line-ratio fit needs at least three lines.")

# ------------------------------------------------------------------ export and next (FR5.9, FR5.10)
buffer = io.StringIO()
writer = csv.writer(buffer)
writer.writerow(["quantity", "value", "uncertainty", "method"])
if len(used) >= 2:
    writer.writerow(["T_exc (eV)", bfit.excitation_temperature_ev, bfit.excitation_temperature_uncertainty_ev,
                     "Boltzmann plot; not an electron temperature"])
    writer.writerow(["R2", bfit.r_squared, "", "Boltzmann plot"])
if lr is not None:
    writer.writerow(["T_e (eV)", lr.te_ev, "", f"CR-model line ratios; n_e from {source}"])
writer.writerow([])
writer.writerow(["wavelength_nm", "intensity", "g_k", "A_ki", "E_k_eV", "used"])
for key, p in labels.items():
    writer.writerow([p.wavelength_nm, p.intensity, p.g_upper, p.a_per_s, p.upper_energy_ev, key not in excluded])
c1, c2 = st.columns(2)
c1.download_button("Download analysis and line list (CSV)", buffer.getvalue(), file_name="oes_analysis.csv", mime="text/csv")
if c2.button("Open the comparison (M7)"):
    st.switch_page(PAGES["compare"])
