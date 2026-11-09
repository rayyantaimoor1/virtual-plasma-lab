"""Headless smoke runs of every Stage 1 screen with Streamlit's own AppTest (Phase 6).

Each screen must run without an exception and show its key content. The full M1 -> M7 workflow is
also clicked through by hand in the browser (BUILD_STEPS.md, Phase 6).
"""
import sys
from pathlib import Path

import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

APP = Path(__file__).resolve().parents[1] / "app"
STATUS = check_reference_data()
needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in STATUS.values()),
                                reason="the LXCat and NIST files have not been downloaded here")
streamlit_testing = pytest.importorskip("streamlit.testing.v1")


def use_database(monkeypatch, path) -> None:
    """Point the app at a database and drop its cached stores, which would otherwise outlive one test."""
    monkeypatch.setenv("PLASMA_TWIN_DB", str(path))
    import common
    common.store.clear()
    common.measured_store.clear()
    common.anomaly_log.clear()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(APP))
    use_database(monkeypatch, tmp_path / "screens.db")
    yield


def open_screen(relative: str, has_run: bool = True):
    at = streamlit_testing.AppTest.from_file(str(APP / relative), default_timeout=300)
    if has_run:
        at.session_state["has_run"] = True
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def text_of(at) -> str:
    parts = [m.value for m in at.markdown] + [s.value for s in at.success] + [i.value for i in at.info]
    parts += [w.value for w in at.warning] + [e.value for e in at.error] + [m.label for m in at.metric]
    return " ".join(str(p) for p in parts)


@needs_data
def test_home_runs_and_lists_reference_data() -> None:
    at = open_screen("Home.py", has_run=False)
    assert any("Run the default experiment" in b.label for b in at.button)
    assert "Reference data" in " ".join(h.value for h in at.subheader)


@needs_data
def test_quick_start_is_one_click_to_results() -> None:
    """USE-1: a new user runs the default experiment in at most two clicks; it takes one."""
    at = open_screen("Home.py", has_run=False)
    next(b for b in at.button if "Run the default experiment" in b.label).click().run()
    assert not at.exception
    assert at.session_state["has_run"]
    assert "Electron temperature T_e" in text_of(at)  # the Results screen is now showing


@needs_data
def test_chamber_screen_flags_an_out_of_range_value() -> None:
    at = open_screen("pages/1_Chamber_configuration.py", has_run=False)
    assert "Every parameter is inside the operating envelope" in text_of(at)
    next(n for n in at.number_input if n.label == "Electrode gap (cm)").set_value(50.0).run()  # typed like a user
    assert "smaller than the chamber height" in text_of(at)
    run_button = next(b for b in at.button if "Run simulation" in b.label)
    assert run_button.disabled  # an invalid configuration cannot be run


@needs_data
@pytest.mark.parametrize(("page", "expected"), [
    ("pages/2_Results.py", "Volume-averaged n_e"),
    ("pages/3_Virtual_OES.py", "Identified Ar I lines"),
    ("pages/4_OES_analysis.py", "Boltzmann plot"),
    ("pages/5_Langmuir_probe.py", "Floating potential V_f"),
    ("pages/6_Comparison.py", "Excitation temperature"),
])
def test_each_stage1_screen_runs(page: str, expected: str) -> None:
    at = open_screen(page)
    headings = " ".join(h.value for h in at.subheader)
    assert expected in text_of(at) + headings


def test_screens_without_a_run_say_so() -> None:
    at = open_screen("pages/2_Results.py", has_run=False)
    assert "No plasma has been simulated yet" in text_of(at)


@needs_data
def test_save_then_list_then_delete_with_confirmation() -> None:
    at = open_screen("pages/2_Results.py")
    at.text_input[0].input("first run").run()
    next(b for b in at.button if "Save as session" in b.label).click().run()
    assert "Saved as S-0001" in text_of(at)
    sessions = open_screen("pages/7_Sessions.py", has_run=False)
    sessions.multiselect[0].select("S-0001").run()
    next(b for b in sessions.button if b.label == "Delete selected").click().run()
    assert "permanently" in text_of(sessions)  # asks first (FR11.4)
    next(b for b in sessions.button if "Yes, delete" in b.label).click().run()
    assert not sessions.exception
    assert "No sessions match" in text_of(sessions)


