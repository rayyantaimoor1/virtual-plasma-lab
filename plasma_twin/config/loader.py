"""Read and check the operating envelope (envelope.toml).

WHY a loader instead of constants in the code: SRS USE-3 and CON-7 need the screens, the validator
and the validation service to share one set of ranges and one tolerance. If each kept its own copy,
a screen could offer a value that the physics later rejects, or a comparison could use a different
tolerance from the one stated in the SRS.
"""
from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

ENVELOPE_PATH = Path(__file__).resolve().parent / "envelope.toml"
RANGE_KEYS = {"min", "default", "max"}


def load_envelope(path: Path = ENVELOPE_PATH) -> dict[str, Any]:
    """Return the envelope as nested dictionaries, after checking that it makes sense.

    A broken range is reported here, at start-up, because a wrong limit found later would look
    like a physics failure and be much harder to trace.
    """
    with open(path, "rb") as handle:  # tomllib requires binary mode
        envelope = tomllib.load(handle)
    problems = find_range_problems(envelope)
    if problems:
        raise ValueError(f"Invalid envelope {path}: " + "; ".join(problems))
    return envelope


def iter_ranges(table: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Yield (dotted name, range table) for every table holding `min` or `max`."""
    for key, value in table.items():
        if not isinstance(value, Mapping):
            continue
        name = f"{prefix}.{key}" if prefix else key
        if value.keys() & {"min", "max"}:
            yield name, value
        else:
            yield from iter_ranges(value, name)


def find_range_problems(envelope: Mapping[str, Any]) -> list[str]:
    """List every range that is incomplete or out of order.

    The rule is min < max and min <= default <= max. The default may equal a limit because the
    supervisor's values do: 10 kV is both the default and the maximum pulse voltage (FR8.2).
    """
    problems: list[str] = []
    for name, rng in iter_ranges(envelope):
        missing = RANGE_KEYS - rng.keys()
        if missing:
            problems.append(f"{name} is missing {sorted(missing)}")
            continue
        if not rng["min"] < rng["max"]:
            problems.append(f"{name}: min must be below max")
        if not rng["min"] <= rng["default"] <= rng["max"]:
            problems.append(f"{name}: default {rng['default']} is outside {rng['min']}-{rng['max']}")
    return problems
