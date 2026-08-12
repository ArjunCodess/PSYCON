from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InferenceDecision:
    state: str
    score: float | None
    confidence: float | None
    model_name: str
    model_version: str
    reasons: tuple[str, ...] = ()


class InferenceEngine:
    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact
        self.feature_names = tuple(artifact["featureNames"])
        self.model_name = str(artifact["modelName"])
        self.model_version = str(artifact["modelVersion"])

    @classmethod
    def from_path(cls, path: str | Path) -> "InferenceEngine":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def evaluate(self, features: dict[str, float]) -> InferenceDecision:
        missing = [name for name in self.feature_names if name not in features]
        invalid = [name for name in self.feature_names if name in features and not math.isfinite(float(features[name]))]
        if missing or invalid:
            reasons = []
            if missing:
                reasons.append("missing_model_features:" + ",".join(missing))
            if invalid:
                reasons.append("nonfinite_model_features:" + ",".join(invalid))
            return InferenceDecision("abstained", None, None, self.model_name, self.model_version, tuple(reasons))
        scaler = self.artifact["scaler"]
        model = self.artifact["logisticRegression"]
        standardized = [
            (float(features[name]) - float(mean)) / float(scale)
            for name, mean, scale in zip(self.feature_names, scaler["mean"], scaler["scale"], strict=True)
        ]
        logit = float(model["intercept"]) + sum(float(weight) * value for weight, value in zip(model["coefficients"], standardized, strict=True))
        score = 1.0 / (1.0 + math.exp(-max(-700.0, min(700.0, logit))))
        state = "unknown"
        for candidate, limits in self.artifact["scoreThresholds"].items():
            low, high = map(float, limits)
            if low <= score <= high and (score < high or high == 1.0):
                state = candidate
                break
        return InferenceDecision(state, score, max(score, 1.0 - score), self.model_name, self.model_version)
