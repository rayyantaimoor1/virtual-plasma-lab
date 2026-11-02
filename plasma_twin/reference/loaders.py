"""Load published reference data, after proving each file is the one that was recorded.

WHY checksums: every physics result depends on these numbers (MNT-2, CON-9). A silently edited
or half-downloaded file would give wrong physics that looks correct. Each file's SHA-256 is stored
in data/reference/manifest.json, and a loader refuses any file that does not match (event E6).

WHY some files are not in git: LXCat does not authorise third parties to redistribute its data, and
NIST Standard Reference Data is a copyrighted compilation. The repository is public, so those files
stay on each computer. The manifest records where to get them and what they must contain.

Units are stated in every field name and converted here, so the physics code never sees cm^-1.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
from scipy import constants as codata

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"
MANIFEST_PATH = REFERENCE_DIR / "manifest.json"
# E [eV] = wavenumber [cm^-1] x (h c / e). CODATA exact values, so no rounded conversion factor.
EV_PER_CM1 = codata.h * codata.c * 100.0 / codata.e


class DataStatus(Enum):
    """The states shown for each data set on the Home screen (FR1.5)."""

    OK = "ok"
    MISSING = "missing"  # the file is absent, or has never been registered
    CORRUPT = "corrupt"  # the file exists, but its checksum differs from the manifest


class ReferenceDataError(RuntimeError):
    """A data set cannot be used. Features depending on it must be disabled (E6, FR17.6)."""

    def __init__(self, dataset_id: str, status: DataStatus, detail: str) -> None:
        super().__init__(f"Reference data '{dataset_id}' is {status.value}: {detail}")
        self.dataset_id = dataset_id
        self.status = status


@dataclass(frozen=True)
class AtomicLines:
    """Spectral lines of one species from the NIST Atomic Spectra Database, sorted by wavelength."""

    species: str
    wavelength_nm: np.ndarray  # in air; the observed value, or the Ritz value if none was observed
    a_ki_per_s: np.ndarray  # Einstein coefficient: how fast the upper level emits this line
    lower_energy_ev: np.ndarray
    upper_energy_ev: np.ndarray
    g_lower: np.ndarray  # statistical weights
    g_upper: np.ndarray
    accuracy: tuple[str, ...]  # NIST's letter grade for each A value
    upper_term: tuple[str, ...]


@dataclass(frozen=True)
class CrossSection:
    """One electron collision process from an LXCat file: sigma(energy)."""

    process_type: str  # ELASTIC, EFFECTIVE, EXCITATION, IONIZATION or ATTACHMENT
    target: str
    product: str  # empty for elastic and effective processes
    threshold_ev: float  # energy needed to cause the process; 0 for elastic
    energy_ev: np.ndarray
    sigma_m2: np.ndarray
    description: str  # the PROCESS line, kept so a result can name its exact source
    # The block's COMMENT lines. Kept because some change how sigma must be used: in the Biagi O2
    # file, three-body attachment is "normalized to gas density", so it is not a plain area in m2.
    comments: tuple[str, ...] = ()


# -------------------------------------------------------------------------- manifest and checksums
def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    """Return the manifest as {dataset id: entry}."""
    return {entry["id"]: entry for entry in json.loads(path.read_text(encoding="utf-8"))["datasets"]}


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file's exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataset_status(entry: dict[str, Any], base: Path = REFERENCE_DIR) -> DataStatus:
    """Classify one manifest entry without loading it."""
    path = base / entry["path"]
    if not path.is_file() or not entry.get("sha256"):
        return DataStatus.MISSING
    return DataStatus.OK if sha256_of(path) == entry["sha256"] else DataStatus.CORRUPT


def check_reference_data(manifest_path: Path = MANIFEST_PATH) -> dict[str, DataStatus]:
    """Return every data set's status, for the start-up check (E1) and the Home screen."""
    return {name: dataset_status(entry, manifest_path.parent) for name, entry in load_manifest(manifest_path).items()}


def verified_path(dataset_id: str, manifest_path: Path = MANIFEST_PATH) -> Path:
    """Return a data file's path, or raise if it cannot be trusted.

    There is deliberately no fallback to built-in numbers (FR17.6): a guessed cross-section would
    produce a plausible plasma that nobody could trace to a source.
    """
    entry = load_manifest(manifest_path)[dataset_id]
    status = dataset_status(entry, manifest_path.parent)
    if status is not DataStatus.OK:
        raise ReferenceDataError(dataset_id, status, entry.get("how_to_get", "see data/reference/README.md"))
    return manifest_path.parent / entry["path"]


# -------------------------------------------------------------------------- NIST atomic lines
def _clean_nist(cell: str) -> str:
    """Remove NIST's spreadsheet wrapper: a value arrives as ="696.5431", or with ? or * marks."""
    cell = cell.strip()
    if cell.startswith('="') and cell.endswith('"'):
        cell = cell[2:-1]
    return cell.strip()


def _nist_number(cell: str) -> float:
    """Read a NIST number, ignoring its uncertainty marks. Returns NaN when the cell is empty."""
    match = re.search(r"-?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?", _clean_nist(cell))
    return float(match.group()) if match else float("nan")


