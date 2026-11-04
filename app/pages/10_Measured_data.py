"""M10 Measured data import and validation (FR10.1-FR10.8), Researcher only."""
from common import axis, is_researcher, measured_store, page_setup, sci, status, svc, svc2  # noqa: I001

from datetime import date

import plotly.graph_objects as go
import streamlit as st

from plasma_twin.config.loader import load_envelope
from plasma_twin.data_io.export import excluded_count, report_rows, validation_csv, validation_pdf
from plasma_twin.data_io.importers import CURRENT_UNITS, FileRejected, mapped, parse
from plasma_twin.data_io.validation import run_validation
from plasma_twin.storage.measured import MeasuredDataError

page_setup("Measured data")
st.title("Measured data and validation")
if not is_researcher():
    status("info", "Importing and validating measured data is for the Researcher role (FR1.4). Switch the role in the sidebar.")
    st.stop()
status("info", "Measured data are used for validation only: they never change any model parameter (CON-6). "
               "Files are stored on this computer only and are not citable unless you say so (FR10.4).")
env = load_envelope()
store = measured_store()

# ------------------------------------------------------------------ upload and preview (FR10.1, FR10.3)
st.subheader("Import a file")
kind = st.radio("Diagnostic", ["oes", "probe"], horizontal=True,
                format_func=lambda k: "OES spectrum (.txt)" if k == "oes" else "Langmuir probe I-V curve (.csv)")
upload = st.file_uploader("File", type=["txt"] if kind == "oes" else ["csv"],
                          help=f"At most {env['data']['import_max_file_mb']} MB. Text only; nothing in the file is ever run.")
if upload is not None:
    raw = upload.getvalue()
    try:
        parsed = parse(upload.name, raw, kind)
    except FileRejected as problem:
        status("error", f"File rejected (E14): {problem}. Nothing was stored.")
        st.stop()
    status("ok", f"{parsed.rows:,} rows read in {len(parsed.columns)} columns ({parsed.delimiter}-separated, "
                 f"{len(parsed.header)} header line(s)).")
    names = [f"column {i + 1}" for i in range(len(parsed.columns))]
    c = st.columns(3)
    x_col = c[0].selectbox("Wavelength λ (nm)" if kind == "oes" else "Voltage V (V)", range(len(names)), format_func=lambda i: names[i])
    y_col = c[1].selectbox("Intensity (a.u.)" if kind == "oes" else "Current", range(len(names)), index=1, format_func=lambda i: names[i])
    unit = c[2].selectbox("Current unit (converted to A)", list(CURRENT_UNITS)) if kind == "probe" else "a.u."
    try:
        x, y = mapped(parsed, x_col, y_col, unit if kind == "probe" else "A")
    except FileRejected as problem:
        status("error", str(problem))
        st.stop()
    px, py = svc.downsample_peaks(x, y)
    fig = go.Figure(go.Scatter(x=px, y=py if kind == "oes" else 1e3 * py, mode="lines"))
    st.plotly_chart(axis(fig, "Wavelength λ (nm)" if kind == "oes" else "Probe voltage V (V)",
                         "Intensity I (a.u.)" if kind == "oes" else "Probe current I (mA)"), use_container_width=True)

    # ------------------------------------------------------------------ metadata and citation (FR10.2, FR10.4)
    with st.form("metadata"):
        st.markdown("**Metadata (all fields required, FR10.2)**")
        m = st.columns(3)
        stage = m[0].selectbox("Plasma stage", [1] if kind == "probe" else [1, 2], help="Probe files are Stage 1 only.")
        measured_on = m[1].date_input("Measurement date", value=date.today(), max_value=date.today())
        instrument = m[2].text_input("Instrument")
        extra = {}
        if kind == "oes":
            extra["instrument_fwhm_nm"] = st.number_input("Instrument resolution FWHM (nm)", float(env["oes"]["resolution_fwhm_nm"]["min"]),
                                                          float(env["oes"]["resolution_fwhm_nm"]["max"]), 0.01, format="%.4f")
        else:
            g = st.columns(2)
            extra["probe"] = {"tip_radius_mm": g[0].number_input("Tip radius (mm)", 0.0, 10.0, 0.195, format="%.3f"),
                              "exposed_length_mm": g[1].number_input("Exposed length (mm)", 0.0, 100.0, 5.0)}
        st.markdown("**Operating conditions (must lie inside the stage's envelope)**")
        o = st.columns(3)
        if stage == 1:
            d = svc.default_config()
            mixtures = env["stage1"]["options"]["gas_mixtures"]
            conditions = {"rf_power_w": o[0].number_input("RF power (W)", value=d["rf_power_w"]),
                          "pressure_mbar": o[1].number_input("Pressure (mbar)", value=d["pressure_mbar"], format="%.3f"),
                          "ar_flow_sccm": o[2].number_input("Ar flow (sccm)", value=d["ar_flow_sccm"])}
            q = st.columns(3)
            conditions["mixture"] = q[0].selectbox("Gas mixture", mixtures)
            conditions["n2_percent"] = q[1].number_input("N₂ (% of Ar flow)", value=d["n2_percent"])
            conditions["o2_percent"] = q[2].number_input("O₂ (% of Ar flow)", value=d["o2_percent"])
        else:
            d = svc2.default_config()
            conditions = {"power_w": o[0].number_input("Average power (W)", value=d["power_w"]),
                          "frequency_khz": o[1].number_input("Frequency (kHz)", value=d["frequency_khz"]),
                          "width_us": o[2].number_input("Pulse width (µs)", value=d["width_us"])}
            q = st.columns(3)
            conditions["gap_mm"] = float(q[0].selectbox("Gap (mm)", env["stage2"]["options"]["electrode_gap_mm"], index=1))
            conditions["o2_flow_sccm"] = q[1].number_input("O₂ flow (sccm)", value=d["o2_flow_sccm"])
            conditions["bubble_gas"] = q[2].selectbox("Gas mixture (bubble gas)", env["stage2"]["options"]["bubble_gas"])
        citable = st.checkbox("These data may be cited in reports (default: not citable)", value=False)
        save, cancel = st.columns(2)
        do_save = save.form_submit_button("Save to the validation set", type="primary")
        do_cancel = cancel.form_submit_button("Cancel")
    if do_cancel:
        status("info", "Cancelled: nothing was stored.")
    if do_save:
        metadata = {"measurement_date": measured_on.isoformat(), "instrument": instrument, "conditions": conditions, **extra}
        mapping = {"x_column": x_col, "y_column": y_col, "current_unit": unit if kind == "probe" else "A"}
        try:
            file_id = store.save(parsed, raw, mapping, metadata, stage, citable)
            status("ok", f"Saved as {file_id} ({'citable' if citable else 'not citable'}); the stored file is read-only.")
        except (MeasuredDataError, FileRejected) as problem:
            status("error", f"Not saved: {problem}")

