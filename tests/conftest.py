"""Shared fixtures. `measured_set` builds a validation set from the model's own synthetic output (clearly not
measured data, BUILD_STEPS.md Phase 8): a non-citable probe file, a citable Stage 1 spectrum and a citable
Stage 2 H-alpha window, all at the default operating conditions."""
import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

STATUS = check_reference_data()
ALL_DATA = all(s is DataStatus.OK for s in STATUS.values())
SECRET_NAME = "ZQXSECRET_lab_probe.csv"
SECRET_INSTRUMENT = "ZQXSECRET probe system"


@pytest.fixture(scope="session")
def secret_markers() -> tuple[str, str]:
    """The non-citable probe file's name and instrument: neither may appear in any export (SEC-3)."""
    return SECRET_NAME, SECRET_INSTRUMENT


@pytest.fixture(scope="session")
def measured_set(tmp_path_factory):
    if not ALL_DATA:
        pytest.skip("the LXCat and NIST files have not been downloaded here")
    from plasma_twin.data_io.importers import parse
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    from plasma_twin.services import stage1, stage2
    from plasma_twin.stage2.uw_oes import build
    from plasma_twin.storage.measured import MeasuredStore

    folder = tmp_path_factory.mktemp("measured")
    store = MeasuredStore(folder / "t.db", folder / "measured")
    config = stage1.default_config()
    result = stage1.run(config)
    conditions = {k: config[k] for k in ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "mixture", "n2_percent", "o2_percent")}

    curve = generate(plasma_from(result), ProbeSettings.defaults(noise_percent=0.0))
    raw = ("V,I_mA\n" + "\n".join(f"{v:.3f},{1e3 * i:.8e}" for v, i in zip(curve.voltage_v, curve.current_a))).encode()
    probe_id = store.save(parse(SECRET_NAME, raw, "probe"), raw, {"x_column": 0, "y_column": 1, "current_unit": "mA"},
                          {"instrument": SECRET_INSTRUMENT, "measurement_date": "2026-11-01", "conditions": conditions,
                           "probe": {"tip_radius_mm": 0.195, "exposed_length_mm": 5.0}}, 1, citable=False)

    spectrum = spectrum_for(result, SpectrometerSettings.defaults(start_nm=690, end_nm=860, noise_percent=0.0))
    raw = ("nm\tcounts\n" + "\n".join(f"{a:.5f}\t{b:.6e}" for a, b in zip(spectrum.wavelength_nm, spectrum.intensity))).encode()
    oes_id = store.save(parse("lab_oes.txt", raw, "oes"), raw, {"x_column": 0, "y_column": 1},
                        {"instrument": "Echelle", "measurement_date": "2026-11-01", "conditions": conditions,
                         "instrument_fwhm_nm": 0.005}, 1, citable=True)

    config2 = stage2.default_config()
    window = build(stage2.run(config2).bubble, SpectrometerSettings.defaults(start_nm=650, end_nm=663, noise_percent=0.0))
    raw = "\n".join(f"{a:.5f} {b:.6e}" for a, b in zip(window.wavelength_nm, window.intensity)).encode()
    conditions2 = {k: config2[k] for k in ("power_w", "frequency_khz", "width_us", "gap_mm", "o2_flow_sccm", "bubble_gas")}
    uw_id = store.save(parse("uw.txt", raw, "oes"), raw, {"x_column": 0, "y_column": 1},
                       {"instrument": "Echelle", "measurement_date": "2026-11-01", "conditions": conditions2,
                        "instrument_fwhm_nm": 0.005}, 2, citable=True)
    return store, probe_id, oes_id, uw_id
