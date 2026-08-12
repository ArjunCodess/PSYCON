from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.inference import InferenceEngine


ROOT = Path(__file__).resolve().parents[2]


def engine() -> InferenceEngine:
    return InferenceEngine.from_path(ROOT / "results" / "app_model.json")


def test_inference_abstains_and_names_every_missing_feature() -> None:
    decision = engine().evaluate({"eda_mean": 1.0})
    assert decision.state == "abstained"
    assert decision.score is None
    assert decision.reasons[0].startswith("missing_model_features:")
    assert "bvp_mean" in decision.reasons[0]


def test_inference_scores_complete_finite_model_vector() -> None:
    artifact = json.loads((ROOT / "results" / "app_model.json").read_text(encoding="utf-8"))
    features = dict(zip(artifact["featureNames"], artifact["scaler"]["mean"], strict=True))
    decision = engine().evaluate(features)
    expected = 1 / (1 + __import__("math").exp(-artifact["logisticRegression"]["intercept"]))
    assert decision.state in {"calm", "mild_stress", "high_stress"}
    assert decision.score == pytest.approx(expected)
    assert decision.confidence is not None and 0.5 <= decision.confidence <= 1.0


def test_inference_abstains_for_nonfinite_input() -> None:
    artifact = json.loads((ROOT / "results" / "app_model.json").read_text(encoding="utf-8"))
    features = dict(zip(artifact["featureNames"], artifact["scaler"]["mean"], strict=True))
    features[artifact["featureNames"][0]] = float("nan")
    decision = engine().evaluate(features)
    assert decision.state == "abstained"
    assert decision.reasons[0].startswith("nonfinite_model_features:")
