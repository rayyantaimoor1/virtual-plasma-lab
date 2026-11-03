"""Bubble plasma model (Phase 7): T_e balance, energy branching, afterglow conservation, power share."""
import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_itikawa_h2o")),
                                reason="the LXCat files have not been downloaded here")


def inputs(**overrides):
    from plasma_twin.config.loader import load_envelope
    from plasma_twin.stage2.bubble_model import BubbleInputs
    from plasma_twin.stage2.pulse import PulseSettings
    values = dict(pulse=PulseSettings.defaults(), water_temperature_c=25.0, gap_mm=2.0, o2_flow_sccm=100.0,
                  with_water_vapour=True, power_share=load_envelope()["stage2"]["power_share"]["default"])
    values.update(overrides)
    return BubbleInputs(**values)


def test_vapour_pressure_is_continuous_across_the_two_antoine_ranges() -> None:
    from plasma_twin.stage2.bubble_model import water_vapour_pressure_pa
    low, high = water_vapour_pressure_pa(303.0), water_vapour_pressure_pa(304.0)
    assert low < high < 1.07 * low  # 1 K apart: about 6 % higher, no jump between the two coefficient sets


@needs_data
def test_te_balances_ionization_and_attachment() -> None:
    from plasma_twin.stage2.bubble_model import h2o_rates, o2_rates, solve_te
    te = solve_te(0.03)
    o2, h2o = o2_rates()[0], h2o_rates()[0]
    gain = 0.97 * o2.k("ionization", te) + 0.03 * h2o.k("ionization", te)
    loss = 0.97 * o2.k("attachment", te) + 0.03 * h2o.k("attachment", te)
    assert gain == pytest.approx(loss, rel=1e-5)


@needs_data
def test_energy_shares_add_up_to_one() -> None:
    from plasma_twin.stage2.bubble_model import branching, solve_te
    _, _, shares = branching(solve_te(0.03), 0.03)
    assert sum(shares.values()) == pytest.approx(1.0)


@needs_data
def test_afterglow_conserves_oxygen_and_hydrogen_atoms() -> None:
    from plasma_twin.stage2.bubble_model import afterglow
    n = 2.46e25
    start = {"O": 0.02 * n, "O1D": 0.005 * n, "OH": 0.002 * n, "H": 0.002 * n, "O2": 0.95 * n, "H2O": 0.03 * n}

    def atoms(d):
        o = (d["O"] + d["O1D"] + 3 * d.get("O3", 0) + d["OH"] + 2 * d.get("HO2", 0) + 2 * d.get("H2O2", 0)
             + 2 * d["O2"] + d["H2O"])
        h = d["OH"] + d["H"] + d.get("HO2", 0) + 2 * d.get("H2O2", 0) + 2 * d["H2O"] + 2 * d.get("H2", 0)
        return o, h

    end = afterglow(start, 298.15, 2e-4)
    assert atoms(end)[0] == pytest.approx(atoms(start)[0], rel=1e-6)
    assert atoms(end)[1] == pytest.approx(atoms(start)[1], rel=1e-6)


@needs_data
def test_envelope_default_power_share_matches_the_validity_rule() -> None:
    from plasma_twin.config.loader import load_envelope
    from plasma_twin.stage2.bubble_model import default_power_share, solve
    assert load_envelope()["stage2"]["power_share"]["default"] == pytest.approx(default_power_share(), abs=1e-3)
    result = solve(inputs())
    assert result.dissociated_o2_fraction <= 0.10
    assert result.warnings == ()


@needs_data
def test_o2_only_makes_no_water_products_and_dry_ozone_is_efficient() -> None:
    from plasma_twin.stage2.bubble_model import solve
    result = solve(inputs(with_water_vapour=False))
    assert result.water_fraction == 0
    assert result.production_mol_s["H2O2"] < 1e-30 and result.production_mol_s["OH"] < 1e-30  # zero up to round-off
    o_atoms = result.yields_per_j["O"] * result.inputs.power_share * result.inputs.pulse.power_w / 6.02214076e23
    assert result.production_mol_s["O3"] > 0.9 * o_atoms  # without water almost every O atom becomes O3


@needs_data
def test_full_power_share_is_capped_and_warned() -> None:
    from plasma_twin.stage2.bubble_model import solve
    result = solve(inputs(power_share=1.0))
    assert result.dissociated_o2_fraction == 1.0
    assert any("capped" in w for w in result.warnings)
    assert np.isfinite(result.ne_m3)
