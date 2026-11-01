"""Tests for the SQLite schema (plasma_twin/storage/db.py)."""
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from plasma_twin.storage.db import SCHEMA_VERSION, TABLES, connect, get_schema_version, init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "nested" / "test.db"
    init_db(path)
    return path


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_path)
    yield connection
    connection.close()  # Windows cannot delete the temporary folder while the file is open


def add_session(conn: sqlite3.Connection) -> int:
    config = conn.execute(
        "INSERT INTO configurations (stage, params_json, config_hash) VALUES (1, '{}', 'abc')"
    ).lastrowid
    return conn.execute(
        "INSERT INTO sessions (configuration_id, stage, model_version) VALUES (?, 1, '0.1')", (config,)
    ).lastrowid


def test_all_tables_exist(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert set(TABLES) <= {row["name"] for row in rows}


def test_schema_version_is_recorded(conn: sqlite3.Connection) -> None:
    assert get_schema_version(conn) == SCHEMA_VERSION


def test_creating_twice_keeps_existing_data(db_path: Path) -> None:
    conn = connect(db_path)
    session_id = add_session(conn)
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)).fetchone()[0] == 1
    conn.close()


def test_refuses_a_newer_database(db_path: Path) -> None:
    conn = connect(db_path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError, match="schema version"):
        init_db(db_path)


def test_session_ids_are_never_reused(conn: sqlite3.Connection) -> None:
    """FR3.9: a deleted session's number must not be given to a new session."""
    first = add_session(conn)
    conn.execute("DELETE FROM sessions WHERE id = ?", (first,))
    assert add_session(conn) > first


def test_result_needs_an_existing_session(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO results (session_id, kind, data_json) VALUES (999, 'state', '{}')")


def test_deleting_a_session_deletes_its_results(conn: sqlite3.Connection) -> None:
    session_id = add_session(conn)
    conn.execute("INSERT INTO results (session_id, kind, data_json) VALUES (?, 'state', '{}')", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0


def test_imported_files_are_not_citable_by_default(conn: sqlite3.Connection) -> None:
    """CON-6, FR10.4: forgetting to set permission must keep the data private."""
    conn.execute(
        "INSERT INTO imported_files (diagnostic, stage, original_name, stored_path, sha256, metadata_json) "
        "VALUES ('probe', 1, 'run.csv', 'x', 'y', '{}')"
    )
    assert conn.execute("SELECT citable FROM imported_files").fetchone()["citable"] == 0


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO configurations (stage, params_json, config_hash) VALUES (3, '{}', 'a')",
        "INSERT INTO imported_files (diagnostic, stage, original_name, stored_path, sha256, metadata_json) "
        "VALUES ('camera', 1, 'a', 'b', 'c', '{}')",
    ],
)
def test_invalid_values_are_rejected(conn: sqlite3.Connection, statement: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(statement)
