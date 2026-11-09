"""Parameter sweeps: Phase 3d (FR2.12, PER-4).

A sweep runs the model at up to 200 values of one input. A point that cannot be solved, or is
outside the envelope, is kept as a failure with its reason, and the sweep carries on, so one bad
point never throws away the others.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from plasma_twin.config.loader import load_envelope
from plasma_twin.stage1.global_model import InputOutOfRange, SolverFailure, Stage1Inputs, Stage1Result, solve

SWEEPABLE = ("rf_power_w", "pressure_mbar", "ar_flow_sccm", "n2_percent_of_ar", "o2_percent_of_ar")


@dataclass(frozen=True)
class SweepPoint:
    value: float
    result: Stage1Result | None
    error: str | None = None

    @property
    def solved(self) -> bool:
        """True when the model converged at this sweep point (E4 otherwise)."""
        return self.result is not None


def sweep(base: Stage1Inputs, parameter: str, values: list[float] | np.ndarray,
          progress: Callable[[int, int], None] | None = None) -> list[SweepPoint]:
    """Solve the model at each value of `parameter`, everything else as in `base`.

    `progress(done, total)` is called after every point, so a screen can show progress at least every
    2 s (PER-4, FR17.14): the slowest single point takes about 0.2 s (Phase 14).
    """
    if parameter not in SWEEPABLE:
        raise ValueError(f"cannot sweep {parameter!r}; choose one of {SWEEPABLE}")
    limit = load_envelope()["stage1"]["options"]["sweep_max_points"]
    if not 1 <= len(values) <= limit:
        raise ValueError(f"a sweep needs 1 to {limit} points, got {len(values)}")
    points: list[SweepPoint] = []
    start_temperature = base.gas_temperature_k
    for value in values:
        try:
            inputs = replace(base, **{parameter: float(value)}, gas_temperature_k=start_temperature)
            result = solve(inputs)
            points.append(SweepPoint(float(value), result))
            start_temperature = result.inputs.gas_temperature_k  # the next point starts from here
        except (InputOutOfRange, SolverFailure, ValueError) as problem:
            points.append(SweepPoint(float(value), None, f"{type(problem).__name__}: {problem}"))
        if progress:
            progress(len(points), len(values))
    return points
