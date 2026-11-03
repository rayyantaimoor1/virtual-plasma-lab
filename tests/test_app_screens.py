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


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PLASMA_TWIN_DB", str(tmp_path / "screens.db"))
    monkeypatch.syspath_prepend(str(APP))
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
    next(n for n in at.number_input if n.label == "Electrode gap").set_value(50.0).run()  # typed like a user
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
