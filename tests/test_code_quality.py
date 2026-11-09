"""Phase 14 checks kept as tests: MNT-1 (a test per module), MNT-3 (hints and docstrings), SEC-4 (SQL),
SEC-5 (no outbound connection) and USE-5 (status never by colour alone).

The methods were fixed in BUILD_STEPS.md (Phase 14 rules) before any measurement.
"""
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

from plasma_twin.reference.loaders import DataStatus, check_reference_data

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("code_checks", ROOT / "scripts" / "code_checks.py")
checks = importlib.util.module_from_spec(spec)
sys.modules["code_checks"] = checks
spec.loader.exec_module(checks)

needs_data = pytest.mark.skipif(any(s is not DataStatus.OK for s in check_reference_data().values()),
                                reason="the LXCat and NIST files have not been downloaded here")

# Reviewed by hand on 9 November 2026: each joins constant SQL text written in the code (column names, a fixed
# SELECT, the schema version number); every value a user can type is passed as a ? parameter.
REVIEWED_COMPOSED_SQL = {"plasma_twin/storage/anomaly_log.py", "plasma_twin/storage/db.py", "plasma_twin/storage/measured.py",
                         "plasma_twin/storage/sessions.py"}


def test_every_public_function_has_type_hints_and_a_docstring() -> None:
    """MNT-3 (presence; whether a docstring explains the reason is judged by hand on a sample)."""
    total, gaps = checks.function_gaps()
    assert total > 300 and gaps == [], [f"{g.where} {g.name}: {g.missing}" for g in gaps]


def test_every_domain_module_is_named_in_a_test_file() -> None:
    """MNT-1: each domain module has tests that refer to it."""
    assert checks.modules_without_tests() == []


def test_sql_text_is_never_built_from_user_values() -> None:
    """SEC-4: composed SQL only in the four reviewed places; everything else is a literal with ? parameters."""
    found = {where.split(":")[0] for where in checks.unsafe_sql()}
    assert found <= REVIEWED_COMPOSED_SQL, found - REVIEWED_COMPOSED_SQL


def test_status_messages_always_carry_a_word_label() -> None:
    """USE-5: no st.success/info/warning/error outside status(), which adds "OK", "Note", "Warning" or "Error"."""
    assert checks.bare_status_calls() == []


@pytest.fixture
def offline(monkeypatch):
    """Any connection that leaves this computer fails, and is recorded (SEC-5)."""
    attempts: list[object] = []
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            attempts.append(address)
            raise OSError(f"SEC-5 test: outbound connection to {address} blocked")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    return attempts


@needs_data
def test_the_twin_and_the_ai_make_no_outbound_connection(offline) -> None:
    """SEC-5: a Stage 1 run, spectrum, probe curve and Stage 2 run, and the AI where models exist, all offline."""
    from plasma_twin.oes.spectrum import SpectrometerSettings, spectrum_for
    from plasma_twin.probe.analysis import analyse_curve
    from plasma_twin.probe.iv_model import ProbeSettings, generate, plasma_from
    from plasma_twin.services import stage1, stage2
    result = stage1.run(stage1.default_config())
    spectrum = spectrum_for(result, SpectrometerSettings.defaults())
    analyse_curve(generate(plasma_from(result), ProbeSettings.defaults()))
    stage2.summarise(stage2.run(stage2.default_config()))

    from plasma_twin.ai import anomaly, inference, recommend
    from plasma_twin.ai import surrogate as sg
    from plasma_twin.ai.registry import Registry
    registry = Registry()
    if inference.current_models():
        inference.estimate(spectrum, registry.load(inference.current_models()[0].model_id)[0])
    if anomaly.current_models():
        anomaly.assess_stage1_config(registry.load(anomaly.current_models()[0].model_id)[0], stage1.default_config())
    if sg.current_models(2):
        model = registry.load(sg.current_models(2)[0].model_id)[0]
        sg.check_with_twin(model, stage2.default_config())
        recommend.recommend(recommend.Goal("lr_least_energy", 3.0), model, stage2.default_config())
    assert offline == []


def test_streamlit_sends_no_usage_statistics_and_listens_on_loopback() -> None:
    """SEC-5 and SEC-1 as configured: no usage statistics, server bound to 127.0.0.1."""
    import tomllib
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False and config["server"]["address"] == "127.0.0.1"
