"""Train the Phase 10 spectrum -> plasma models on the locked Stage 1 dataset and print the results as they come.

    python scripts/train_spectrum_models.py [--algorithm random_forest|xgboost|both] [--workers 6]

The physics line-ratio fits on the held-out rows are cached in data/ai/ the first time (about 2 s per row).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.ai import datasets, inference  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithm", default="both", choices=["random_forest", "xgboost", "both"])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    frame, card = datasets.load(datasets.dataset_id(1))
    for algorithm in (inference.ALGORITHMS if args.algorithm == "both" else (args.algorithm,)):
        model_card = inference.train(algorithm, frame, card, physics_workers=args.workers)
        print(f"\n=== {model_card.model_id} ({algorithm}) ===")
        print(json.dumps(model_card.metrics, indent=1))


if __name__ == "__main__":
    main()
