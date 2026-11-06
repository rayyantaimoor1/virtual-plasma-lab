"""Train the Phase 12 residual anomaly detector on the locked Stage 1 dataset and print the results as they come.

    python scripts/train_anomaly.py [--workers 6]

The first run computes the twin's noise-free expectation at all 1,200 recorded inputs (a few minutes, cached in data/ai/).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plasma_twin.ai import anomaly, datasets  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    frame, card = datasets.load(datasets.dataset_id(1))
    model_card = anomaly.train(frame, card, workers=args.workers)
    print(f"=== {model_card.model_id} ===")
    print(json.dumps(model_card.metrics, indent=1))


if __name__ == "__main__":
    main()
