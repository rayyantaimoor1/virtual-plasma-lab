"""Tests for the probe-style electron temperature (plasma_twin/probe/retardation.py)."""
import numpy as np
import pytest

from plasma_twin.probe.retardation import WINDOWS, probe_style_te, retarding_current
from plasma_twin.stage1.eedf import DRUYVESTEYN_SHAPE, EEDF, MAXWELLIAN_SHAPE


@pytest.mark.parametrize("window", list(WINDOWS))
@pytest.mark.parametrize("te", [0.8, 2.0, 5.0])
def test_maxwellian_reads_back_its_own_temperature(window: str, te: float) -> None:
    """For a Maxwellian, I_e ∝ exp(-V/T_e) exactly, so every window must return T_e."""
    assert probe_style_te(te, MAXWELLIAN_SHAPE, window) == pytest.approx(te, rel=1e-4)


def test_maxwellian_current_is_an_exact_exponential() -> None:
    volts = np.linspace(0.0, 10.0, 11)
    current = retarding_current(EEDF(2.0, MAXWELLIAN_SHAPE), volts)
    assert np.allclose(current / current[0], np.exp(-volts / 2.0), rtol=1e-5)


@pytest.mark.parametrize("window", list(WINDOWS))
def test_ratio_to_mean_energy_te_does_not_depend_on_te(window: str) -> None:
    """For a fixed EEDF shape everything scales with T_e, so the probe reading is a fixed fraction."""
    ratios = [probe_style_te(te, DRUYVESTEYN_SHAPE, window) / te for te in (1.0, 2.5, 6.0)]
    assert np.ptp(ratios) < 1e-6


def test_druyvesteyn_reads_low_near_the_floating_potential() -> None:
    """Its depleted tail makes the current fall faster at large retarding voltage."""
    te = 3.0
    near_floating = probe_style_te(te, DRUYVESTEYN_SHAPE, "near_floating_potential")
    near_plasma = probe_style_te(te, DRUYVESTEYN_SHAPE, "near_plasma_potential")
    assert near_floating < near_plasma < te