def read_nist_lines(path: Path, species: str) -> AtomicLines:
    """Parse a NIST ASD CSV file. Lines without an A value are dropped, as they cannot be modelled."""
    rows: list[tuple[Any, ...]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            a_value = _nist_number(row["Aki(s^-1)"])
            observed = _nist_number(row["obs_wl_air(nm)"])
            wavelength = observed if np.isfinite(observed) else _nist_number(row["ritz_wl_air(nm)"])
            lower, upper = _nist_number(row["Ei(cm-1)"]), _nist_number(row["Ek(cm-1)"])
            g_lower, g_upper = _nist_number(row["g_i"]), _nist_number(row["g_k"])
            values = (a_value, wavelength, lower, upper, g_lower, g_upper)
            if all(np.isfinite(v) for v in values):
                rows.append((wavelength, a_value, lower, upper, g_lower, g_upper,
                             _clean_nist(row["Acc"]), _clean_nist(row["term_k"])))
    rows.sort(key=lambda r: r[0])
    columns = list(zip(*rows)) if rows else [()] * 8
    return AtomicLines(
        species=species,
        wavelength_nm=np.array(columns[0], dtype=float),
        a_ki_per_s=np.array(columns[1], dtype=float),
        lower_energy_ev=np.array(columns[2], dtype=float) * EV_PER_CM1,
        upper_energy_ev=np.array(columns[3], dtype=float) * EV_PER_CM1,
        g_lower=np.array(columns[4], dtype=float),
        g_upper=np.array(columns[5], dtype=float),
        accuracy=tuple(columns[6]),
        upper_term=tuple(columns[7]),
    )


def load_atomic_lines(species: str, manifest_path: Path = MANIFEST_PATH) -> AtomicLines:
    """Load verified lines. `species` is 'Ar I', 'O I' or 'H I'."""
    dataset_id = "nist_" + species.lower().replace(" ", "_")
    return read_nist_lines(verified_path(dataset_id, manifest_path), species)


# -------------------------------------------------------------------------- LXCat cross-sections
_LXCAT_PROCESSES = {"ELASTIC", "EFFECTIVE", "EXCITATION", "IONIZATION", "ATTACHMENT", "ROTATIONAL"}


def read_lxcat(path: Path) -> list[CrossSection]:
    """Parse an LXCat cross-section file.

    Each block is: a process keyword, a target line (`Ar` or `Ar -> Ar^+`), a threshold line
    (missing for attachment), labelled lines such as PROCESS: and COMMENT:, then a table of energy
    (eV) and sigma (m2) between two dashed lines. Checked against a real Biagi download (Nov 2026).
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    sections: list[CrossSection] = []
    i = 0
    while i < len(lines):
        keyword = lines[i].strip()
        if keyword not in _LXCAT_PROCESSES:
            i += 1
            continue
        parts = lines[i + 1].replace("<->", "->").split("->")
        target, product = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        i += 2
        threshold, description, comments = 0.0, "", []
        while i < len(lines) and not lines[i].lstrip().startswith("-----"):
            text = lines[i].strip()
            if text.startswith("PROCESS:"):
                description = text.removeprefix("PROCESS:").strip()
            elif text.startswith("COMMENT:"):
                comments.append(text.removeprefix("COMMENT:").strip())
            elif keyword != "EFFECTIVE" and keyword != "ELASTIC" and threshold == 0.0 and not re.match(r"^[A-Z. ]+:", text):
                # In excitation and ionization blocks this first bare number is the threshold. In
                # elastic and effective blocks the bare number is a mass ratio, so it is skipped.
                match = re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
                threshold = float(match.group()) if match else 0.0
            i += 1
        i += 1  # opening dashed line
        table: list[tuple[float, float]] = []
        while i < len(lines) and not lines[i].lstrip().startswith("-----"):
            columns = lines[i].split()
            table.append((float(columns[0]), float(columns[1])))
            i += 1
        i += 1  # closing dashed line
        data = np.array(table, dtype=float).reshape(-1, 2)
        sections.append(CrossSection(keyword, target, product, threshold, data[:, 0], data[:, 1],
                                     description, tuple(comments)))
    return sections


def load_cross_sections(target: str, manifest_path: Path = MANIFEST_PATH) -> list[CrossSection]:
    """Load verified cross-sections for one gas: 'Ar', 'N2' or 'O2'."""
    sections = read_lxcat(verified_path("lxcat_cross_sections", manifest_path))
    return [s for s in sections if s.target == target]


# -------------------------------------------------------------------------- constants and benchmarks
def _read_csv(dataset_id: str, manifest_path: Path) -> list[dict[str, str]]:
    path = verified_path(dataset_id, manifest_path)
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


def load_diatomic_constants(molecule: str, state: str, manifest_path: Path = MANIFEST_PATH) -> dict[str, float]:
    """Return the spectroscopic constants of one molecular state, in cm^-1 (bond length in angstrom)."""
    for row in _read_csv("diatomic_constants", manifest_path):
        if row["molecule"] == molecule and row["state"] == state:
            return {k: float(v) for k, v in row.items() if k not in ("molecule", "state", "source")}
    raise KeyError(f"No constants for {molecule} {state}")


def load_benchmarks(manifest_path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    """Return the published validation values (ACC-1). Each row must carry its own citation."""
    return _read_csv("benchmarks", manifest_path)
