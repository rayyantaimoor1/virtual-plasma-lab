"""Pulse rules of the underwater supply (Phase 7, FR8.4, FR8.5, E5)."""
import pytest

from plasma_twin.stage2.pulse import PulseBlocked, PulseSettings


def test_100_us_at_10_khz_is_blocked() -> None:
    with pytest.raises(PulseBlocked, match="overlap"):
        PulseSettings.defaults(width_us=100.0, frequency_khz=10.0).check()


def test_10_us_at_5_khz_gives_5_percent_and_20_mj() -> None:
    pulse = PulseSettings.defaults(width_us=10.0, frequency_khz=5.0, power_w=100.0)
    assert pulse.check() == []
    assert pulse.duty_cycle == pytest.approx(0.05)
    assert pulse.energy_per_pulse_j == pytest.approx(0.020)
    assert pulse.pulse_power_w == pytest.approx(2000.0)


def test_duty_above_half_warns_but_runs() -> None:
    warnings = PulseSettings.defaults(width_us=60.0, frequency_khz=10.0).check()
    assert warnings and "50 %" in warnings[0]


def test_power_outside_envelope_is_blocked() -> None:
    with pytest.raises(PulseBlocked, match="average_power_w"):
        PulseSettings.defaults(power_w=500.0).check()