# ------------------------------------------------------------------ the validation set (FR10.5)
st.subheader("Validation set")
files = store.list()
if files:
    st.dataframe([{"File": f.file_id, "Diagnostic": f.diagnostic, "Stage": f.stage, "Original name": f.original_name,
                   "Measured": f.metadata.get("measurement_date"), "Citable": "yes" if f.citable else "no", "Imported": f.imported_at}
                  for f in files], hide_index=True, use_container_width=True)
    doomed = st.multiselect("Select files to delete", [f.file_id for f in files])
    if st.button("Delete selected files", disabled=not doomed):
        st.session_state["confirm_delete_files"] = doomed
    pending = st.session_state.get("confirm_delete_files")
    if pending:
        status("warn", f"Delete {', '.join(pending)} and their validation results permanently?")
        if st.button("Yes, delete permanently", type="primary"):
            store.delete(pending, confirmed=True)
            del st.session_state["confirm_delete_files"]
            st.rerun()
else:
    st.caption("No measured files yet. The literature benchmarks can still be run.")

# ------------------------------------------------------------------ validation (FR10.6-FR10.8)
st.subheader("Validation")
if st.button("Run validation (FR10.7)"):
    with st.spinner("Running every benchmark and measured-data comparison..."):
        st.session_state["validation_checks"] = run_validation(store)
checks = st.session_state.get("validation_checks")
if checks:
    tol = env["validation"]["agreement_tolerance_fraction"]
    st.dataframe([{"Check": c.name, "Source": c.reference_source, "Model": "-" if c.computed is None else f"{sci(c.computed)} {c.unit}",
                   "Reference": "-" if c.reference is None else f"{sci(c.reference)} {c.unit}",
                   "Deviation": "-" if c.deviation is None else f"{100 * c.deviation:+.1f} %",
                   "Result": {True: "pass", False: "fail", None: "not run"}[c.passed], "Note": c.note} for c in checks],
                 hide_index=True, use_container_width=True)
    passed = sum(1 for c in checks if c.passed)
    status("info", f"{passed} of {sum(1 for c in checks if c.passed is not None)} checks within ±{tol:.0%}; results recorded "
                   "with the date and software version.")
    excluded = excluded_count(checks)
    status("warn" if excluded else "ok", f"{excluded} non-citable file(s) will appear in exports only as anonymised pass/fail entries (E19).")
    with st.expander("What the exported report will show"):
        st.dataframe([dict(zip(("Check", "Source", "Model", "Reference", "Deviation", "Result"), r)) for r in report_rows(checks)],
                     hide_index=True, use_container_width=True)
    e1, e2 = st.columns(2)
    e1.download_button("Download validation report (PDF)", validation_pdf(checks), file_name="validation_report.pdf", mime="application/pdf")
    e2.download_button("Download validation results (CSV)", validation_csv(checks), file_name="validation_results.csv", mime="text/csv")
