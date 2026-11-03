"""Hom (Hunt & Marinas) survival model (Phase 7, FR9.1, FR9.3, LI-6)."""
import numpy as np
import pytest

from plasma_twin.stage2.hom import OrganismUnavailable, rate_constant, survival


def test_constant_ozone_reproduces_first_order_kinetics_at_20_c() -> None:
    """Hunt & Marinas: ln(N/N0) = -k C t with k = 130 L/(mg s) at 20 C, i.e. Hom with n = m = 1."""
    t = np.linspace(0, 2, 11)  # 2 s, inside their 1.8-33 s
    c = np.full_like(t, 0.020)  # 20 ug/L, inside their 6-41 ug/L
    result = survival(t, c, c * t, "E. coli", 1e6, 1000, 20.0, 50.0)
    assert result.rate_constant_l_mg_s == pytest.approx(130.0)
    assert result.log_survival[-1] == pytest.approx(-130.0 * 0.020 * 2 / np.log(10))
    assert result.flags == ()


def test_arrhenius_temperature_dependence() -> None:
    from scipy import constants
    ratio = rate_constant(25.0) / rate_constant(20.0)
    assert ratio == pytest.approx(np.exp(-37100 / constants.R * (1 / 298.15 - 1 / 293.15)))


def test_reduction_is_capped_at_one_cell_in_the_volume() -> None:
    t = np.linspace(0, 60, 61)
    c = np.full_like(t, 1.0)
    result = survival(t, c, c * t, "E. coli", 1.5e5, 500, 20.0, 100.0)
    assert result.capped and result.log_reduction == pytest.approx(np.log10(1.5e5 * 500))


def test_organism_without_parameters_is_unavailable() -> None:
    t = np.linspace(0, 1, 3)
    with pytest.raises(OrganismUnavailable):
        survival(t, t, t, "S. aureus", 1e5, 500, 20.0, 100.0)
