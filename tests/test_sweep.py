"""Tests for parameter sweeps (Phase 3d)."""
import time

import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.global_model import default_inputs, solve
from plasma_twin.stage1.sweep import sweep

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


def test_unknown_parameter_and_too_many_points_are_refused() -> None:
    with pytest.raises(ValueError):
        sweep(default_inputs(), "frequency_hz", [13.56e6])
    with pytest.raises(ValueError):
        sweep(default_inputs(), "rf_power_w", np.linspace(10, 100, 201))
    with pytest.raises(ValueError):
        sweep(default_inputs(), "rf_power_w", [])


@needs_lxcat
def test_a_failed_point_is_kept_and_the_others_are_solved() -> None:
    points = sweep(default_inputs(), "rf_power_w", [20, 150, 60])  # 150 W is outside the envelope
    assert [p.value for p in points] == [20, 150, 60]
    assert [p.solved for p in points] == [True, False, True]
    assert "InputOutOfRange" in points[1].error


@needs_lxcat
def test_sweep_points_equal_single_runs() -> None:
    """Starting each point from the previous gas temperature must not change the answer."""
    points = sweep(default_inputs(), "pressure_mbar", [0.15, 0.35])
    single = solve(default_inputs(pressure_mbar=0.35))
    assert points[1].result.te_ev == pytest.approx(single.te_ev, rel=1e-8)
    assert points[1].result.ne_center_m3 == pytest.approx(single.ne_center_m3, rel=1e-8)


@needs_lxcat
def test_two_hundred_points_within_two_minutes() -> None:
    start = time.perf_counter()
    points = sweep(default_inputs(), "rf_power_w", np.linspace(10, 100, 200))
    assert time.perf_counter() - start <= 120  # PER-4
    assert len(points) == 200 and all(p.solved for p in points)
    assert np.all(np.diff([p.result.ne_center_m3 for p in points]) > 0)
