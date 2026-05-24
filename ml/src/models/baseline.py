from __future__ import annotations

import numpy as np
import pandas as pd


class RuleBaseline:
    model_name = "rule_baseline"

    def __init__(self) -> None:
        self.eda_threshold_: float = 0.0
        self.motion_threshold_: float = 0.0

    def fit(self, x: pd.DataFrame, y: np.ndarray) -> "RuleBaseline":
        calm = x[np.asarray(y) == 0]
        self.eda_threshold_ = float(calm["eda_mean"].mean() + calm["eda_mean"].std()) if "eda_mean" in x else 0.0
        self.motion_threshold_ = float(calm["acc_mag_mean"].mean() + calm["acc_mag_mean"].std()) if "acc_mag_mean" in x else 0.0
        return self

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        eda_score = _scale(x.get("eda_mean", pd.Series(0, index=x.index)).to_numpy(), self.eda_threshold_)
        motion_score = _scale(x.get("acc_mag_mean", pd.Series(0, index=x.index)).to_numpy(), self.motion_threshold_)
        stress_score = np.clip((0.7 * eda_score) + (0.3 * motion_score), 0.0, 1.0)
        return np.column_stack([1.0 - stress_score, stress_score])

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(x)[:, 1] >= 0.5).astype(int)

    def to_dict(self) -> dict:
        return {
            "modelName": self.model_name,
            "edaThreshold": self.eda_threshold_,
            "motionThreshold": self.motion_threshold_,
        }


def _scale(values: np.ndarray, threshold: float) -> np.ndarray:
    if threshold <= 0:
        return np.zeros_like(values, dtype=float)
    return np.clip(values / threshold - 0.5, 0.0, 1.0)

