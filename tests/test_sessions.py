"""Tests for saved sessions (Phase 6; FR3.9, FR11.1-FR11.4, SEC-4)."""
import sqlite3
from pathlib import Path

import pytest

from plasma_twin.storage.db import TABLES, connect
from plasma_twin.storage.sessions import SessionError, SessionStore, format_id, parse_id

CONFIG = {"rf_power_w": 50.0, "pressure_mbar": 0.3, "mixture": "Ar"}
RESULTS = {"plasma_state": {"te_ev": 3.06, "ne_center_m3": 3.2e16}}


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


def save(store: SessionStore, note: str = "", stage: int = 1, config: dict | None = None) -> str:
    return store.save(stage, config or CONFIG, "hash", RESULTS, note, "0.6.0", seed=1)


def test_ids_count_up_and_are_never_reused(store: SessionStore) -> None:
    first, second = save(store), save(store)
    assert (first, second) == ("S-0001", "S-0002")
    store.delete([second], confirmed=True)
    assert save(store) == "S-0003"  # FR3.9


def test_id_format_round_trips() -> None:
    assert format_id(7) == "S-0007" and parse_id("S-0007") == 7
    with pytest.raises(SessionError):
        parse_id("7; DROP TABLE sessions")


def test_sessions_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "restart.db"
    session_id = save(SessionStore(path), note="before restart")
    reopened = SessionStore(path).get(session_id)  # a new store, new connections: like restarting the app
    assert reopened.note == "before restart"
    assert reopened.config == CONFIG and reopened.results == RESULTS
    assert reopened.model_version == "0.6.0" and reopened.seed == 1


def test_list_is_newest_first_and_filters_by_stage_and_text(store: SessionStore) -> None:
    a = save(store, note="argon baseline")
    b = save(store, note="with nitrogen", config={**CONFIG, "mixture": "Ar+N2"})
    c = save(store, note="underwater", stage=2)
    assert [r.session_id for r in store.list()] == [c, b, a]
    assert [r.session_id for r in store.list(stage=1)] == [b, a]
    assert [r.session_id for r in store.list(search="nitrogen")] == [b]
    assert [r.session_id for r in store.list(search="Ar+N2")] == [b]  # matches the configuration too
    assert [r.session_id for r in store.list(limit=1)] == [c]


def test_delete_needs_explicit_confirmation(store: SessionStore) -> None:
    session_id = save(store)
    with pytest.raises(SessionError, match="confirmation"):
        store.delete([session_id])
    assert store.get(session_id)  # still there
    assert store.delete([session_id], confirmed=True) == 1
    with pytest.raises(SessionError):
        store.get(session_id)


@pytest.mark.parametrize("attack", ["'; DROP TABLE sessions; --", "x' OR '1'='1", "%", "_", "\\", "Robert'); --"])
def test_injection_strings_are_just_text(store: SessionStore, attack: str) -> None:
    """SEC-4: stored and searched as plain text; every table survives; wildcards match only themselves."""
    plain = save(store, note="ordinary note")
    tricky = save(store, note=f"note with {attack} inside")
    assert store.get(tricky).note == f"note with {attack} inside"
    assert [r.session_id for r in store.list(search=attack)] == [tricky]
    assert plain not in [r.session_id for r in store.list(search=attack)]
    conn = connect(store.path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert set(TABLES) <= names


def test_compare_needs_two_to_five_sessions_of_one_stage(store: SessionStore) -> None:
    ids = [save(store) for _ in range(6)]
    assert len(store.compare(ids[:2])) == 2
    with pytest.raises(SessionError):
        store.compare(ids[:1])
    with pytest.raises(SessionError):
        store.compare(ids)
    other_stage = save(store, stage=2)
    with pytest.raises(SessionError, match="stages"):
        store.compare([ids[0], other_stage])


def test_named_configurations_are_unique(store: SessionStore) -> None:
    store.save_named_configuration("my baseline", 1, CONFIG, "hash")
    assert store.named_configurations(1) == {"my baseline": CONFIG}
    with pytest.raises(SessionError, match="already exists"):
        store.save_named_configuration("my baseline", 1, CONFIG, "hash")


def test_a_failed_save_leaves_nothing_behind(store: SessionStore) -> None:
    """REL-3: results that cannot be stored roll the whole session back."""
    with pytest.raises(TypeError):
        store.save(1, CONFIG, "hash", {"bad": object()}, "", "0.6.0")
    assert store.list() == []
    conn = connect(store.path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM configurations").fetchone()[0] == 0
    finally:
        conn.close()
    assert isinstance(sqlite3.sqlite_version, str)
