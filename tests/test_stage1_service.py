"""Tests for the Stage 1 application services (Phase 6)."""
import csv
import io
import json

import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.services import stage1 as svc

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")


def test_defaults_are_valid_and_every_preset_fits_the_envelope() -> None:
    assert svc.validate_config(svc.default_config()) == {}
    presets = svc.load_presets()
    assert "default" in presets
    for name, preset in presets.items():
        assert svc.validate_config(preset["config"]) == {}, name
        assert preset["title"] and preset["description"]


@pytest.mark.parametrize(("field", "value", "fragment"), [
    ("rf_power_w", 150.0, "between 10 and 100"), ("pressure_mbar", 0.05, "between 0.1 and 0.5"),
    ("electrode_diameter_cm", 45.0, "smaller than the chamber"), ("electrode_gap_cm", 50.0, "chamber height"),
])
def test_each_bad_field_gets_its_own_message(field: str, value: float, fragment: str) -> None:
    problems = svc.validate_config({**svc.default_config(), field: value})
    assert fragment in problems[field]


def test_admixture_is_checked_only_when_that_gas_is_chosen() -> None:
    config = {**svc.default_config(), "n2_percent": 50.0}
    assert svc.validate_config(config) == {}  # mixture is "Ar", so the N2 field is ignored
    assert "n2_percent" in svc.validate_config({**config, "mixture": "Ar+N2"})


def test_pressure_units() -> None:
    units = svc.pressure_units(0.3)
    assert units["Pa"] == pytest.approx(30.0)
    assert units["mTorr"] == pytest.approx(225.0, rel=1e-3)


def test_config_hash_ignores_key_order_but_not_values() -> None:
    a = svc.default_config()
    b = dict(reversed(list(a.items())))
    assert svc.config_hash(a) == svc.config_hash(b)
    assert svc.config_hash(a) != svc.config_hash({**a, "rf_power_w": 51.0})


def test_downsampling_keeps_every_peak() -> None:
    x = np.linspace(300, 900, 600_000)
    y = np.zeros_like(x)
    peaks = [123_457, 400_001, 599_998]
    y[peaks] = [5.0, 7.0, 3.0]
    xs, ys = svc.downsample_peaks(x, y)
    assert len(xs) <= 4000
    for i in peaks:
        assert y[i] in ys


@needs_lxcat
def test_run_summarise_and_export_round_trip() -> None:
    config = svc.default_config()
    result = svc.run(config)
    summary = svc.summarise(result)
    assert json.loads(json.dumps(summary)) == summary  # plain JSON, so it can be stored
    assert summary["te_ev"] == pytest.approx(result.te_ev)
    assert summary["ne_volume_mean_m3"] < summary["ne_center_m3"]
    text = svc.results_csv(summary, config)
    rows = list(csv.reader(line for line in io.StringIO(text) if not line.startswith("#")))  # skip the FR3.10 header
    assert rows[0] == ["section", "quantity", "value", "unit"]
    assert ["result", "te_ev", str(summary["te_ev"]), "eV"] in rows
    assert any("RF power taken as power absorbed" in a for a in svc.assumptions(result))


def test_invalid_configuration_is_not_run() -> None:
    from plasma_twin.stage1.global_model import InputOutOfRange
    with pytest.raises(InputOutOfRange):
        svc.run({**svc.default_config(), "rf_power_w": 500.0})


def test_admixture_flows_are_a_share_of_the_argon_flow_and_zero_when_not_chosen() -> None:
    config = {**svc.default_config(), "mixture": "Ar+N2", "ar_flow_sccm": 200.0, "n2_percent": 5.0, "o2_percent": 7.0}
    assert svc.admixture_flows_sccm(config) == {"N2": pytest.approx(10.0), "O2": 0.0}


def test_regime_note_gives_the_ion_mean_free_path_and_flags_oxygen() -> None:
    notes = svc.regime_notes(svc.default_config())
    assert "0.138 mm" in notes[0]  # kT / (p sigma) at 0.3 mbar, 300 K, sigma = 1e-18 m^2
    assert any("LI-4" in n for n in svc.regime_notes({**svc.default_config(), "mixture": "Ar+O2"}))


@needs_lxcat
def test_default_run_has_a_collisional_sheath_and_the_csv_names_its_session() -> None:
    from plasma_twin import __version__
    result = svc.run(svc.default_config())
    assert svc.sheath_regime(result)[0]
    text = svc.results_csv(svc.summarise(result), svc.default_config(), "S-0007")
    assert text.startswith(f"# session: S-0007\n# software version: {__version__}\n")
