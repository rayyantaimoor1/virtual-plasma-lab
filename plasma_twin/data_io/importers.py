"""Reading measured OES spectra (.txt) and Langmuir probe I-V curves (.csv): Phase 8 (FR10.1-FR10.3, E13, E14).

RULES (BUILD_STEPS.md, Phase 8, fixed before this code):
- A file is data, never code (SEC-2). OES must be .txt and probe .csv (the supervisor's formats).
  Rejected, with the exact reason and nothing stored (E14): over 50 MB; a NUL byte (binary); fewer
  than two numeric columns; fewer than 10 data rows; a non-numeric or empty cell after the header
  (the line number is given); an OES wavelength column that is not increasing.
- Leading lines that are not all numbers are the file's header. The delimiter (tab, comma,
  semicolon or spaces) is detected from the first data line, then the whole file is read with
  pandas' C parser (PER-7: 50 MB in at most 15 s).
- Units: OES wavelength in nm, intensity in arbitrary units. Probe voltage in V; current in A, mA or
  uA, converted to A.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import numpy as np
import pandas as pd

from plasma_twin.config.loader import load_envelope

EXTENSIONS = {"oes": ".txt", "probe": ".csv"}
CURRENT_UNITS = {"A": 1.0, "mA": 1e-3, "µA": 1e-6}
MIN_ROWS = 10
DELIMITERS = {"\t": "tab", ",": "comma", ";": "semicolon", None: "spaces"}


class FileRejected(ValueError):
    """The file cannot be imported; the message is the exact reason (E14)."""


@dataclass(frozen=True)
class ParsedFile:
    name: str
    diagnostic: str  # "oes" or "probe"
    header: tuple[str, ...]  # the leading non-numeric lines, kept as they were
    delimiter: str  # its name: tab, comma, semicolon or spaces
    columns: tuple[np.ndarray, ...]
    sha256: str
    size_bytes: int

    @property
    def rows(self) -> int:
        """The number of data rows read."""
        return len(self.columns[0])


def _numbers(fields: list[str]) -> bool:
    try:
        [float(f) for f in fields]
    except ValueError:
        return False
    return len(fields) >= 2


def _split(line: str, delimiter: str | None) -> list[str]:
    parts = line.split(delimiter) if delimiter else line.split()
    while parts and not parts[-1].strip():  # a trailing delimiter makes an empty last field
        parts.pop()
    return [p.strip() for p in parts]


def parse(name: str, raw: bytes, diagnostic: str) -> ParsedFile:
    """Check and read one uploaded file. Raises FileRejected with the exact reason."""
    if diagnostic not in EXTENSIONS:
        raise FileRejected(f"unknown diagnostic {diagnostic!r}")
    extension = EXTENSIONS[diagnostic]
    if not name.lower().endswith(extension):
        raise FileRejected(f"a {'spectrum' if diagnostic == 'oes' else 'probe I-V curve'} must be a {extension} file, "
                           f"not '{name}'")
    limit_mb = load_envelope()["data"]["import_max_file_mb"]
    if len(raw) > limit_mb * 1024 * 1024:
        raise FileRejected(f"the file is {len(raw) / 1024 / 1024:.1f} MB; the limit is {limit_mb} MB")
    if b"\x00" in raw:
        raise FileRejected("the file contains binary data (a NUL byte); only text files can be imported")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # every byte is valid Latin-1, and NUL bytes were refused above
    lines = text.splitlines()

    # the header: leading lines that are not all numbers under any delimiter
    start = None
    for i, line in enumerate(lines):
        if line.strip() and any(_numbers(_split(line, d)) for d in DELIMITERS):
            start = i
            break
    if start is None:
        raise FileRejected("no line with two or more numbers was found")
    # the delimiter: the first one (tab, comma, semicolon, spaces) that splits the first data line into numbers
    delimiter = next(d for d in DELIMITERS if _numbers(_split(lines[start], d)))
    width = len(_split(lines[start], delimiter))
    sep = delimiter if delimiter else r"\s+"
    try:  # fast path: every cell is a number
        numeric = pd.read_csv(io.StringIO(text), sep=sep, header=None, skiprows=start, engine="c", skip_blank_lines=True,
                              dtype=float, usecols=range(width))
        if numeric.isna().to_numpy().any():
            raise ValueError("empty cell")
    except (ValueError, pd.errors.ParserError):
        numeric = _locate_problem(text, sep, start, width)
    if numeric.shape[1] < 2:
        raise FileRejected("fewer than two numeric columns")
    if len(numeric) < MIN_ROWS:
        raise FileRejected(f"only {len(numeric)} data rows; at least {MIN_ROWS} are needed")
    columns = tuple(numeric[c].to_numpy(dtype=float) for c in numeric.columns)
    return ParsedFile(name, diagnostic, tuple(lines[:start]), DELIMITERS[delimiter], columns,
                      hashlib.sha256(raw).hexdigest(), len(raw))


def mapped(parsed: ParsedFile, x_column: int, y_column: int, current_unit: str = "A") -> tuple[np.ndarray, np.ndarray]:
    """FR10.3: the two chosen columns in SI-style units (OES: nm and a.u.; probe: V and A)."""
    if x_column == y_column:
        raise FileRejected("choose two different columns")
    x, y = parsed.columns[x_column], parsed.columns[y_column]
    if parsed.diagnostic == "oes":
        if not np.all(np.diff(x) > 0):
            raise FileRejected(f"column {x_column + 1} is not an increasing wavelength")
        return x, y
    if current_unit not in CURRENT_UNITS:
        raise FileRejected(f"current unit must be one of {', '.join(CURRENT_UNITS)}")
    return x, y * CURRENT_UNITS[current_unit]


def _locate_problem(text: str, sep: str, start: int, width: int) -> pd.DataFrame:
    """Slow path, only when the fast read failed: find the first bad cell and raise with its line number."""
    try:
        table = pd.read_csv(io.StringIO(text), sep=sep, header=None, skiprows=start, engine="c", skip_blank_lines=False,
                            dtype=str, keep_default_na=False, na_filter=False)
    except pd.errors.ParserError as problem:
        raise FileRejected(f"the rows do not all have the same number of columns ({problem})") from problem
    table = table.iloc[:, :width]
    blank = (table.apply(lambda col: col.str.strip()) == "").all(axis=1)
    numeric = table.apply(lambda col: pd.to_numeric(col.str.strip(), errors="coerce"))
    bad = numeric.isna().to_numpy() & ~blank.to_numpy()[:, None]
    if bad.any():
        row, col = np.argwhere(bad)[0]
        value = table.iat[row, col].strip()
        raise FileRejected(f"line {start + 1 + row}, column {col + 1}: "
                           + ("empty cell" if not value else f"'{value[:20]}' is not a number"))
    return numeric[~blank.to_numpy()]