@needs_data
def test_home_has_four_entry_points_and_ai_status() -> None:
    """FR1.1, FR1.5."""
    at = open_screen("Home.py", has_run=False)
    markdown = text_of(at)
    for entry in ("Stage 1", "Stage 2", "Diagnostics & data", "AI module"):
        assert entry in markdown
    assert any(b.label == "View all sessions" for b in at.button) or "No saved sessions yet" in " ".join(c.value for c in at.caption)


@needs_data
def test_admixture_field_is_disabled_outside_the_mixture_and_flow_is_shown() -> None:
    """FR2.5, FR2.10, FR2.12."""
    at = open_screen("pages/1_Chamber_configuration.py", has_run=False)
    n2 = next(n for n in at.number_input if n.label.startswith("N₂ flow"))
    assert n2.disabled and n2.value == 0.0
    assert "N₂ 0.0 sccm" in " ".join(c.value for c in at.caption)
    assert "Model regime" in text_of(at)
    at.radio[0].set_value("Ar+N2").run()
    assert not next(n for n in at.number_input if n.label.startswith("N₂ flow")).disabled
    assert "N₂ 15.0 sccm" in " ".join(c.value for c in at.caption)
    assert "N₂ admixture (% of Ar flow)" in at.selectbox[-1].options


@needs_data
def test_oes_screen_lists_line_details_and_toggles_species() -> None:
    """FR4.2, FR4.5."""
    at = streamlit_testing.AppTest.from_file(str(APP / "pages/3_Virtual_OES.py"), default_timeout=300)
    at.session_state["has_run"] = True
    at.run()
    assert not at.exception
    assert {"E_k (eV)", "g_k A_ki (s⁻¹)", "Relative intensity", "In Boltzmann plot"} <= set(at.dataframe[0].value.columns)
    o_i = next(c for c in at.checkbox if c.label == "O I")
    assert o_i.disabled  # no oxygen lines yet; only species in the mixture can be shown
    next(c for c in at.checkbox if c.label == "Ar I").uncheck().run()
    assert not at.exception


@needs_data
def test_oes_analysis_shows_populations_and_gas_temperature() -> None:
    """FR5.4, FR5.6."""
    at = open_screen("pages/4_OES_analysis.py")
    headings = " ".join(h.value for h in at.subheader)
    assert "Level populations against a Boltzmann distribution" in headings and "Gas temperature" in headings
    assert "Not in equilibrium" in text_of(at)


@needs_data
def test_probe_screen_reports_oml_density_type_and_smoothing() -> None:
    """FR6.1, FR6.6, FR6.8."""
    at = open_screen("pages/5_Langmuir_probe.py")
    assert "n_e (OML ion current)" in text_of(at)
    assert at.selectbox[0].value == "Single cylindrical probe"
    assert "Savitzky-Golay" in " ".join(c.value for c in at.caption)


@needs_data
def test_underwater_configuration_blocks_overlapping_pulses() -> None:
    """FR8.4, E5: 100 us at 10 kHz cannot run."""
    at = open_screen("pages/8_Underwater_configuration.py", has_run=False)
    assert "Every parameter is inside the operating envelope" in text_of(at)
    next(n for n in at.number_input if n.label == "Repetition frequency (kHz)").set_value(10.0).run()
    next(n for n in at.number_input if n.label == "Pulse width (µs)").set_value(100.0).run()
    assert "overlap" in text_of(at)
    assert next(b for b in at.button if "Run disinfection simulation" in b.label).disabled


@needs_data
def test_underwater_results_show_disinfection_and_save_a_stage2_session() -> None:
    """FR9.1-FR9.6."""
    at = streamlit_testing.AppTest.from_file(str(APP / "pages/9_Underwater_results.py"), default_timeout=300)
    at.session_state["has_run2"] = True
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    labels = text_of(at)
    assert "Log reduction at the treatment time" in labels and "n_e from the H-alpha Stark width" in labels
    headings = " ".join(h.value for h in at.subheader)
    for part in ("Reactive species in the water", "Survival curve (Hom model)", "Underwater emission spectrum",
                 "Water before and after treatment"):
        assert part in headings
    at.text_input[0].input("underwater run").run()
    next(b for b in at.button if "Save as session" in b.label).click().run()
    saved = text_of(at)
    assert "Saved as S-" in saved  # the cached store may hold earlier tests' sessions, so the number is not fixed
    session_id = saved.split("Saved as ")[1][:6]
    sessions = open_screen("pages/7_Sessions.py", has_run=False)
    assert not sessions.exception
    table = sessions.dataframe[0].value
    assert table.loc[table["Session"] == session_id, "Stage"].tolist() == [2]



