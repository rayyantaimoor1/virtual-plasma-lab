"""Tests for the electron energy distributions (Phase 2a)."""
import numpy as np
import pytest
from scipy.integrate import quad

from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE, EEDF, MAXWELLIAN_SHAPE, from_name

ENERGY = np.linspace(0.0, 400.0, 400001)
SHAPES = [MAXWELLIAN_SHAPE, DRUYVESTEYN_SHAPE]


def moment(eedf: EEDF, power: int) -> float:
    """integral(e**power f(e) de) by adaptive quadrature, independent of any grid in the code."""
    return quad(lambda e: e**power * float(eedf(np.array([e]))[0]), 0.0, np.inf, epsabs=1e-13, epsrel=1e-11)[0]


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("te", [0.5, 1.0, 3.0, 10.0])
def test_each_distribution_integrates_to_one(shape: float, te: float) -> None:
    assert moment(EEDF(te, shape), 0) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("te", [0.5, 1.0, 3.0, 10.0])
def test_mean_energy_is_three_halves_te(shape: float, te: float) -> None:
    assert moment(EEDF(te, shape), 1) == pytest.approx(1.5 * te, rel=1e-9)


def test_maxwellian_is_the_textbook_formula() -> None:
    te = 2.5
    expected = 2 * np.sqrt(ENERGY / np.pi) * te**-1.5 * np.exp(-ENERGY / te)
    assert np.allclose(EEDF(te, MAXWELLIAN_SHAPE)(ENERGY), expected, rtol=1e-12, atol=0)


@pytest.mark.parametrize("multiple", [4, 6, 10])
def test_druyvesteyn_tail_is_below_maxwellian(multiple: float) -> None:
    """Same mean energy, but elastic collisions deplete the fast electrons that ionize."""
    te = 3.0
    energy = np.array([multiple * te])
    assert EEDF(te, DRUYVESTEYN_SHAPE)(energy)[0] < EEDF(te, MAXWELLIAN_SHAPE)(energy)[0]


def test_names_and_bad_values() -> None:
    assert from_name("Druyvesteyn", 2.0).shape == DRUYVESTEYN_SHAPE
    assert from_name("Maxwellian", 2.0).shape == MAXWELLIAN_SHAPE
    with pytest.raises(ValueError):
        from_name("Boltzmann", 2.0)
    with pytest.raises(ValueError):
        EEDF(0.0)
