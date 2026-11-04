"""Registry, model cards, baselines and the training framework (Phase 9, FR16.2-FR16.5, AIQ-6, E22)."""
import json
from dataclasses import asdict

import numpy as np
import pytest

from plasma_twin import TWIN_VERSION
from plasma_twin.ai.registry import ModelUnavailable, Registry, make_card
from plasma_twin.ai.training import RangeCheck, detection_metrics, paired_bootstrap_p, regression_metrics


@pytest.fixture
def registry(tmp_path):
    return Registry(tmp_path / "models", tmp_path / "mlruns")


def test_a_model_is_logged_and_loaded_when_current(registry) -> None:
    card = registry.register(make_card("m-1", "task", "ridge", "S1-x", 1, {"a": 1}, ["f"], ["t"],
                                       {"random": {"model": {"r2": 0.9}, "baseline": {"r2": 0.5}, "p_value": 0.01}}), {"weights": [1, 2]})
    assert card.mlflow_run_id and registry.status(card) == "current"
    model, loaded = registry.load("m-1")
    assert model == {"weights": [1, 2]} and loaded.twin_version == TWIN_VERSION
    runs = registry.runs()
    assert runs["tags.model_id"].tolist() == ["m-1"] and runs["metrics.random.p_value"].tolist() == [0.01]


def test_a_model_stamped_with_an_old_twin_version_is_out_of_date(registry) -> None:
    """E22, AIQ-6: listed, never used."""
    registry.register(make_card("m-old", "task", "ridge", "S1-x", 1, {}, [], [], {}), object())
    path = registry.models_dir / "m-old" / "card.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "twin_version": "0.9"}), encoding="utf-8")
    card = next(c for c in registry.cards() if c.model_id == "m-old")
    assert card.out_of_date and registry.status(card) == "out of date"
    with pytest.raises(ModelUnavailable, match="out of date"):
        registry.load("m-old")


def test_a_missing_model_is_refused(registry) -> None:
    with pytest.raises(ModelUnavailable, match="missing"):
        registry.load("nothing")


def test_paired_bootstrap_separates_a_better_model_from_an_equal_one() -> None:
    rng = np.random.default_rng(0)
    baseline = np.abs(rng.normal(0, 1.0, 200))
    assert paired_bootstrap_p(baseline * 0.5, baseline) < 0.01
    assert paired_bootstrap_p(baseline, baseline) == 1.0


def test_metrics_and_range_check() -> None:
    truth = np.array([1.0, 2.0, 3.0, 4.0])
    assert regression_metrics(truth, truth)["r2"] == 1.0
    assert regression_metrics(truth, truth * 1.1)["median_relative_error"] == pytest.approx(0.1)
    check = RangeCheck().fit(np.array([[0.0, 0.0], [1.0, 1.0]]))
    assert check.flag(np.array([[0.5, 0.5], [1.5, 0.5]])).tolist() == [False, True]
    assert detection_metrics(np.array([1, 1, 0, 0]), np.array([True, False, False, True])) == {"recall": 0.5, "false_alarm_rate": 0.5}


def test_training_on_a_small_dataset_reports_both_splits_and_the_baseline(registry) -> None:
    from plasma_twin.reference.loaders import DataStatus, check_reference_data
    if any(s is not DataStatus.OK for s in check_reference_data().values()):
        pytest.skip("the LXCat and NIST files have not been downloaded here")
    from plasma_twin.ai import datasets
    from plasma_twin.ai.training import train
    frame, card = datasets.build(1, runs=60, workers=6)
    model_card = train("spectrum_to_te_ne", "xgboost", frame, card, registry)
    assert set(model_card.metrics) == {"random", "region"}
    for split in ("random", "region"):
        result = model_card.metrics[split]
        assert {"te_mae", "ne_median_relative_error", "te_r2"} <= set(result["model"]) and result["baseline"]
        assert 0 < result["p_value"] <= 1
    assert model_card.dataset_id == card.dataset_id and registry.status(model_card) == "current"
    assert json.loads(json.dumps(asdict(model_card)))  # the card is plain JSON
