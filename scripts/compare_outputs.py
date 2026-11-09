"""Bit-identical check for refactors that must not change the model (Phase 15 rules).

    python scripts/compare_outputs.py save    FILE   # before the change
    python scripts/compare_outputs.py compare FILE   # after: the largest relative difference must be exactly 0

It records every numeric output of the 100 Stage 1 configurations of the PER-1 draw (all mixtures, both
EEDFs, 0D) and the N2 second-positive line positions (which use the air-dispersion formula).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def outputs() -> dict[str, float]:
    import numpy as np

    from measure_phase14 import _numbers, stage1_draws
    from plasma_twin.oes.n2_band import vacuum_to_air_nm
    from plasma_twin.services import stage1
    values: dict[str, float] = {}
    for k, config in enumerate(stage1_draws(100)):
        values.update({f"run{k}{key}": v for key, v in _numbers(stage1.run(config).as_dict()).items()})
    for k, x in enumerate(vacuum_to_air_nm(np.linspace(25000.0, 35000.0, 501))):
        values[f"n2_air_nm[{k}]"] = float(x)
    return values


def main() -> None:
    action, file = sys.argv[1], Path(sys.argv[2])
    now = outputs()
    if action == "save":
        file.write_text(json.dumps(now), encoding="utf-8")
        print(f"saved {len(now)} numbers")
        return
    before = json.loads(file.read_text(encoding="utf-8"))
    missing = sorted(set(before) ^ set(now))
    worst, where = 0.0, None
    for key, x in before.items():
        y = now.get(key)
        if y is None or x == y:
            continue
        difference = abs(x - y) / max(abs(x), abs(y))
        if difference > worst:
            worst, where = difference, key
    print(json.dumps({"numbers": len(before), "keys_differing_in_name": missing[:10], "largest_relative_difference": worst,
                      "where": where, "identical": worst == 0.0 and not missing}, indent=1))


if __name__ == "__main__":
    main()
