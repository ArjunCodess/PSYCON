from __future__ import annotations

import numpy as np
import pandas as pd


class RuleBaseline:
    model_name = "rule_baseline"

    def __init__(self) -> None:
        self.feature_names_: list[str] = []
        self.calm_mean_: np.ndarray = np.array([], dtype=float)
        self.calm_std_: np.ndarray = np.array([], dtype=float)
        self.threshold_: float = 0.0

    def fit(self, x: pd.DataFrame, y: np.ndarray) -> "RuleBaseline":
        self.feature_names_ = [str(col) for col in x.columns]
        calm = x[np.asarray(y) == 0]
        if calm.empty or not self.feature_names_:
            self.calm_mean_ = np.zeros(len(self.feature_names_), dtype=float)
            self.calm_std_ = np.ones(len(self.feature_names_), dtype=float)
            self.threshold_ = 1.0
            return self

        calm_values = calm[self.feature_names_].to_numpy(dtype=float)
        self.calm_mean_ = np.mean(calm_values, axis=0)
        self.calm_std_ = np.std(calm_values, axis=0)
        self.calm_std_ = np.where(self.calm_std_ < 1e-9, 1.0, self.calm_std_)

        train_scores = self._deviation_scores(x)
        calm_scores = train_scores[np.asarray(y) == 0]
        self.threshold_ = float(np.mean(calm_scores) + np.std(calm_scores)) if len(calm_scores) else 1.0
        return self

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        raw_score = self._deviation_scores(x)
        stress_score = _scale(raw_score, self.threshold_)
        return np.column_stack([1.0 - stress_score, stress_score])

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(x)[:, 1] >= 0.5).astype(int)

    def to_dict(self) -> dict:
        return {
            "modelName": self.model_name,
            "featureNames": self.feature_names_,
            "calmMean": self.calm_mean_.tolist(),
            "calmStd": self.calm_std_.tolist(),
            "threshold": self.threshold_,
        }

    def _deviation_scores(self, x: pd.DataFrame) -> np.ndarray:
        if not self.feature_names_:
            return np.zeros(len(x), dtype=float)
        values = x[self.feature_names_].to_numpy(dtype=float)
        z = np.abs((values - self.calm_mean_) / self.calm_std_)
        return np.mean(z, axis=1)


def _scale(values: np.ndarray, threshold: float) -> np.ndarray:
    if threshold <= 0:
        return np.zeros_like(values, dtype=float)
    return np.clip((values - threshold) / max(threshold, 1e-9), 0.0, 1.0)
