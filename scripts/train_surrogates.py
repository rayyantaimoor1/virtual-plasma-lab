"""Train the Phase 11 surrogates of the twin (both stages, both algorithms) and print the results as they come.

    python scripts/train_surrogates.py [--stage 1|2|both] [--algorithm xgboost|random_forest|both] [--workers 6]

The first Stage 1 run re-runs the twin noise-free at the locked plan's 1,200 inputs (a few minutes, cached in data/ai/).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.ai import surrogate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="both", choices=["1", "2", "both"])
    parser.add_argument("--algorithm", default="both", choices=["xgboost", "random_forest", "both"])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    for stage in ((1, 2) if args.stage == "both" else (int(args.stage),)):
        table = surrogate.training_table(stage, args.workers)
        for algorithm in (surrogate.ALGORITHMS if args.algorithm == "both" else (args.algorithm,)):
            card = surrogate.train(stage, algorithm, table=table)
            print(f"\n=== {card.model_id} ({algorithm}) ===")
            print(json.dumps(card.metrics, indent=1))


if __name__ == "__main__":
    main()
