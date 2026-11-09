"""Pulsed DC supply of the underwater discharge: Phase 7 (FR8.2-FR8.5, event E5).

The supervisor gave 10 kV, 5-10 kHz and 100 W average power. The pulse width defaults to 10 us
(SUPERVISOR_QUESTIONS.md, Q11): a 100 us pulse at 5-10 kHz would be on 50-100 % of the time.

RULES (BUILD_STEPS.md, Phase 7): duty = width x frequency; the run is blocked at duty >= 1 (E5) and
warned above 0.5. Energy per pulse = P / f; power while the pulse is on = P / duty.
"""
from __future__ import annotations

from dataclasses import dataclass

from plasma_twin.config.loader import load_envelope


class PulseBlocked(ValueError):
    """The pulse settings cannot run (E5): the pulses would overlap, or a value is outside the envelope."""


@dataclass(frozen=True)
class PulseSettings:
    voltage_kv: float
    frequency_khz: float
    width_us: float
    power_w: float

    @classmethod
    def defaults(cls, **overrides: float) -> "PulseSettings":
        """The supervisor's pulse settings from the envelope, with any settings overridden."""
        env = load_envelope()["stage2"]
        values = {"voltage_kv": env["pulse_voltage_kv"]["default"], "frequency_khz": env["pulse_frequency_khz"]["default"],
                  "width_us": env["pulse_rules"]["default_width_us"], "power_w": env["average_power_w"]["default"]}
        values.update(overrides)
        return cls(**{k: float(v) for k, v in values.items()})

    @property
    def frequency_hz(self) -> float:
        """The repetition frequency in hertz."""
        return self.frequency_khz * 1e3

    @property
    def duty_cycle(self) -> float:
        """Width times frequency: the fraction of time the pulse is on (E5 blocks it at 1)."""
        return self.width_us * 1e-6 * self.frequency_hz

    @property
    def energy_per_pulse_j(self) -> float:
        """Average power over frequency: the energy each pulse delivers (FR8.5)."""
        return self.power_w / self.frequency_hz

    @property
    def pulse_power_w(self) -> float:
        """Power while the pulse is on."""
        return self.power_w / self.duty_cycle

    def check(self) -> list[str]:
        """Raise PulseBlocked if the run cannot go ahead; otherwise return any warnings."""
        env = load_envelope()["stage2"]
        for value, key, unit in ((self.voltage_kv, "pulse_voltage_kv", "kV"), (self.frequency_khz, "pulse_frequency_khz", "kHz"),
                                 (self.power_w, "average_power_w", "W")):
            low, high = env[key]["min"], env[key]["max"]
            if not low <= value <= high:
                raise PulseBlocked(f"{key} = {value} {unit} is outside {low}-{high} {unit} (envelope)")
        if not self.width_us > 0:
            raise PulseBlocked("the pulse width must be greater than zero")
        rules = env["pulse_rules"]
        if self.duty_cycle >= rules["duty_cycle_block_at"] - 1e-9:  # 100 us x 10 kHz is 0.9999999999999999 in floating point
            raise PulseBlocked(f"duty cycle {self.duty_cycle:.0%} >= 100 %: the pulses would overlap (E5)")
        if self.duty_cycle > rules["duty_cycle_warn_above"]:
            return [f"duty cycle {self.duty_cycle:.0%} is above 50 %: the supply is barely pulsed"]
        return []
