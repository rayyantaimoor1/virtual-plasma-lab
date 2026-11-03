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
