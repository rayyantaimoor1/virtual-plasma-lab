"""Saved sessions: save, list, search, open, compare and delete (Phase 6; FR3.9, FR11.1-FR11.4, SEC-4).

SAFETY RULES (BUILD_STEPS.md, Phase 6):
- Every statement uses ? placeholders. A note is passed to SQL as data, never pasted into it, and a
  search is matched in Python, so an "injection" string is stored and searched for as plain text (SEC-4).
- IDs come from an AUTOINCREMENT key and are shown as S-0001, so a deleted ID is never reused (FR3.9).
- delete_sessions refuses to act unless called with confirmed=True; the screen only passes it after
  a second, explicit click (FR11.4).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plasma_twin.storage.db import DEFAULT_DB_PATH, connect, init_db

ID_PATTERN = re.compile(r"^S-(\d{4,})$")


class SessionError(ValueError):
    """A session request that cannot be carried out (unknown ID, unconfirmed delete, bad comparison)."""


def format_id(number: int) -> str:
    return f"S-{number:04d}"


def parse_id(session_id: str) -> int:
    match = ID_PATTERN.match(session_id.strip())
    if not match:
        raise SessionError(f"{session_id!r} is not a session ID (expected S-0001, S-0002, ...)")
    return int(match.group(1))


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    stage: int
    note: str
    model_version: str
    seed: int | None
    created_at: str
    config: dict[str, Any]
    config_hash: str
    results: dict[str, Any]


class SessionStore:
    """All session access goes through here; each method opens and closes its own connection."""

    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self.path = path
        init_db(path)

    def save(self, stage: int, config: dict[str, Any], config_hash: str, results: dict[str, Any], note: str,
             model_version: str, seed: int | None = None, name: str | None = None) -> str:
        """Store a configuration, its results and a note in one transaction; return the new ID."""
        conn = connect(self.path)
        try:
            with conn:  # one transaction: all rows are written or none (REL-3)
                cursor = conn.execute(
                    "INSERT INTO configurations (name, stage, params_json, config_hash) VALUES (?, ?, ?, ?)",
                    (name, stage, json.dumps(config, sort_keys=True), config_hash))
                configuration_id = cursor.lastrowid
                cursor = conn.execute(
                    "INSERT INTO sessions (configuration_id, stage, note, model_version, seed) VALUES (?, ?, ?, ?, ?)",
                    (configuration_id, stage, note, model_version, seed))
                session_number = cursor.lastrowid
                for kind, data in results.items():
                    conn.execute("INSERT INTO results (session_id, kind, data_json) VALUES (?, ?, ?)",
                                 (session_number, kind, json.dumps(data)))
            return format_id(session_number)
        finally:
            conn.close()

    def _record(self, conn: sqlite3.Connection, row: sqlite3.Row) -> SessionRecord:
        results = {r["kind"]: json.loads(r["data_json"]) for r in
                   conn.execute("SELECT kind, data_json FROM results WHERE session_id = ?", (row["id"],))}
        return SessionRecord(format_id(row["id"]), row["stage"], row["note"], row["model_version"], row["seed"],
                             row["created_at"], json.loads(row["params_json"]), row["config_hash"], results)

    _SELECT = ("SELECT s.id, s.stage, s.note, s.model_version, s.seed, s.created_at, c.params_json, c.config_hash "
               "FROM sessions s JOIN configurations c ON c.id = s.configuration_id")

    def list(self, stage: int | None = None, search: str = "", limit: int | None = None) -> list[SessionRecord]:
        """Newest first, optionally filtered by stage and by text in the note or the configuration's values (FR11.1).

        The text search runs in Python on the rows SQL returns, so typed text never reaches SQL at all. It
        looks at values only (for example "Ar+N2", "50.0"), not field names, which would make a search for
        "power" match every session.
        """
        sql, values = self._SELECT, []
        if stage is not None:
            sql += " WHERE s.stage = ?"
            values.append(stage)
        sql += " ORDER BY s.id DESC"
        conn = connect(self.path)
        try:
            records = [self._record(conn, row) for row in conn.execute(sql, values)]
        finally:
            conn.close()
        if search:
            needle = search.casefold()
            records = [r for r in records if needle in r.note.casefold()
                       or needle in " ".join(str(v) for v in r.config.values()).casefold()]
        return records if limit is None else records[: int(limit)]

    def get(self, session_id: str) -> SessionRecord:
        conn = connect(self.path)
        try:
            row = conn.execute(self._SELECT + " WHERE s.id = ?", (parse_id(session_id),)).fetchone()
            if row is None:
                raise SessionError(f"session {session_id} does not exist")
            return self._record(conn, row)
        finally:
            conn.close()

    def compare(self, session_ids: list[str]) -> list[SessionRecord]:
        """2-5 sessions of the same stage, for overlaying their results (FR11.2)."""
        if not 2 <= len(set(session_ids)) <= 5:
            raise SessionError("choose between 2 and 5 different sessions to compare")
        records = [self.get(s) for s in dict.fromkeys(session_ids)]
        if len({r.stage for r in records}) != 1:
            raise SessionError("sessions from different stages cannot be compared")
        return records

    def delete(self, session_ids: list[str], confirmed: bool = False) -> int:
        """Delete sessions permanently, but only when the user has confirmed (FR11.4). Returns how many."""
        if not confirmed:
            raise SessionError("deleting sessions is permanent and needs explicit confirmation")
        numbers = [parse_id(s) for s in session_ids]
        conn = connect(self.path)
        try:
            with conn:
                deleted = 0
                for number in numbers:
                    row = conn.execute("SELECT configuration_id FROM sessions WHERE id = ?", (number,)).fetchone()
                    if row is None:
                        continue
                    conn.execute("DELETE FROM results WHERE session_id = ?", (number,))
                    conn.execute("DELETE FROM sessions WHERE id = ?", (number,))
                    still_used = conn.execute("SELECT 1 FROM sessions WHERE configuration_id = ?",
                                              (row["configuration_id"],)).fetchone()
                    if still_used is None:
                        conn.execute("DELETE FROM configurations WHERE id = ? AND name IS NULL", (row["configuration_id"],))
                    deleted += 1
            return deleted
        finally:
            conn.close()

    def save_named_configuration(self, name: str, stage: int, config: dict[str, Any], config_hash: str) -> None:
        """FR2.13: keep a configuration under a unique name for later reuse."""
        if not name.strip():
            raise SessionError("a configuration name cannot be empty")
        conn = connect(self.path)
        try:
            with conn:
                conn.execute("INSERT INTO configurations (name, stage, params_json, config_hash) VALUES (?, ?, ?, ?)",
                             (name.strip(), stage, json.dumps(config, sort_keys=True), config_hash))
        except sqlite3.IntegrityError as problem:
            raise SessionError(f"a configuration called {name.strip()!r} already exists") from problem
        finally:
            conn.close()

    def named_configurations(self, stage: int) -> dict[str, dict[str, Any]]:
        conn = connect(self.path)
        try:
            return {row["name"]: json.loads(row["params_json"]) for row in conn.execute(
                "SELECT name, params_json FROM configurations WHERE stage = ? AND name IS NOT NULL ORDER BY name",
                (stage,))}
        finally:
            conn.close()
