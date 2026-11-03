"""Underwater spectrum and Stark n_e (Phase 7, FR9.4, PER-5)."""
import time

import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
needs_data = pytest.mark.skipif(
    any(STATUS[k] is not DataStatus.OK for k in ("lxcat_cross_sections", "lxcat_itikawa_h2o", "nist_h_i", "nist_o_i")),
    reason="the LXCat and NIST files have not been downloaded here")


def test_stark_relation_inverts_exactly() -> None:
    from plasma_twin.stage2.uw_oes import ne_from_stark, stark_fwhm_nm
    for ne in (1e20, 3.3e21, 1e23):
        assert ne_from_stark(stark_fwhm_nm(ne)) == pytest.approx(ne)
    assert stark_fwhm_nm(1e23) == pytest.approx(0.833, rel=1e-3)  # van der Horst et al.: about 0.8 nm at 1e23 m^-3


@pytest.fixture(scope="module")
def bubble():
    from plasma_twin.services import stage2
    return stage2.run(stage2.default_config()).bubble


@needs_data
@pytest.mark.parametrize("noise", [0.0, 1.0])
def test_stark_width_inverts_back_to_the_model_ne(bubble, noise) -> None:
    from plasma_twin.oes.spectrum import SpectrometerSettings
    from plasma_twin.stage2.uw_oes import build, stark_density
    spectrum = build(bubble, SpectrometerSettings.defaults(start_nm=650, end_nm=663, noise_percent=noise))
    tolerance = 1e-3 if noise == 0 else 0.05  # BUILD_STEPS.md, Phase 7 (as built)
    assert stark_density(spectrum).ne_m3 == pytest.approx(bubble.ne_m3, rel=tolerance)


@needs_data
def test_stark_is_refused_when_the_instrument_is_too_coarse(bubble) -> None:
    from plasma_twin.oes.spectrum import SpectrometerSettings
    from plasma_twin.stage2.uw_oes import StarkUnavailable, build, stark_density
    with pytest.raises(StarkUnavailable, match="instrument"):
        stark_density(build(bubble, SpectrometerSettings.defaults(start_nm=650, end_nm=663, fwhm_nm=0.5)))


@needs_data
def test_one_run_takes_at_most_ten_seconds() -> None:
    """PER-5: a 1 min Stage 2 run within 10 s."""
    from plasma_twin.services import stage2
    start = time.perf_counter()
    stage2.run(stage2.default_config())
    assert time.perf_counter() - start <= 10.0
