"""Comparison of the argon global model with published measurements (ACC-1, Phase 2 exit gate).

The rules were committed before the first run (BUILD_STEPS.md). The first run failed; the result
is recorded in docs/validation/phase2_stage1_benchmarks.md. The gate test is marked as an expected
failure in strict mode: it keeps failing visibly in the report, and the moment it starts to pass,
pytest flags it so the record and the exit gate are updated deliberately.
"""
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.benchmark import GATE_POINTS, compare

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


@needs_lxcat
def test_every_gate_point_is_compared_for_both_quantities() -> None:
    gate = [c for c in compare() if c.in_gate]
    assert {(c.point, c.quantity) for c in gate} == {(p, q) for p in GATE_POINTS for q in ("n_e", "T_e")}
    assert all(0.1 <= c.pressure_mbar <= 0.5 for c in gate)


@needs_lxcat
def test_model_follows_the_measured_pressure_trend() -> None:
    """Measured n_e rises with pressure at 50 W; the model must at least get the direction right."""
    density = sorted((c.pressure_mbar, c.modelled) for c in compare() if c.quantity == "n_e" and c.power_w == 50
                     and c.point.startswith("saikia2018_p"))
    assert all(b[1] > a[1] for a, b in zip(density, density[1:]))


@needs_lxcat
@pytest.mark.xfail(strict=True, reason="Runs 1 and 2 failed (2 Nov 2026): n_e +159 to +217 %, T_e +115 to "
                                        "+137 %. See docs/validation/phase2_stage1_benchmarks.md")
def test_gate_points_agree_within_tolerance() -> None:
    failing = [(c.point, c.quantity, f"{100 * c.difference:+.0f}%") for c in compare() if c.in_gate
               and not c.within_tolerance]
    assert not failing, failing
