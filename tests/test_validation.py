"""Validation against benchmarks and measured files (Phase 8, FR10.6, FR10.7, CON-6, CON-7)."""
import pytest

from plasma_twin.data_io.validation import Check, run_validation, tolerance


def test_tolerance_comes_from_the_versioned_envelope() -> None:
    from plasma_twin.config.loader import load_envelope
    assert tolerance() == load_envelope()["validation"]["agreement_tolerance_fraction"] == 0.30
    assert Check("x", "T_e", "eV", "s", None, True, 1.3, 1.0).passed  # exactly +30 % passes
    assert not Check("x", "T_e", "eV", "s", None, True, 1.31, 1.0).passed
    assert Check("x", "n_e", "m^-3", "s", None, True, float("nan"), 1.0).passed is None  # not run, never a fail


def test_model_files_validate_against_their_own_model(measured_set) -> None:
    """Files made from the model must agree with it: this checks the import-to-analysis chain, not the physics."""
    store, probe_id, oes_id, uw_id = measured_set
    checks = run_validation(store, include_benchmarks=False, record=False)
    by_file = {}
    for c in checks:
        by_file.setdefault(c.file_id, []).append(c)
    assert all(c.passed for c in by_file[probe_id])
    oes = by_file[oes_id]
    assert len(oes) == 1 and "taken from probe file" in oes[0].note and abs(oes[0].deviation) < 0.05
    assert by_file[uw_id][0].deviation == pytest.approx(0.0, abs=0.01)


def test_results_are_recorded_with_date_and_version(measured_set) -> None:
    from plasma_twin import __version__
    from plasma_twin.storage.db import connect
    store = measured_set[0]
    checks = run_validation(store, include_benchmarks=False)
    conn = connect(store.db_path)
    rows = conn.execute("SELECT software_version, run_at, tolerance FROM validation_results").fetchall()
    conn.close()
    assert len(rows) >= sum(1 for c in checks if c.passed is not None)
    assert all(r["software_version"] == __version__ and r["run_at"] and r["tolerance"] == 0.30 for r in rows)


def test_measured_data_never_change_the_model(measured_set) -> None:
    """CON-6: the model gives identical results before and after a validation run."""
    from plasma_twin.services import stage1
    before = stage1.summarise(stage1.run(stage1.default_config()))
    run_validation(measured_set[0], include_benchmarks=False)
    assert stage1.summarise(stage1.run(stage1.default_config())) == before


def test_benchmarks_list_source_values_and_results() -> None:
    from plasma_twin.reference.loaders import DataStatus, check_reference_data
    if check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK:
        pytest.skip("LXCat data not downloaded")
    from plasma_twin.data_io.validation import benchmark_checks
    checks = benchmark_checks()
    assert checks and all("Saikia" in c.reference_source and c.computed and c.reference for c in checks)
    assert sum("exit-gate" in c.name for c in checks) == 6
