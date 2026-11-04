"""PDF, CSV and PNG exports with the citation filter: Phase 8 (FR10.8, FR11.5, E19, SEC-3).

RULES (BUILD_STEPS.md, Phase 8, fixed before this code):
- PDF (multi-page report with tables and figures), CSV and PNG, all drawn with matplotlib.
- A measured file that is not citable appears only as an anonymised entry, "Measured file M-0003
  (not citable): pass" (or fail, or not run): no file name, no metadata, no values, no curve.
- The number of non-citable files excluded is shown before every export (E19).

How the filter is made hard to break: every export is built from `report_rows`, the one function
that decides what a check may show. The renderers never see a non-citable check's values.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # no screen needed: exports are drawn off-screen
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from plasma_twin import __version__  # noqa: E402
from plasma_twin.data_io.validation import Check, tolerance  # noqa: E402

COLUMNS = ("Check", "Source", "Model", "Reference", "Deviation", "Result")
ROWS_PER_PAGE = 22


def _result(passed: bool | None) -> str:
    return {True: "pass", False: "fail", None: "not run"}[passed]


def excluded_count(checks: list[Check]) -> int:
    """E19: how many non-citable measured files the export leaves out (shown before exporting)."""
    return len({c.file_id for c in checks if c.file_id and not c.citable})


def report_rows(checks: list[Check]) -> list[tuple[str, ...]]:
    """The only place that decides what a check may show. Non-citable: anonymised pass/fail, nothing else."""
    rows = []
    for c in checks:
        if c.file_id and not c.citable:
            rows.append((f"Measured file {c.file_id} (not citable)", "-", "-", "-", "-", _result(c.passed)))
            continue
        rows.append((f"{c.name} ({c.quantity})", c.reference_source,
                     "-" if c.computed is None else f"{c.computed:.3g} {c.unit}",
                     "-" if c.reference is None else f"{c.reference:.3g} {c.unit}",
                     "-" if c.deviation is None else f"{100 * c.deviation:+.1f} %", _result(c.passed)))
    return rows


def _summary(checks: list[Check]) -> list[str]:
    counts = {r: sum(1 for c in checks if _result(c.passed) == r) for r in ("pass", "fail", "not run")}
    return [f"Plasma Digital Twin validation report (FR10.8)",
            f"Generated {datetime.now():%Y-%m-%d %H:%M}, software version {__version__}",
            f"Tolerance: +/-{tolerance():.0%}, fixed in envelope.toml before the comparison (CON-7)",
            f"{counts['pass']} pass, {counts['fail']} fail, {counts['not run']} not run",
            f"{excluded_count(checks)} non-citable measured file(s) appear only as anonymised pass/fail entries (E19)",
            "Measured data are used for validation only and never change model parameters (CON-6)."]


def validation_csv(checks: list[Check]) -> str:
    buffer = io.StringIO()
    for line in _summary(checks):
        buffer.write(f"# {line}\n")
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    writer.writerows(report_rows(checks))
    return buffer.getvalue()


def _table_page(pdf: PdfPages, title_lines: list[str], rows: list[tuple[str, ...]]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))  # A4 landscape
    fig.text(0.04, 0.95, title_lines[0], fontsize=14, weight="bold")
    for i, line in enumerate(title_lines[1:]):
        fig.text(0.04, 0.91 - 0.03 * i, line, fontsize=9)
    if rows:
        ax = fig.add_axes((0.03, 0.04, 0.94, 0.70))
        ax.axis("off")
        table = ax.table(cellText=[[cell[:60] for cell in r] for r in rows], colLabels=COLUMNS, loc="upper left",
                         colWidths=(0.30, 0.30, 0.10, 0.10, 0.10, 0.10))
        table.auto_set_font_size(False)
        table.set_fontsize(7)
    pdf.savefig(fig)
    plt.close(fig)


def validation_pdf(checks: list[Check]) -> bytes:
    """FR10.8: all checks, non-citable data only as anonymised pass/fail entries."""
    rows = report_rows(checks)
    buffer = io.BytesIO()
    with PdfPages(buffer, metadata={"Title": "Plasma Digital Twin validation report", "Creator": f"plasma_twin {__version__}"}) as pdf:
        summary = _summary(checks)
        pages = [rows[i:i + ROWS_PER_PAGE] for i in range(0, len(rows), ROWS_PER_PAGE)] or [[]]
        for n, chunk in enumerate(pages):
            _table_page(pdf, summary if n == 0 else [f"Validation report, page {n + 1}"], chunk)
    return buffer.getvalue()


# ------------------------------------------------------------------------------------ sessions (FR11.5)
def _session_rows(records) -> list[tuple[str, ...]]:
    rows = []
    for r in records:
        state = r.results.get("plasma_state") or r.results.get("stage2", {})
        keys = ("te_ev", "ne_center_m3", "gas_temperature_k") if r.stage == 1 else ("log_reduction", "te_ev", "ozone_end_mg_l")
        values = ", ".join(f"{k} = {state[k]:.3g}" for k in keys if isinstance(state.get(k), (int, float)))
        rows.append((r.session_id, f"Stage {r.stage}", r.created_at, r.note[:40], values, r.model_version))
    return rows


def sessions_csv(records) -> str:
    buffer = io.StringIO()
    buffer.write(f"# Plasma Digital Twin sessions, software version {__version__}\n")
    writer = csv.writer(buffer)
    writer.writerow(("Session", "Stage", "Saved", "Note", "Key results", "Model version"))
    writer.writerows(_session_rows(records))
    for r in records:
        writer.writerow([])
        writer.writerow((r.session_id, "configuration"))
        writer.writerows((r.session_id, k, v) for k, v in r.config.items())
    return buffer.getvalue()


def sessions_figure(records):
    """One bar chart of the sessions' headline quantity (T_e for Stage 1, log reduction for Stage 2)."""
    fig, ax = plt.subplots(figsize=(7, 4))
    stage = records[0].stage if records else 1
    key, label = ("te_ev", "Electron temperature T_e (eV)") if stage == 1 else ("log_reduction", "Log reduction (dimensionless)")
    values = [(r.results.get("plasma_state") or r.results.get("stage2", {})).get(key) for r in records]
    ax.bar([r.session_id for r in records], [v if isinstance(v, (int, float)) else 0 for v in values])
    ax.set_xlabel("Session")
    ax.set_ylabel(label)
    fig.tight_layout()
    return fig


def sessions_png(records) -> bytes:
    fig = sessions_figure(records)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    return buffer.getvalue()


def sessions_pdf(records) -> bytes:
    buffer = io.BytesIO()
    with PdfPages(buffer, metadata={"Title": "Plasma Digital Twin sessions", "Creator": f"plasma_twin {__version__}"}) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.text(0.04, 0.95, "Plasma Digital Twin sessions (FR11.5)", fontsize=14, weight="bold")
        fig.text(0.04, 0.91, f"Generated {datetime.now():%Y-%m-%d %H:%M}, software version {__version__}. "
                             "Sessions hold model results only; no measured data are included.", fontsize=9)
        ax = fig.add_axes((0.03, 0.10, 0.94, 0.75))
        ax.axis("off")
        table = ax.table(cellText=[list(r) for r in _session_rows(records)],
                         colLabels=("Session", "Stage", "Saved", "Note", "Key results", "Model version"), loc="upper left")
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        pdf.savefig(fig)
        plt.close(fig)
        fig = sessions_figure(records)
        pdf.savefig(fig)
        plt.close(fig)
    return buffer.getvalue()
