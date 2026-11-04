"""Exports and the citation filter (Phase 8, FR10.8, FR11.5, E19, SEC-3)."""
import re

import matplotlib
import numpy as np
import pytest

from plasma_twin.data_io.export import excluded_count, report_rows, validation_csv, validation_pdf
from plasma_twin.data_io.validation import Check


def pdf_text(pdf: bytes) -> str:
    """The text matplotlib drew, from an uncompressed PDF with Type 3 fonts (each TJ array joined)."""
    arrays = re.findall(rb"\[(.*?)\] TJ", pdf, re.S)
    text = "\n".join(b"".join(re.findall(rb"\(((?:\\.|[^\\)])*)\)", a)).decode("latin-1") for a in arrays)
    return text.replace("\\(", "(").replace("\\)", ")")  # PDF strings escape parentheses


@pytest.fixture
def readable_pdf(monkeypatch):
    monkeypatch.setitem(matplotlib.rcParams, "pdf.compression", 0)
    monkeypatch.setitem(matplotlib.rcParams, "pdf.fonttype", 3)


SECRET = Check("T_e from the probe", "T_e", "eV", "M-0007", "M-0007", False, 4.56789, 6.54321)
PUBLIC = Check("T_e at 100 mTorr", "T_e", "eV", "Saikia et al. (2018), Table II", None, True, 1.234, 1.37)


def test_non_citable_rows_are_anonymised(readable_pdf) -> None:
    rows = report_rows([SECRET, PUBLIC])
    assert rows[0] == ("Measured file M-0007 (not citable)", "-", "-", "-", "-", "fail")
    assert "1.23 eV" in rows[1]
    text = pdf_text(validation_pdf([SECRET, PUBLIC]))
    assert "Saikia" in text and "1.23" in text  # the renderer works and is readable here
    for leak in ("4.57", "6.54", "+-30.2"):
        assert leak not in text and leak not in validation_csv([SECRET, PUBLIC])
    assert excluded_count([SECRET, PUBLIC]) == 1


def test_no_export_contains_a_non_citable_dataset(measured_set, secret_markers, readable_pdf) -> None:
    """SEC-3: a real validation run with a non-citable probe file; nothing of it may leave in PDF or CSV."""
    from plasma_twin.data_io.validation import run_validation
    store, probe_id, _, _ = measured_set
    checks = run_validation(store, include_benchmarks=False, record=False)
    secret_values = [f"{c.reference:.3g}" for c in checks if c.file_id == probe_id]
    exports = [validation_csv(checks), pdf_text(validation_pdf(checks))]
    for text in exports:
        assert all(marker[:20] not in text for marker in secret_markers)
        assert all(value not in text for value in secret_values)
        assert f"{probe_id} (not citable)" in text  # "fi" in "file" is drawn as one ligature glyph in the PDF
    assert excluded_count(checks) == 1


def test_session_exports_are_made(tmp_path) -> None:
    from plasma_twin.data_io.export import sessions_csv, sessions_pdf, sessions_png
    from plasma_twin.storage.sessions import SessionStore
    store = SessionStore(tmp_path / "s.db")
    for te in (2.5, 3.0):
        store.save(1, {"rf_power_w": 50.0}, "h", {"plasma_state": {"te_ev": te, "ne_center_m3": 1e16}}, "note", "0.8.0")
    records = store.list()
    assert sessions_pdf(records).startswith(b"%PDF") and sessions_png(records).startswith(b"\x89PNG")
    assert "rf_power_w" in sessions_csv(records)


def test_overlay_normalises_both_spectra_to_the_strongest_common_line() -> None:
    from plasma_twin.data_io.overlay import NoCommonLine, normalise
    w = np.linspace(700, 820, 12001)
    lines = {750.387: 2.0, 811.531: 5.0, 900.0: 9.0}  # 900 nm is outside both ranges

    def draw(scale):
        return scale * sum(p * np.exp(-0.5 * ((w - wl) / 0.01) ** 2) for wl, p in lines.items())

    norm = normalise(w, draw(1.0), 0.01, lines, w, draw(7.0), 0.01)
    assert norm.reference_nm == 811.531 and norm.scale == pytest.approx(1 / 7)
    with pytest.raises(NoCommonLine):
        normalise(w, draw(1.0), 0.01, {900.0: 1.0}, w, draw(1.0), 0.01)
