"""Measured files saved by a Researcher: Phase 8 (FR10.2, FR10.4, FR10.5, CON-6).

RULES (BUILD_STEPS.md, Phase 8): a saved file is copied byte for byte to data/measured/<sha256>.<ext>
(gitignored, so measured data never leave this computer), made read-only, and recorded in the
imported_files table with its metadata, column mapping and units. Citation permission is "not citable"
unless the Researcher ticks it, and is fixed at save time. Nothing is written until every check has
passed. IDs are shown as M-0001 and are never reused (AUTOINCREMENT).
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from plasma_twin.config.loader import load_envelope
from plasma_twin.data_io.importers import EXTENSIONS, FileRejected, ParsedFile, mapped, parse
from plasma_twin.storage.db import DEFAULT_DB_PATH, connect, init_db

DEFAULT_FILES_DIR = DEFAULT_DB_PATH.parent / "measured"


class MeasuredDataError(ValueError):
    """A measured file cannot be saved or found."""


def format_id(number: int) -> str:
    """A measured-file ID such as M-0001 from its row number."""
    return f"M-{number:04d}"


def parse_id(file_id: str) -> int:
    """The row number from a measured-file ID, refusing anything else."""
    if not (file_id.startswith("M-") and file_id[2:].isdigit()):
        raise MeasuredDataError(f"'{file_id}' is not a measured-file ID such as M-0001")
    return int(file_id[2:])


@dataclass(frozen=True)
class MeasuredFile:
    file_id: str
    diagnostic: str
    stage: int
    original_name: str
    metadata: dict[str, Any]
    citable: bool
    imported_at: str
    stored_path: Path


def validate_metadata(diagnostic: str, stage: int, metadata: dict[str, Any]) -> dict[str, str]:
    """FR10.2: every field is mandatory and the operating conditions lie inside the stage's envelope."""
    from plasma_twin.services import stage1, stage2
    problems: dict[str, str] = {}
    if diagnostic == "probe" and stage != 1:
        problems["stage"] = "probe files are Stage 1 only: a Langmuir probe is not used in the underwater discharge"
    if not str(metadata.get("instrument", "")).strip():
        problems["instrument"] = "is required"
    try:
        measured_on = date.fromisoformat(str(metadata.get("measurement_date", "")))
        if measured_on > date.today():
            problems["measurement_date"] = "cannot be in the future"
    except ValueError:
        problems["measurement_date"] = "is required, as YYYY-MM-DD"
    conditions = metadata.get("conditions") or {}
    if stage == 1:
        config = {**stage1.default_config(), **conditions}
        problems.update({f"conditions.{k}": v for k, v in stage1.validate_config(config).items()})
    elif stage == 2:
        stage_problems, _ = stage2.validate_config({**stage2.default_config(), **conditions})
        problems.update({f"conditions.{k}": v for k, v in stage_problems.items()})
    else:
        problems["stage"] = "must be 1 or 2"
    if diagnostic == "oes":
        # CHANGED WHILE BUILDING (before any result): the analysis needs the spectrometer's resolution to
        # integrate lines and to remove the instrument width from H-alpha, so OES files must give it.
        fwhm = metadata.get("instrument_fwhm_nm")
        low, high = (load_envelope()["oes"]["resolution_fwhm_nm"][k] for k in ("min", "max"))
        if fwhm is None or not low <= float(fwhm) <= high:
            problems["instrument_fwhm_nm"] = f"is required, between {low} and {high} nm"
    if diagnostic == "probe":
        env = load_envelope()["probe"]
        geometry = metadata.get("probe") or {}
        for key in ("tip_radius_mm", "exposed_length_mm"):
            value = geometry.get(key)
            low, high = env[key]["min"], env[key]["max"]
            if value is None or not low <= float(value) <= high:
                problems[f"probe.{key}"] = f"is required, between {low} and {high} mm"
    return problems


class MeasuredStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH, files_dir: Path | None = None) -> None:
        self.db_path = db_path
        self.files_dir = files_dir or db_path.parent / "measured"
        init_db(db_path)

    def save(self, parsed: ParsedFile, raw: bytes, mapping: dict[str, Any], metadata: dict[str, Any], stage: int,
             citable: bool = False) -> str:
        """Store a checked file; raise before writing anything if any check fails (E14, FR10.2)."""
        mapped(parsed, mapping["x_column"], mapping["y_column"], mapping.get("current_unit", "A"))  # raises if unusable
        problems = validate_metadata(parsed.diagnostic, stage, metadata)
        if problems:
            raise MeasuredDataError("; ".join(f"{k}: {v}" for k, v in problems.items()))
        conn = connect(self.db_path)
        try:
            duplicate = conn.execute("SELECT id FROM imported_files WHERE sha256 = ?", (parsed.sha256,)).fetchone()
            if duplicate:
                raise MeasuredDataError(f"this file is already saved as {format_id(duplicate['id'])}")
            self.files_dir.mkdir(parents=True, exist_ok=True)
            target = self.files_dir / f"{parsed.sha256}{EXTENSIONS[parsed.diagnostic]}"
            with conn:  # one transaction: the row is written only if the copy succeeded
                cursor = conn.execute(
                    "INSERT INTO imported_files (diagnostic, stage, original_name, stored_path, sha256, metadata_json, citable)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (parsed.diagnostic, stage, parsed.name, target.name, parsed.sha256,
                     json.dumps({**metadata, "mapping": mapping}, sort_keys=True), int(bool(citable))))
                target.write_bytes(raw)
                os.chmod(target, stat.S_IREAD)  # FR10.5: saved files are read-only
            return format_id(cursor.lastrowid)
        finally:
            conn.close()

    def _record(self, row) -> MeasuredFile:
        return MeasuredFile(format_id(row["id"]), row["diagnostic"], row["stage"], row["original_name"],
                            json.loads(row["metadata_json"]), bool(row["citable"]), row["imported_at"],
                            self.files_dir / row["stored_path"])

    def list(self, diagnostic: str | None = None, stage: int | None = None) -> list[MeasuredFile]:
        """Imported files, optionally of one diagnostic or stage, newest first."""
        query, args = "SELECT * FROM imported_files WHERE 1 = 1", []
        if diagnostic:
            query += " AND diagnostic = ?"
            args.append(diagnostic)
        if stage:
            query += " AND stage = ?"
            args.append(stage)
        conn = connect(self.db_path)
        try:
            return [self._record(r) for r in conn.execute(query + " ORDER BY id", args).fetchall()]
        finally:
            conn.close()

    def get(self, file_id: str) -> MeasuredFile:
        """One imported file's record by ID."""
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT * FROM imported_files WHERE id = ?", (parse_id(file_id),)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise MeasuredDataError(f"{file_id} does not exist")
        return self._record(row)

    def load(self, file_id: str) -> tuple[np.ndarray, np.ndarray, MeasuredFile]:
        """The file's two mapped columns (OES: nm, a.u.; probe: V, A), read again from the stored copy."""
        record = self.get(file_id)
        raw = record.stored_path.read_bytes()
        try:
            parsed = parse(record.original_name, raw, record.diagnostic)
        except FileRejected as problem:
            raise MeasuredDataError(f"{file_id}: the stored file no longer reads ({problem})") from problem
        m = record.metadata["mapping"]
        x, y = mapped(parsed, m["x_column"], m["y_column"], m.get("current_unit", "A"))
        return x, y, record

    def delete(self, file_ids: list[str], confirmed: bool = False) -> int:
        """Remove files and their rows; refuses unless confirmed (the screen asks first)."""
        if not confirmed:
            raise MeasuredDataError("deleting measured files needs explicit confirmation")
        records = [self.get(i) for i in file_ids]
        conn = connect(self.db_path)
        try:
            with conn:
                for r in records:
                    conn.execute("DELETE FROM validation_results WHERE imported_file_id = ?", (parse_id(r.file_id),))
                    conn.execute("DELETE FROM imported_files WHERE id = ?", (parse_id(r.file_id),))
        finally:
            conn.close()
        for r in records:
            if r.stored_path.exists():
                os.chmod(r.stored_path, stat.S_IREAD | stat.S_IWRITE)
                r.stored_path.unlink()
        return len(records)
