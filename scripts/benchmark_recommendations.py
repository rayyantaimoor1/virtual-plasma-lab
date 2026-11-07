"""Run the Phase 13 benchmark: 30 reachable goals through the recommender, each verified by the twin (AIQ-4).

    python scripts/benchmark_recommendations.py

Uses the current XGBoost surrogates (Phase 11). Saves data/ai/recommend-benchmark.json (gitignored), which M14 shows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.ai import recommend  # noqa: E402


def main() -> None:
    models = {stage: recommend.load_surrogate(stage) for stage in (1, 2)}
    result = recommend.run_benchmark(models, progress=print)
    recommend.save_benchmark(result)
    for row in result["rows"]:
        print(json.dumps(row, default=float))
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
