"""Tests for the model vs OES vs probe comparison (Phase 5)."""
import pytest

from plasma_twin.compare.diagnostics import QuantityComparison, entry, within_tolerance
from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")


def test_thirty_one_percent_fails_and_twenty_nine_passes() -> None:
    assert within_tolerance(0.29) and within_tolerance(-0.29) and within_tolerance(0.30)
    assert not within_tolerance(0.31) and not within_tolerance(-0.31)


def test_dependent_and_unreliable_values_are_not_counted() -> None:
    good = entry("probe", 1.1, 1.0)
    dependent = entry("OES", 2.0, 1.0, independent=False)
    noisy = entry("probe", 5.0, 1.0, reliable=False)
    q = QuantityComparison("n_e", "m^-3", 1.0, (good, dependent, noisy))
    assert q.compared == (good,)
    assert q.passes and q.max_deviation == pytest.approx(0.1)
    assert QuantityComparison("T_gas", "K", 300.0, (dependent,)).passes is None


@pytest.fixture(scope="module")
def nitrogen_report():
    from plasma_twin.compare.diagnostics import compare
    from plasma_twin.probe.iv_model import ProbeSettings
    from plasma_twin.stage1.global_model import default_inputs, solve
    return compare(solve(default_inputs(n2_percent_of_ar=5)), ProbeSettings.defaults(noise_percent=0.0))


@needs_data
def test_oes_density_from_the_probe_is_marked_dependent(nitrogen_report) -> None:
    ne = next(q for q in nitrogen_report.quantities if q.quantity == "n_e")
    oes = next(e for e in ne.entries if e.method == "OES")
    assert not oes.independent and "dependent" in oes.note


@needs_data
def test_gas_temperature_comes_from_the_n2_band(nitrogen_report) -> None:
    gas = next(q for q in nitrogen_report.quantities if q.quantity == "T_gas")
    assert gas.entries and gas.passes


@needs_data
def test_excitation_temperature_is_shown_but_excluded(nitrogen_report) -> None:
    assert "excluded" in nitrogen_report.excitation_note
    assert all(q.quantity != "T_exc" for q in nitrogen_report.quantities)


@needs_data
def test_oxygen_results_are_flagged_approximate() -> None:
    """Phase 5 exit gate, LI-4."""
    from plasma_twin.compare.diagnostics import compare
    from plasma_twin.stage1.global_model import default_inputs, solve
    report = compare(solve(default_inputs(o2_percent_of_ar=5)))
    assert report.approximate
    assert any("LI-4" in w for w in report.warnings)
    for q in report.quantities:
        assert all(not e.counted for e in q.entries)  # nothing counts as agreement while flagged approximate
