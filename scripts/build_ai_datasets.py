"""Build the locked AI datasets (Phase 9) into data/ai/.

  python scripts/build_ai_datasets.py            both stages, all cores but two
  python scripts/build_ai_datasets.py --stage 1  one stage only

The settings and seeds come from plasma_twin/config/ai_datasets.toml (locked 2026-11-04); the same
settings always give the same rows, so the files are not kept in git.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.ai import datasets  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", type=int, choices=(1, 2))
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()
    for stage in ([args.stage] if args.stage else [1, 2]):
        start = time.perf_counter()

        def progress(done: int, total: int) -> None:
            if done % 50 == 0 or done == total:
                print(f"stage {stage}: {done}/{total} rows, {time.perf_counter() - start:.0f} s", flush=True)

        frame, card = datasets.build(stage, workers=args.workers, progress=progress)
        path = datasets.save(frame, card)
        print(f"saved {path.name}: {card.rows} rows, faults {card.rows_per_fault}, {time.perf_counter() - start:.0f} s", flush=True)


if __name__ == "__main__":
    main()
