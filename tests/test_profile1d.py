"""Tests for the axial electron density profile (Phase 3c)."""
import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.global_model import default_inputs, solve
from plasma_twin.stage1.profile1d import axial_profile

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


@pytest.fixture(scope="module")
def solved():
    result = solve(default_inputs())
    return result, axial_profile(result)


@needs_lxcat
def test_profile_is_symmetric_and_peaks_at_the_centre(solved) -> None:
    result, profile = solved
    assert np.allclose(profile.ne_m3, profile.ne_m3[::-1], rtol=1e-12)
    assert profile.ne_m3[len(profile.ne_m3) // 2] == pytest.approx(result.ne_center_m3, rel=1e-12)
    assert profile.ne_m3.argmax() == len(profile.ne_m3) // 2


@needs_lxcat
def test_profile_meets_the_0d_sheath_edge_density(solved) -> None:
    result, profile = solved
    assert profile.ne_m3[0] == pytest.approx(result.ne_sheath_edge_m3, rel=1e-10)
    assert profile.ne_m3[-1] == pytest.approx(result.ne_sheath_edge_m3, rel=1e-10)
    assert profile.half_width_m * 2 + 2 * profile.sheath_width_m == pytest.approx(result.inputs.electrode_gap_m)


@needs_lxcat
def test_profile_falls_steadily_towards_each_sheath(solved) -> None:
    _, profile = solved
    middle = len(profile.ne_m3) // 2
    assert np.all(np.diff(profile.ne_m3[middle:]) < 0)


@needs_lxcat
def test_bulk_average_matches_the_numerical_average(solved) -> None:
    _, profile = solved
    assert profile.bulk_average_m3 == pytest.approx(np.trapezoid(profile.ne_m3, profile.position_m)
                                                    / (2 * profile.half_width_m), rel=1e-4)


@needs_lxcat
def test_profile_solves_the_diffusion_equation(solved) -> None:
    """n'' = -k^2 n everywhere in the bulk (finite differences on a fine grid)."""
    result, _ = solved
    fine = axial_profile(result, points=4001)
    dx = fine.position_m[1] - fine.position_m[0]
    second = (fine.ne_m3[2:] - 2 * fine.ne_m3[1:-1] + fine.ne_m3[:-2]) / dx**2
    assert np.allclose(second, -fine.wavenumber_per_m**2 * fine.ne_m3[1:-1], rtol=1e-4)
