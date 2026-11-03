"""Shared pieces of the Stage 1 screens: the import path, roles, cached runs and status messages.

Everything here is presentation glue. The physics lives in plasma_twin/ and is reached through
plasma_twin.services.stage1, so the screens never compute anything themselves.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# `streamlit run app/Home.py` puts app/ on the import path, not the project root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from plasma_twin import __version__  # noqa: E402
from plasma_twin.services import stage1 as svc  # noqa: E402
from plasma_twin.storage.sessions import SessionStore  # noqa: E402

ROLES = ("Student", "Researcher")
PAGES = {
    "home": "Home.py",
    "chamber": "pages/1_Chamber_configuration.py",
    "results": "pages/2_Results.py",
    "oes": "pages/3_Virtual_OES.py",
    "oes_analysis": "pages/4_OES_analysis.py",
    "probe": "pages/5_Langmuir_probe.py",
    "compare": "pages/6_Comparison.py",
    "sessions": "pages/7_Sessions.py",
}


def page_setup(title: str) -> None:
    """Every screen starts here: page title, sidebar role switch (FR1.4) and the open configuration."""
    st.set_page_config(page_title=f"{title} - Plasma Digital Twin", layout="wide")
    if "config" not in st.session_state:
        st.session_state["config"] = svc.default_config()
    st.session_state.setdefault("role", ROLES[0])
    with st.sidebar:
        st.session_state["role"] = st.radio("Role", ROLES, index=ROLES.index(st.session_state["role"]),
                                            help="Researchers can import measured data (Phase 8). No login is needed.")
        st.caption(f"Model version {__version__}")
        if st.session_state.get("session_id"):
            st.caption(f"Open session: {st.session_state['session_id']}")


@st.cache_resource
def store() -> SessionStore:
    """The session database. PLASMA_TWIN_DB points it elsewhere, so screen tests never touch real sessions."""
    import os
    path = os.environ.get("PLASMA_TWIN_DB")
    return SessionStore(Path(path)) if path else SessionStore()


def config_json(config: dict) -> str:
    return json.dumps(config, sort_keys=True)


@st.cache_data(show_spinner="Solving the plasma model...", max_entries=64)
def cached_run(config_text: str):
    """Model run cached by the configuration's JSON (the same content as its config_hash, PER-1)."""
    return svc.run(json.loads(config_text))


def current_result():
    """The plasma state of the open configuration, or None if it is invalid or has not been run."""
    if not st.session_state.get("has_run"):
        return None
    config = st.session_state["config"]
    if svc.validate_config(config):
        return None
    return cached_run(config_json(config))


def need_result():
    """Stop the screen with a clear message when there is no plasma state yet (FR3.8)."""
    result = current_result()
    if result is None:
        status("info", "No plasma has been simulated yet. Run one from the Home screen or the chamber configuration.")
        if st.button("Go to chamber configuration"):
            st.switch_page(PAGES["chamber"])
        st.stop()
    return result


def run_and_open_results(config: dict) -> None:
    """Store the configuration, mark it as run, and open the Results screen (FR2.11)."""
    st.session_state["config"] = dict(config)
    st.session_state["has_run"] = True
    st.session_state.pop("session_id", None)
    cached_run(config_json(config))
    st.switch_page(PAGES["results"])


def status(kind: str, text: str) -> None:
    """USE-5: every status has words as well as colour: the label is part of the text."""
    labels = {"ok": ("OK", st.success), "info": ("Note", st.info), "warn": ("Warning", st.warning),
              "error": ("Error", st.error)}
    label, show = labels[kind]
    show(f"**{label}:** {text}")


def axis(fig, x: str, y: str, log_y: bool = False):
    """USE-4: a symbol and an SI unit on every axis."""
    fig.update_layout(xaxis_title=x, yaxis_title=y, margin=dict(l=10, r=10, t=30, b=10), height=380)
    if log_y:
        fig.update_yaxes(type="log")
    return fig


def sci(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}g}"


@st.cache_data(show_spinner="Computing the spectrum...", max_entries=16)
def cached_spectrum(config_text: str, settings_text: str):
    """Spectrum and CR model of the open plasma, cached by configuration and instrument settings."""
    from plasma_twin.oes.cr_model import solve_cr_for
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    plasma = cached_run(config_text)
    return spectrum_for(plasma, SpectrometerSettings(**json.loads(settings_text))), solve_cr_for(plasma)


@st.cache_data(show_spinner="Separating the species...", max_entries=16)
def cached_contributions(config_text: str, settings_text: str):
    """Noise-free part of each species in the spectrum (FR4.2), on the same grid as cached_spectrum."""
    from plasma_twin.oes.spectrum import SpectrometerSettings, species_contributions
    return species_contributions(cached_run(config_text), SpectrometerSettings(**json.loads(settings_text)))


def spectrometer_settings_text() -> str:
    """The instrument settings last used on the OES screen, or the envelope defaults."""
    from plasma_twin.oes.spectrum import SpectrometerSettings
    return st.session_state.get("oes_settings") or json.dumps(SpectrometerSettings.defaults().__dict__, sort_keys=True)


@st.cache_data(show_spinner="Simulating the probe...", max_entries=16)
def cached_probe(config_text: str, settings_text: str):
    """Probe curve and its analysis; the analysis error, if any, is returned as text (E11)."""
    from plasma_twin.probe.analysis import ProbeAnalysisError, analyse_curve
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    curve = generate(plasma_from(cached_run(config_text)), ProbeSettings(**json.loads(settings_text)))
    try:
        return curve, analyse_curve(curve), None
    except ProbeAnalysisError as problem:
        return curve, None, str(problem)


def probe_settings_text() -> str:
    from plasma_twin.probe.iv_model import ProbeSettings
    return st.session_state.get("probe_settings") or json.dumps(ProbeSettings.defaults().__dict__, sort_keys=True)


def metric_grid(items: list[tuple[str, str, str]], per_row: int = 2) -> None:
    """Metrics laid out a few per row, so long values with units are never cut off on narrow screens.

    items: (label, value, help text).
    """
    for start in range(0, len(items), per_row):
        columns = st.columns(per_row)
        for column, (label, value, help_text) in zip(columns, items[start:start + per_row]):
            column.metric(label, value, help=help_text or None)
