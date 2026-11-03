"""Tests for the operating envelope (plasma_twin/config)."""
from pathlib import Path

import pytest

from plasma_twin.config.loader import find_range_problems, iter_ranges, load_envelope


@pytest.fixture(scope="module")
def envelope() -> dict:
    return load_envelope()


def test_envelope_loads_with_a_version(envelope: dict) -> None:
    assert envelope["config_version"]


def test_every_range_is_complete_and_in_order(envelope: dict) -> None:
    ranges = dict(iter_ranges(envelope))
    # A count guards against the loop passing because it found nothing to check.
    assert len(ranges) == 23  # Stage 1: 4, OES: 4, probe: 7 (RF amplitude added in Phase 5), Stage 2: 8
    for name, rng in ranges.items():
        assert rng["min"] < rng["max"], name
        assert rng["min"] <= rng["default"] <= rng["max"], name


@pytest.mark.parametrize(
    ("section", "name", "low", "default", "high"),
    [
        ("stage1", "rf_power_w", 10, 50, 100),
        ("stage1", "pressure_mbar", 0.1, 0.3, 0.5),
        ("stage1", "ar_flow_sccm", 100, 300, 500),
        ("stage2", "pulse_voltage_kv", 1, 10, 10),
        ("stage2", "pulse_frequency_khz", 5, 5, 10),
        ("stage2", "average_power_w", 10, 100, 100),
        ("stage2", "o2_flow_sccm", 100, 100, 300),
    ],
)
def test_supervisor_values_match_the_srs(envelope: dict, section: str, name: str, low: float, default: float, high: float) -> None:
    rng = envelope[section][name]
    assert (rng["min"], rng["default"], rng["max"]) == (low, default, high)


def test_fixed_values_and_tolerance_match_the_srs(envelope: dict) -> None:
    assert envelope["validation"]["agreement_tolerance_fraction"] == 0.30
    assert envelope["stage1"]["fixed"]["rf_frequency_mhz"] == 13.56
    assert envelope["stage2"]["fixed"]["pressure_atm"] == 1.0
    assert envelope["stage2"]["options"]["electrode_gap_mm"] == [1, 2, 3]
    assert envelope["stage2"]["pulse_rules"]["duty_cycle_block_at"] == 1.0


@pytest.mark.parametrize(
    ("rng", "expected"),
    [
        ({"min": 5, "default": 5, "max": 1}, "min must be below max"),
        ({"min": 1, "default": 9, "max": 5}, "outside"),
        ({"min": 1, "max": 5}, "missing"),
    ],
)
def test_broken_ranges_are_reported(rng: dict, expected: str) -> None:
    problems = find_range_problems({"stage": {"bad": rng}})
    assert problems and expected in problems[0]


def test_loading_a_broken_file_fails_with_the_range_name(tmp_path: Path) -> None:
    bad = tmp_path / "envelope.toml"
    bad.write_text("[stage1.rf_power_w]\nmin = 100\ndefault = 50\nmax = 10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stage1.rf_power_w"):
        load_envelope(bad)