def open_as_researcher(relative: str, has_run: bool = True):
    at = streamlit_testing.AppTest.from_file(str(APP / relative), default_timeout=300)
    at.session_state["role"] = "Researcher"
    if has_run:
        at.session_state["has_run"] = True
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@needs_data
def test_measured_data_screen_is_for_researchers_only() -> None:
    at = open_screen("pages/10_Measured_data.py", has_run=False)
    assert "Researcher role" in text_of(at)
    assert not at.subheader


@needs_data
def test_measured_data_screen_lists_files_and_runs_validation(measured_set, monkeypatch) -> None:
    """FR10.5-FR10.8 on the screen, with the synthetic validation set."""
    use_database(monkeypatch, measured_set[0].db_path)
    at = open_as_researcher("pages/10_Measured_data.py", has_run=False)
    assert {"Import a file", "Validation set", "Validation"} <= {h.value for h in at.subheader}
    assert {measured_set[1], measured_set[2], measured_set[3]} <= set(at.dataframe[0].value["File"])
    next(b for b in at.button if "Run validation" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "1 non-citable file(s) will appear in exports only as anonymised" in text_of(at)


@needs_data
def test_researcher_overlays_and_imported_analysis(measured_set, monkeypatch) -> None:
    """FR4.6 overlay on M4, FR5.1 imported spectrum on M5, FR6.9 imported I-V curve on M6."""
    use_database(monkeypatch, measured_set[0].db_path)
    _, probe_id, oes_id, _ = measured_set
    m4 = open_as_researcher("pages/3_Virtual_OES.py")
    next(s for s in m4.selectbox if "Overlay a measured" in s.label).set_value(oes_id).run()
    assert not m4.exception and any("normalised to their peak" in c.value for c in m4.caption)
    m5 = open_as_researcher("pages/4_OES_analysis.py")
    next(s for s in m5.selectbox if "Spectrum to analyse" in s.label).set_value(oes_id).run()
    assert not m5.exception and f"Analysing measured file {oes_id}" in text_of(m5)
    m6 = open_as_researcher("pages/5_Langmuir_probe.py")
    next(s for s in m6.selectbox if "measured I-V curve" in s.label).set_value(probe_id).run()
    assert not m6.exception and f"Analysing measured file {probe_id}" in text_of(m6)
    assert "Floating potential V_f" in text_of(m6)


@needs_data
def test_sessions_export_panel_offers_pdf_csv_and_png() -> None:
    at = open_screen("pages/2_Results.py")
    next(b for b in at.button if "Save as session" in b.label).click().run()
    sessions = open_screen("pages/7_Sessions.py", has_run=False)
    assert "Export" in [h.value for h in sessions.subheader]
    assert "0 non-citable measured files are excluded (E19)" in text_of(sessions)


@pytest.fixture
def ai_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("PLASMA_TWIN_MODELS", str(tmp_path / "models"))
    monkeypatch.setenv("PLASMA_TWIN_AI_DATA", str(tmp_path / "ai"))
    return tmp_path


def test_ai_training_screen_shows_datasets_and_gates_training(ai_folders) -> None:
    """FR16.1, E23: everyone sees the dataset settings; only a Researcher may train."""
    at = open_screen("pages/11_AI_training.py", has_run=False)
    assert {"Training data", "Train a model", "Model registry"} <= {h.value for h in at.subheader}
    assert at.dataframe[0].value["Settings locked"].tolist() == ["2026-11-04", "2026-11-04"]
    assert "Training is for the Researcher role" in text_of(at)


@needs_data
def test_ai_training_screen_lists_a_registered_model_with_its_evaluation(ai_folders) -> None:
    """FR16.3-FR16.5 with a small dataset and one trained model."""
    from plasma_twin.ai import datasets
    from plasma_twin.ai.registry import Registry
    from plasma_twin.ai.training import train
    # one process: a process pool started after Streamlit's AppTest has run in this interpreter crashes on Windows
    frame, card = datasets.build(1, runs=30, workers=1)
    datasets.save(frame, card)
    model = train("spectrum_to_te_ne", "xgboost", frame, card, Registry())
    at = open_as_researcher("pages/11_AI_training.py", has_run=False)
    table = at.dataframe[1].value
    assert table["Model"].tolist() == [model.model_id] and table["Status"].tolist() == ["current"]
    assert "Evaluation and model card" in [h.value for h in at.subheader]
    assert any("Paired bootstrap" in c.value for c in at.caption)


@needs_data
def test_ai_spectrum_screen_without_a_model_shows_only_the_physics(ai_folders) -> None:
    """M12, E22: with no current model the AI estimate is absent and the physics fit is still shown."""
    at =open_screen("pages/12_AI_spectrum.py")
    assert "No current AI model" in text_of(at)
    assert "T_e (CR-model line-ratio fit)" in text_of(at) and "T_e (AI estimate)" not in text_of(at)


@needs_data
def test_ai_spectrum_screen_puts_the_ai_estimate_next_to_the_physics(ai_folders) -> None:
    """M12 with a Phase 10 model trained on the locked dataset (physics comparison skipped to keep the test short)."""
    from plasma_twin.ai import datasets, inference
    from plasma_twin.ai.registry import Registry
    if not (datasets.DATA_DIR / f"{datasets.dataset_id(1)}.parquet").exists():
        pytest.skip("the locked Stage 1 dataset has not been built here")
    frame, card = datasets.load(datasets.dataset_id(1), folder=datasets.DATA_DIR)
    model = inference.train("xgboost", frame, card, Registry(), with_physics=False)
    at = open_screen("pages/12_AI_spectrum.py")
    text = text_of(at)
    assert "T_e (AI estimate)" in text and "T_e (CR-model line-ratio fit)" in text
    assert any("90 % interval" in c.value for c in at.caption) and any(model.model_id in c.value for c in at.caption)


def test_ai_surrogate_screen_without_a_model_says_so(ai_folders) -> None:
    """M15, E22: no current surrogate means no map, only a clear message."""
    at = open_screen("pages/13_AI_surrogate.py", has_run=False)
    assert "No current surrogate for this stage" in text_of(at) and not at.subheader


@needs_data
def test_ai_surrogate_screen_maps_explains_and_checks_with_the_twin(ai_folders) -> None:
    """FR15.1-FR15.6 with a Stage 2 surrogate (timing skipped to keep the test short)."""
    from plasma_twin.ai import datasets
    from plasma_twin.ai import surrogate as sg
    from plasma_twin.ai.registry import Registry
    if not (datasets.DATA_DIR / f"{datasets.dataset_id(2)}.parquet").exists():
        pytest.skip("the locked Stage 2 dataset has not been built here")
    table, _ = datasets.load(datasets.dataset_id(2), folder=datasets.DATA_DIR)
    sg.train(2, "xgboost", Registry(), table=table, timing=False)
    at = streamlit_testing.AppTest.from_file(str(APP / "pages/13_AI_surrogate.py"), default_timeout=300)
    at.run()
    next(r for r in at.radio if r.label == "Stage").set_value(2).run()
    assert not at.exception, [e.value for e in at.exception]
    headings = {h.value for h in at.subheader}
    assert {"Fast map (surrogate)", "Check a point with the twin", "Global importance (SHAP)", "Why this value? (open configuration)"} <= headings
    assert any("the contributions add up exactly" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Check with twin").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Surrogate and twin" in text_of(at) and at.dataframe[0].value["Value shown"].str.contains("surrogate|twin").all()


def test_ai_anomaly_screen_without_a_detector_says_so(ai_folders) -> None:
    at = open_screen("pages/14_AI_anomaly.py", has_run=False)
    assert "No current anomaly detector" in text_of(at)


@needs_data
def test_ai_anomaly_screen_checks_logs_reviews_and_exports(ai_folders) -> None:
    """FR13.1-FR13.7 with the detector trained on the locked dataset (the twin's expectation from the cache)."""
    import json
    import shutil

    from plasma_twin.ai import anomaly, datasets
    from plasma_twin.ai.registry import Registry
    from plasma_twin.probe.iv_model import ProbeSettings
    expected = datasets.DATA_DIR / f"{datasets.dataset_id(1)}-expected.parquet"
    if not expected.exists():
        pytest.skip("the twin's expectation has not been computed here (scripts/train_anomaly.py)")
    frame, card = datasets.load(datasets.dataset_id(1), folder=datasets.DATA_DIR)
    datasets.data_dir().mkdir(parents=True, exist_ok=True)
    shutil.copy(expected, datasets.data_dir() / expected.name)  # the test's own data folder gets the cached expectation
    anomaly.train(frame, card, Registry(), workers=1)
    at = streamlit_testing.AppTest.from_file(str(APP / "pages/14_AI_anomaly.py"), default_timeout=300)
    at.session_state["probe_settings"] = json.dumps(ProbeSettings.defaults(rf_amplitude_v=20.0).__dict__, sort_keys=True)
    at.run()
    next(b for b in at.button if b.label == "Run anomaly check").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.dataframe[0].value["Severity"].tolist()[0] in ("Warning", "Critical")  # RF left on the probe
    assert "flagged (E24)" in text_of(at) and "Why this score?" in {h.value for h in at.subheader}
    next(b for b in at.button if b.label == "Mark reviewed").click().run()
    assert not at.exception and at.dataframe[1].value["Reviewed"].tolist() == ["yes"]


def test_ai_recommend_screen_without_a_surrogate_says_so(ai_folders) -> None:
    """M14, E22: the recommender needs a surrogate to search on."""
    at = open_screen("pages/15_AI_recommend.py", has_run=False)
    assert "No current surrogate for this stage" in text_of(at)


@needs_data
def test_ai_recommend_screen_verifies_candidates_and_applies_one(ai_folders) -> None:
    """FR14.1-FR14.8 with a Stage 2 surrogate: twin-verified candidates, what-if, save and apply."""
    from plasma_twin.ai import datasets
    from plasma_twin.ai import surrogate as sg
    from plasma_twin.ai.registry import Registry
    if not (datasets.DATA_DIR / f"{datasets.dataset_id(2)}.parquet").exists():
        pytest.skip("the locked Stage 2 dataset has not been built here")
    table, _ = datasets.load(datasets.dataset_id(2), folder=datasets.DATA_DIR)
    sg.train(2, "xgboost", Registry(), table=table, timing=False)
    at = streamlit_testing.AppTest.from_file(str(APP / "Home.py"), default_timeout=300)  # from Home, so switch_page knows every page
    at.run()
    at.switch_page("pages/15_AI_recommend.py").run()
    next(r for r in at.radio if r.label == "Stage").set_value(2).run()
    next(b for b in at.button if b.label == "Find settings").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Ranked candidates (every outcome re-simulated by the twin)" in {h.value for h in at.subheader}
    ranked = at.dataframe[0].value
    assert ranked["Goal met (twin)"].tolist()[0] == "yes" and "Log reduction, twin-verified" in ranked.columns
    assert "The twin confirms the goal" in text_of(at)
    next(b for b in at.button if b.label == "Re-simulate with the twin").click().run()
    assert not at.exception and any("re-simulated by the digital twin" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Apply to the configuration screen").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["config2"]["power_w"] < 20 and not at.session_state["has_run2"]  # filled, not run


# ------------------------------------------------------------------ REL-2 (Phase 14): every event gives a message, never a trace
@needs_data
@pytest.mark.xfail(strict=True, reason="measured 9 Nov 2026 (Phase 14, REL-2): the Results screen catches no SolverFailure, so E4 "
                                       "reaches the user as an error trace, not a message (FR17.4)")
def test_a_solver_failure_shows_a_message_not_a_trace(monkeypatch) -> None:
    import common

    from plasma_twin.stage1.global_model import SolverFailure

    def fails(config):
        raise SolverFailure("the particle balance has no T_e between 0.55 and 19.5 eV")

    monkeypatch.setattr(common.svc, "run", fails)
    common.cached_run.clear()
    at = streamlit_testing.AppTest.from_file(str(APP / "pages/2_Results.py"), default_timeout=300)
    at.session_state["has_run"] = True
    at.run()
    assert not at.exception and "converge" in text_of(at).lower()  # a message, not a trace


@needs_data
@pytest.mark.xfail(strict=True, reason="measured 9 Nov 2026 (Phase 14, REL-2): saving a session catches no database error, so E18 "
                                       "reaches the user as an error trace; there is no retry and no message (FR17.15)")
def test_a_failed_session_save_shows_a_message_and_keeps_the_results(monkeypatch) -> None:
    import sqlite3

    import common

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    at = open_screen("pages/2_Results.py")
    monkeypatch.setattr(common.store(), "save", locked)
    next(b for b in at.button if "Save as session" in b.label).click().run()
    assert not at.exception and "not saved" in text_of(at).lower()
