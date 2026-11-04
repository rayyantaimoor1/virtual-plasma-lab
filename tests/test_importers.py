"""Importing measured files and storing them (Phase 8, FR10.1-FR10.5, E13, E14, SEC-2, PER-7)."""
import os
import stat
import time

import numpy as np
import pytest

from plasma_twin.data_io.importers import FileRejected, mapped, parse
from plasma_twin.storage.measured import MeasuredDataError, MeasuredStore, validate_metadata

STAGE1_CONDITIONS = {"rf_power_w": 50.0, "pressure_mbar": 0.3, "ar_flow_sccm": 300.0, "mixture": "Ar", "n2_percent": 5.0,
                     "o2_percent": 5.0}
PROBE_META = {"instrument": "test probe", "measurement_date": "2026-11-01", "conditions": STAGE1_CONDITIONS,
              "probe": {"tip_radius_mm": 0.195, "exposed_length_mm": 5.0}}


def probe_text(rows: int = 141) -> bytes:
    v = np.linspace(-20, 50, rows)
    return ("Exported by the probe software\nV,I (mA)\n" + "\n".join(f"{a:.3f},{b:.6e}" for a, b in zip(v, 2.0 * np.tanh(v / 10)))).encode()


def test_milliamps_are_converted_to_amps() -> None:
    parsed = parse("curve.csv", probe_text(), "probe")
    assert parsed.rows == 141 and parsed.delimiter == "comma" and len(parsed.header) == 2
    v, i = mapped(parsed, 0, 1, "mA")
    assert i == pytest.approx(2.0e-3 * np.tanh(v / 10))
    assert mapped(parsed, 0, 1, "µA")[1] == pytest.approx(2.0e-6 * np.tanh(v / 10))


@pytest.mark.parametrize(("name", "raw", "kind", "reason"), [
    ("spectrum.csv", b"1\t2\n" * 20, "oes", "must be a .txt"),
    ("curve.txt", b"1,2\n" * 20, "probe", "must be a .csv"),
    ("spectrum.txt", b"\x00\x01binary" * 10, "oes", "binary"),
    ("spectrum.txt", b"just words\nno numbers\n", "oes", "no line with two or more numbers"),
    ("spectrum.txt", b"1 2\n" * 5, "oes", "only 5 data rows"),
    ("spectrum.txt", b"1 2\n" * 6 + b"3 x\n" + b"4 5\n" * 6, "oes", "line 7, column 2: 'x' is not a number"),
    ("curve.csv", b"1,2,3\n" * 12 + b"1,2\n", "probe", "line 13, column 3: empty cell"),
])
def test_bad_files_are_rejected_with_the_exact_reason(name, raw, kind, reason) -> None:
    with pytest.raises(FileRejected, match=reason):
        parse(name, raw, kind)


def test_oversized_file_is_rejected(monkeypatch) -> None:
    import plasma_twin.data_io.importers as importers
    real = importers.load_envelope
    monkeypatch.setattr(importers, "load_envelope", lambda: {**real(), "data": {**real()["data"], "import_max_file_mb": 0.001}})
    with pytest.raises(FileRejected, match="limit"):
        parse("curve.csv", probe_text(), "probe")


def test_decreasing_wavelength_is_refused_when_mapped() -> None:
    raw = "\n".join(f"{900 - k} {k}" for k in range(20)).encode()
    with pytest.raises(FileRejected, match="increasing"):
        mapped(parse("s.txt", raw, "oes"), 0, 1)


def test_a_50_mb_file_parses_within_15_s() -> None:
    """PER-7."""
    rows = 2_700_000
    w = np.linspace(300, 900, rows)
    raw = ("nm\tcounts\n" + "\n".join(f"{a:.5f}\t{b:.6f}" for a, b in zip(w, np.random.default_rng(0).random(rows)))).encode()
    assert 45 * 2**20 < len(raw) <= 50 * 2**20
    start = time.perf_counter()
    parsed = parse("big.txt", raw, "oes")
    assert time.perf_counter() - start <= 15.0
    assert parsed.rows == rows


def test_metadata_is_mandatory_and_inside_the_envelope() -> None:
    assert validate_metadata("probe", 1, PROBE_META) == {}
    problems = validate_metadata("probe", 2, {"conditions": {**STAGE1_CONDITIONS, "rf_power_w": 900.0}})
    assert {"stage", "instrument", "measurement_date", "probe.tip_radius_mm"} <= set(problems)
    assert "conditions.rf_power_w" in validate_metadata("probe", 1, {**PROBE_META, "conditions": {**STAGE1_CONDITIONS, "rf_power_w": 900.0}})
    assert "instrument_fwhm_nm" in validate_metadata("oes", 1, {k: v for k, v in PROBE_META.items() if k != "probe"})
    assert "measurement_date" in validate_metadata("probe", 1, {**PROBE_META, "measurement_date": "2999-01-01"})


def test_save_is_read_only_private_and_stores_nothing_on_failure(tmp_path) -> None:
    store = MeasuredStore(tmp_path / "t.db", tmp_path / "measured")
    raw = probe_text()
    parsed = parse("curve.csv", raw, "probe")
    with pytest.raises(MeasuredDataError):
        store.save(parsed, raw, {"x_column": 0, "y_column": 1, "current_unit": "mA"}, {**PROBE_META, "instrument": ""}, 1)
    assert store.list() == [] and not (tmp_path / "measured").exists()  # nothing stored on rejection
    file_id = store.save(parsed, raw, {"x_column": 0, "y_column": 1, "current_unit": "mA"}, PROBE_META, 1)
    record = store.get(file_id)
    assert file_id == "M-0001" and record.citable is False  # not citable unless permission is given
    assert record.stored_path.read_bytes() == raw  # byte for byte
    assert not os.stat(record.stored_path).st_mode & stat.S_IWRITE  # read-only (FR10.5)
    with pytest.raises(MeasuredDataError, match="already saved"):
        store.save(parsed, raw, {"x_column": 0, "y_column": 1, "current_unit": "mA"}, PROBE_META, 1)
    v, i, _ = store.load(file_id)
    assert i.max() == pytest.approx(2.0e-3 * np.tanh(5.0))
    with pytest.raises(MeasuredDataError, match="confirmation"):
        store.delete([file_id])
    assert store.delete([file_id], confirmed=True) == 1 and not record.stored_path.exists()


def test_measured_folder_is_gitignored() -> None:
    from pathlib import Path
    ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/measured/" in ignore and "*.db" in ignore


def test_streamlit_upload_limit_matches_the_envelope() -> None:
    import tomllib
    from pathlib import Path

    from plasma_twin.config.loader import load_envelope
    config = tomllib.loads((Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == load_envelope()["data"]["import_max_file_mb"]
