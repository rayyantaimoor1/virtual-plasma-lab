"""Tests for the argon collisional-radiative model (Phase 4a)."""
import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_bsr_argon", "nist_ar_i", "nist_ar_i_ir")),
    reason="the LXCat and NIST files have not been downloaded here")
BASE = {"te_ev": 3.0, "argon_density_m3": 7.2e21, "shape": DRUYVESTEYN_SHAPE, "gas_temperature_k": 300.0,
        "gap_m": 0.045, "radius_m": 0.07}


@needs_data
def test_every_level_and_its_paschen_name_come_from_the_data() -> None:
    from plasma_twin.oes.cr_model import LEVELS, level_data, racah_to_paschen
    assert set(racah_to_paschen().values()) == set(LEVELS)
    data = level_data()
    assert set(data.energy_ev) == set(LEVELS)
    assert all(level_data().weight[name] == w for name, w in {"1s5": 5, "1s3": 1, "2p9": 7, "2p1": 1}.items())
    wavelengths = [round(line.wavelength_nm, 1) for line in data.lines]
    assert {750.4, 763.5, 811.5, 912.3} <= set(wavelengths)


@needs_data
def test_populations_are_positive_and_rise_with_density() -> None:
    from plasma_twin.oes.cr_model import LEVELS, solve_cr
    results = [solve_cr(ne_m3=ne, **BASE) for ne in (1e15, 1e16, 1e17)]
    for result in results:
        assert all(result.populations_m3[name] > 0 for name in LEVELS)
    for name in LEVELS:
        values = [r.populations_m3[name] for r in results]
        assert np.all(np.diff(values) > 0), name


@needs_data
def test_without_electrons_nothing_is_excited() -> None:
    from plasma_twin.oes.cr_model import solve_cr
    result = solve_cr(ne_m3=1e16, electron_collisions=False, **BASE)
    assert all(v == 0 for v in result.populations_m3.values())


@needs_data
@pytest.mark.parametrize("ne", [1e15, 3e16, 1e17])
def test_populations_satisfy_every_balance(ne: float) -> None:
    """Gains equal losses for all 14 levels, with the escape factors the solution itself implies."""
    from plasma_twin.oes.cr_model import solve_cr
    result = solve_cr(ne_m3=ne, **BASE)
    assert result.balance_residual < 1e-9
    assert result.iterations < 100


def test_escape_factor_limits() -> None:
    from plasma_twin.oes.cr_model import Line, escape_factor
    line = Line(811.531, "2p9", "1s5", 3.3e7, 7, 5, 13.08)
    assert escape_factor(0.0, line, 300.0, 0.0225) == pytest.approx(1.0)
    thick = [escape_factor(n, line, 300.0, 0.0225) for n in (1e14, 1e15, 1e16, 1e17)]
    assert all(0 < g < 1 for g in thick)
    assert np.all(np.diff(thick) < 0)  # more absorbing atoms, fewer photons escape


@needs_data
def test_runs_on_a_global_model_result_in_well_under_a_second() -> None:
    import time
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.stage1.global_model import default_inputs, solve
    result = solve(default_inputs())
    start = time.perf_counter()
    cr = solve_cr_for(result)
    assert time.perf_counter() - start < 1.0
    brightest = max(cr.line_emission_w_m3, key=cr.line_emission_w_m3.get)
    assert brightest == pytest.approx(811.531, abs=0.01)  # 2p9 -> 1s5, the strongest argon line in practice
