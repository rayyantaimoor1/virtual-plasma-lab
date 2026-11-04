"""Model registry, model cards and run logging: Phase 9 (FR16.4, FR16.5, AIQ-5, AIQ-6, E22).

RULES (BUILD_STEPS.md, Phase 9): every training run is logged with MLflow in the local folder store
mlruns/ (mlflow-skinny; the folder store is opted into with MLFLOW_ALLOW_FILE_STORE, see the rules).
Each fitted model is saved under models/<model_id>/ with a JSON model card. Every model is stamped with
the twin version; a model stamped with another version is "out of date": listed, never used (E22).
"""
from __future__ import annotations

import json
import os
import pickle
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from plasma_twin import TWIN_VERSION, __version__

os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "models"
MLRUNS_DIR = ROOT / "mlruns"
EXPERIMENT = "plasma-digital-twin"


class ModelUnavailable(RuntimeError):
    """The model is missing or out of date (E22); no AI result may come from it (AIQ-6)."""


@dataclass(frozen=True)
class ModelCard:
    model_id: str
    task: str
    algorithm: str
    dataset_id: str
    twin_version: str
    software_version: str
    seed: int
    hyperparameters: dict[str, Any]
    features: list[str]
    targets: list[str]
    metrics: dict[str, Any]  # {split: {"model": {...}, "baseline": {...}, "p_value": ...}}
    created_at: str
    mlflow_run_id: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def out_of_date(self) -> bool:
        return self.twin_version != TWIN_VERSION


class Registry:
    def __init__(self, models_dir: Path | None = None, mlruns_dir: Path | None = None) -> None:
        # PLASMA_TWIN_MODELS moves both folders (screen tests), as PLASMA_TWIN_DB moves the database
        moved = os.environ.get("PLASMA_TWIN_MODELS")
        self.models_dir = models_dir or (Path(moved) if moved else MODELS_DIR)
        self.mlruns_dir = mlruns_dir or (self.models_dir.parent / "mlruns" if moved else MLRUNS_DIR)

    def _mlflow(self):
        import mlflow
        mlflow.set_tracking_uri(self.mlruns_dir.resolve().as_uri())
        mlflow.set_experiment(EXPERIMENT)
        return mlflow

    def register(self, card: ModelCard, model: Any, predictions: dict[str, Any] | None = None) -> ModelCard:
        """Log the run with MLflow, then save the model, its card and its held-out predictions (FR16.3)."""
        mlflow = self._mlflow()
        with mlflow.start_run(run_name=card.model_id) as run:
            mlflow.set_tags({"model_id": card.model_id, "task": card.task, "algorithm": card.algorithm, "dataset_id": card.dataset_id,
                             "twin_version": card.twin_version, "software_version": card.software_version})
            mlflow.log_params({"seed": card.seed, **{f"hp.{k}": v for k, v in card.hyperparameters.items()}})
            for split, result in card.metrics.items():
                for key, value in result.items():
                    if isinstance(value, dict):  # model, baseline, physics
                        for name, number in value.items():
                            if isinstance(number, (int, float)) and not isinstance(number, bool) and number == number:
                                mlflow.log_metric(f"{split}.{key}.{name}", float(number))
                    elif isinstance(value, (int, float)) and not isinstance(value, bool) and value == value:
                        mlflow.log_metric(f"{split}.{key}", float(value))  # p-values, intervals, row counts
        card = ModelCard(**{**asdict(card), "mlflow_run_id": run.info.run_id})
        folder = self.models_dir / card.model_id
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "model.pkl", "wb") as handle:
            pickle.dump(model, handle)  # our own model, written and read only on this computer
        (folder / "card.json").write_text(json.dumps(asdict(card), indent=2), encoding="utf-8")
        if predictions is not None:
            (folder / "predictions.json").write_text(json.dumps(predictions), encoding="utf-8")
        return card

    def predictions(self, model_id: str) -> dict[str, Any]:
        """Held-out predictions of the model and its baseline on each split, for the evaluation plot."""
        path = self.models_dir / model_id / "predictions.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def cards(self) -> list[ModelCard]:
        if not self.models_dir.exists():
            return []
        out = []
        for path in sorted(self.models_dir.glob("*/card.json")):
            out.append(ModelCard(**json.loads(path.read_text(encoding="utf-8"))))
        return sorted(out, key=lambda c: c.created_at, reverse=True)

    def status(self, card: ModelCard) -> str:
        if not (self.models_dir / card.model_id / "model.pkl").exists():
            return "missing"
        return "out of date" if card.out_of_date else "current"

    def load(self, model_id: str) -> tuple[Any, ModelCard]:
        """The model and its card, or ModelUnavailable if it is missing or out of date (E22, AIQ-6)."""
        path = self.models_dir / model_id / "card.json"
        if not path.exists():
            raise ModelUnavailable(f"model {model_id} is missing")
        card = ModelCard(**json.loads(path.read_text(encoding="utf-8")))
        status = self.status(card)
        if status != "current":
            raise ModelUnavailable(f"model {model_id} is {status}: trained on twin version {card.twin_version}, "
                                   f"the twin is {TWIN_VERSION}; retrain it (E22)")
        with open(self.models_dir / model_id / "model.pkl", "rb") as handle:
            return pickle.load(handle), card

    def runs(self):
        """Every logged training run, newest first (FR16.5)."""
        mlflow = self._mlflow()
        return mlflow.search_runs(experiment_names=[EXPERIMENT], order_by=["attributes.start_time DESC"])


def new_model_id(task: str) -> str:
    return f"{task}-{datetime.now():%Y%m%d-%H%M%S-%f}"


def make_card(model_id: str, task: str, algorithm: str, dataset_id: str, seed: int, hyperparameters: dict[str, Any],
              features: list[str], targets: list[str], metrics: dict[str, Any], notes: list[str] | None = None) -> ModelCard:
    return ModelCard(model_id, task, algorithm, dataset_id, TWIN_VERSION, __version__, seed, hyperparameters, features, targets,
                     metrics, datetime.now().isoformat(timespec="seconds"), "", notes or [])
