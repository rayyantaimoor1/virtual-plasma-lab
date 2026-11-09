"""The anomaly log: every check, its severity and likely cause, and whether it was reviewed (Phase 12, FR13.7, E24).

Every statement uses ? placeholders, as in the session store (SEC-4).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from plasma_twin.storage.db import DEFAULT_DB_PATH, connect, init_db

COLUMNS = ("id", "checked_at", "source", "detector", "model_id", "score", "severity", "likely_cause", "range_check",
           "reviewed", "reviewed_at")


@dataclass(frozen=True)
class LogEntry:
    id: int
    checked_at: str
    source: str
    detector: str
    model_id: str
    score: float
    severity: str
    likely_cause: str
    range_check: str
    reviewed: bool
    reviewed_at: str | None


class AnomalyLog:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self.path = path
        init_db(path)

    def add(self, source: str, detector: str, model_id: str, score: float, severity: str, likely_cause: str,
            range_check: str) -> int:
        """Record one anomaly check with parameterised SQL (FR13.7, SEC-4); returns its entry number."""
        conn = connect(self.path)
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO anomaly_log (source, detector, model_id, score, severity, likely_cause, range_check) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", (source, detector, model_id, float(score), severity, likely_cause, range_check))
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def list(self) -> list[LogEntry]:
        """Oldest first, so the score history reads left to right (FR13.4)."""
        conn = connect(self.path)
        try:
            rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM anomaly_log ORDER BY id").fetchall()
            return [LogEntry(**{**dict(r), "reviewed": bool(r["reviewed"])}) for r in rows]
        finally:
            conn.close()

    def mark_reviewed(self, entry_id: int) -> None:
        """Mark a flagged check as reviewed, with the time (FR13.7)."""
        conn = connect(self.path)
        try:
            with conn:
                changed = conn.execute("UPDATE anomaly_log SET reviewed = 1, reviewed_at = datetime('now') WHERE id = ?",
                                       (int(entry_id),)).rowcount
            if changed == 0:
                raise ValueError(f"no anomaly log entry {entry_id}")
        finally:
            conn.close()

    def to_csv(self) -> str:
        """The whole log as CSV for export (FR13.7)."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        for entry in self.list():
            writer.writerow([getattr(entry, c) for c in COLUMNS])
        return buffer.getvalue()
