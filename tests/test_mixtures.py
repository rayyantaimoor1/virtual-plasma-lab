"""Tests for argon with N2 and O2 admixtures (Phase 3e)."""
import numpy as np
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data
from plasma_twin.stage1.global_model import InputOutOfRange, default_inputs, solve
from plasma_twin.stage1.mixtures import Composition
from plasma_twin.stage1.sweep import sweep

needs_lxcat = pytest.mark.skipif(check_reference_data()["lxcat_cross_sections"] is not DataStatus.OK,
                                 reason="the LXCat file has not been downloaded here")
MODES = {"Ar+N2": {"n2_percent_of_ar": 5}, "Ar+O2": {"o2_percent_of_ar": 5},
         "Ar+N2+O2": {"n2_percent_of_ar": 5, "o2_percent_of_ar": 5}}


def quick(**overrides):
    """Fixed gas temperature and no flow: faster, and isolates the mixture chemistry."""
    return default_inputs(**{"gas_heating": False, "ar_flow_sccm": 0.0, **overrides})


def test_mole_fractions_follow_the_flows() -> None:
    """5 % of the Ar flow each: Ar : N2 : O2 = 100 : 5 : 5."""
    assert Composition(5, 5).fractions == pytest.approx((100 / 110, 5 / 110, 5 / 110))
    assert Composition(0, 0).fractions == (1.0, 0.0, 0.0)


@pytest.mark.parametrize("override", [{"n2_percent_of_ar": 0.5}, {"o2_percent_of_ar": 12},
                                      {"n2_percent_of_ar": 5, "excited_states": False}])
def test_admixtures_outside_the_envelope_are_refused(override: dict) -> None:
    with pytest.raises(InputOutOfRange):
        solve(default_inputs(**override))


@needs_lxcat
def test_zero_admixture_is_exactly_pure_argon() -> None:
    assert solve(quick(n2_percent_of_ar=0, o2_percent_of_ar=0)).as_dict() == solve(quick()).as_dict()


@pytest.fixture(scope="module")
def solved():
    return {name: solve(quick(**kw)) for name, kw in MODES.items()} | {"Ar": solve(quick())}


@needs_lxcat
@pytest.mark.parametrize("mode", list(MODES))
def test_every_balance_closes_and_energy_is_accounted_for(solved, mode: str) -> None:
    result = solved[mode]
    assert all(r < 1e-8 for r in result.residuals.values()), result.residuals
    assert sum(result.losses_w.values()) == pytest.approx(result.absorbed_power_w, rel=1e-8)


@needs_lxcat
@pytest.mark.parametrize("mode", list(MODES))
def test_charge_is_neutral(solved, mode: str) -> None:
    m = solved[mode].mixture
    positive = sum(m["ion_densities_m3"].values())
    assert positive == pytest.approx(solved[mode].ne_center_m3 + m["negative_ion_density_m3"], rel=1e-10)


@needs_lxcat
@pytest.mark.parametrize("mode", ["Ar+O2", "Ar+N2+O2"])
def test_oxygen_atoms_are_conserved(solved, mode: str) -> None:
    result = solved[mode]
    m = result.mixture
    _, _, x_o2 = Composition(result.inputs.n2_percent_of_ar, result.inputs.o2_percent_of_ar).fractions
    in_chamber = (m["o2_density_m3"] + m["o2a_density_m3"] + m["o_atom_density_m3"] / 2
                  + m["negative_ion_density_m3"] / 2 + m["ion_densities_m3"]["O2+"])
    assert in_chamber == pytest.approx(x_o2 * result.gas_density_m3, rel=1e-10)


@needs_lxcat
@pytest.mark.parametrize("mode", list(MODES))
def test_molecules_quench_argon_metastables(solved, mode: str) -> None:
    assert solved[mode].metastable_density_m3 < solved["Ar"].metastable_density_m3


@needs_lxcat
def test_only_oxygen_makes_the_plasma_electronegative(solved) -> None:
    assert solved["Ar+N2"].mixture["negative_ion_density_m3"] == 0.0
    assert solved["Ar+O2"].mixture["electronegativity"] > 0
    assert solved["Ar+N2+O2"].mixture["electronegativity"] > 0


@needs_lxcat
def test_negative_ions_are_pushed_out_of_the_sheath_edge(solved) -> None:
    """Boltzmann negative ions with T_e / T_g ~ 100 hardly reach the edge (Kemaneci Eq. 11 with alpha_s)."""
    m = solved["Ar+O2"].mixture
    if not m["attachment_dominated"]:
        assert m["sheath_edge_electronegativity"] < 1e-6 * m["electronegativity"]


@needs_lxcat
def test_n2_c_is_excited_by_electrons_and_argon_metastables(solved) -> None:
    m = solved["Ar+N2"].mixture
    assert m["n2c_excitation_m3_s"] > 0
    assert "n2c_excitation_m3_s" not in solved["Ar"].mixture


@needs_lxcat
@pytest.mark.parametrize("mode", list(MODES))
def test_new_ions_appear_and_charge_transfer_feeds_them(solved, mode: str) -> None:
    ions = solved[mode].mixture["ion_densities_m3"]
    assert set(ions) >= {"Ar+"} and len(ions) == 1 + mode.count("+")
    assert all(n > 0 for n in ions.values())


@needs_lxcat
def test_molecular_gas_takes_electron_energy_and_lowers_the_density(solved) -> None:
    assert solved["Ar+N2"].ne_center_m3 < solved["Ar"].ne_center_m3
    assert solved["Ar+O2"].ne_center_m3 < solved["Ar"].ne_center_m3
    assert solved["Ar+N2"].shares_percent("losses")["excitation"] > solved["Ar"].shares_percent("losses")["excitation"]


@needs_lxcat
@pytest.mark.parametrize("mode", list(MODES))
def test_converges_across_the_envelope(mode: str) -> None:
    for power in (10, 55, 100):
        for pressure in (0.1, 0.3, 0.5):
            result = solve(quick(rf_power_w=power, pressure_mbar=pressure, **MODES[mode]))
            assert max(result.residuals.values()) < 1e-8, (mode, power, pressure)


@needs_lxcat
def test_sweep_over_the_admixture_fraction() -> None:
    points = sweep(quick(), "o2_percent_of_ar", [1, 4, 7, 10])
    assert all(p.solved for p in points)
    alphas = [p.result.mixture["electronegativity"] for p in points]
    assert np.all(np.diff(alphas) > 0)  # more O2, more negative ions
