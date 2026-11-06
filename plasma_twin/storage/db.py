"""SQLite storage: the database schema and how it is opened.

WHY SQLite: the platform is single-user and local (OE-6), so a database server would add set-up
with no benefit. SQLite is one file and still gives transactions, which protect saved sessions if
the program is killed while saving (REL-3).

The schema version uses SQLite's built-in `PRAGMA user_version`. A later phase that changes the
tables raises SCHEMA_VERSION and adds a migration, so a user's saved sessions are never lost.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2  # 2 (Phase 12): adds anomaly_log; additive, so a version-1 file just gains the table
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "plasma_twin.db"

TABLES = ("configurations", "sessions", "results", "imported_files", "validation_results", "anomaly_log")

# Structured values (settings, results, metadata) are stored as JSON text because Stage 1 and
# Stage 2 have different fields. One column per field would need a table per stage and a schema
# change whenever a model gains an output.
SCHEMA = """
CREATE TABLE IF NOT EXISTS configurations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE,                                 -- FR2.13: optional, unique when given
    stage       INTEGER NOT NULL CHECK (stage IN (1, 2)),
    params_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,                               -- E2: the key of the result cache
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- AUTOINCREMENT, because FR3.9 says session IDs are never reused. Without it, SQLite can give a
-- deleted session's number to a new one, so an old report could point at the wrong run.
CREATE TABLE IF NOT EXISTS sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,      -- shown to users as S-0001
    configuration_id INTEGER NOT NULL REFERENCES configurations(id),
    stage            INTEGER NOT NULL CHECK (stage IN (1, 2)),
    note             TEXT NOT NULL DEFAULT '',
    model_version    TEXT NOT NULL,                          -- REL-4, FR11.3
    seed             INTEGER,                                -- REL-4: reproduces seeded noise
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,                                -- for example plasma_state or spectrum
    data_json  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, kind)
);

-- citable defaults to 0 because the supervisor's data may not be cited unless a Researcher records
-- permission (CON-6, FR10.4). Forgetting to set it must keep data private, never publish it.
CREATE TABLE IF NOT EXISTS imported_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    diagnostic    TEXT NOT NULL CHECK (diagnostic IN ('oes', 'probe')),
    stage         INTEGER NOT NULL CHECK (stage IN (1, 2)),
    original_name TEXT NOT NULL,
    stored_path   TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    metadata_json TEXT NOT NULL,                             -- FR10.2: mandatory metadata
    citable       INTEGER NOT NULL DEFAULT 0 CHECK (citable IN (0, 1)),
    imported_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS validation_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    check_name       TEXT NOT NULL,
    reference_source TEXT NOT NULL,                          -- FR10.6: the citation or file name
    imported_file_id INTEGER REFERENCES imported_files(id),  -- empty for a literature benchmark
    computed_value   REAL,
    reference_value  REAL,
    deviation        REAL,
    tolerance        REAL NOT NULL,                          -- the tolerance actually applied
    passed           INTEGER NOT NULL CHECK (passed IN (0, 1)),
    software_version TEXT NOT NULL,                          -- FR10.7
    run_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase 12, FR13.7: every anomaly check, so flagged runs can be reviewed and the log exported.
CREATE TABLE IF NOT EXISTS anomaly_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,                              -- "open plasma", a session ID or a measured file ID
    detector     TEXT NOT NULL,                              -- full, oes or probe
    model_id     TEXT NOT NULL,
    score        REAL NOT NULL,
    severity     TEXT NOT NULL CHECK (severity IN ('Normal', 'Warning', 'Critical')),
    likely_cause TEXT NOT NULL,
    range_check  TEXT NOT NULL,                              -- flagged, passed or not applicable
    reviewed     INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
    reviewed_at  TEXT,
    checked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database with the settings every connection needs.

    SQLite leaves foreign-key checks off by default and applies the setting per connection, so it
    is set here to stop any part of the program from storing a result for a missing session.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # REL-3: an interrupted save cannot corrupt the file
    return conn


def init_db(path: Path = DEFAULT_DB_PATH) -> None:
    """Create the tables if needed. Safe to call on every start-up (E1).

    It refuses a database from a newer version of the program, because reading tables this code
    does not understand could damage a user's saved sessions.
    """
    conn = connect(path)
    try:
        version = get_schema_version(conn)
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database {path} has schema version {version}, but this program supports up to "
                f"{SCHEMA_VERSION}. Update the program, or move the database file and restart."
            )
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version stored in the database (0 for a brand-new file)."""
    return conn.execute("PRAGMA user_version").fetchone()[0]
