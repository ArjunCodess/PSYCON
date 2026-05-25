from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import CHARTS_DIR, RESULTS_DIR, STATE_THRESHOLDS
from ..config import COMMON_HZ, HOP_SECONDS, WINDOW_SECONDS
from ..features import feature_columns, modality_columns
from .baseline import RuleBaseline


@dataclass
class ModelResult:
    name: str
    modality: str
    accuracy: float
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    actual_stress: int
    predicted_stress: int
    confusion_matrix: list[list[int]]


def train_all(features: pd.DataFrame, results_dir: Path = RESULTS_DIR, charts_dir: Path = CHARTS_DIR) -> dict[str, Any]:
    import matplotlib.pyplot as plt
    import seaborn as sns

    results_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    groups = features["subject"].to_numpy()
    y = features["label_binary"].to_numpy(dtype=int)
    unique_groups = np.unique(groups)
    if len(unique_groups) >= 2:
        split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
        train_idx, test_idx = next(split.split(features, y, groups))
    else:
        indices = np.arange(len(features))
        train_idx, test_idx = train_test_split(indices, test_size=0.25, random_state=42, stratify=y)

    all_results: list[ModelResult] = []
    trained_multimodal: Pipeline | None = None
    trained_feature_names: list[str] = []
    modalities = modality_columns(features.columns)

    for modality, cols in modalities.items():
        if not cols:
            continue
        x_train = features.iloc[train_idx][cols]
        x_test = features.iloc[test_idx][cols]
        y_train = y[train_idx]
        y_test = y[test_idx]

        baseline = RuleBaseline().fit(x_train, y_train)
        all_results.append(_evaluate("rule_baseline", modality, baseline, x_test, y_test))

        logistic = Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
        ])
        logistic.fit(x_train, y_train)
        all_results.append(_evaluate("logistic_regression", modality, logistic, x_test, y_test))

        forest = RandomForestClassifier(n_estimators=160, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1)
        forest.fit(x_train, y_train)
        all_results.append(_evaluate("random_forest", modality, forest, x_test, y_test))

        xgb_result = _try_train_xgboost(x_train, y_train, x_test, y_test, modality)
        if xgb_result is not None:
            all_results.append(xgb_result)

        lightgbm_result = _try_train_lightgbm(x_train, y_train, x_test, y_test, modality)
        if lightgbm_result is not None:
            all_results.append(lightgbm_result)

        if modality == "multimodal":
            trained_multimodal = logistic
            trained_feature_names = cols

    metrics = {"models": [r.__dict__ for r in all_results]}
    (results_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    comparison = pd.DataFrame([r.__dict__ for r in all_results])
    comparison.to_csv(results_dir / "model_comparison.csv", index=False)

    _write_model_comparison_chart(comparison, charts_dir / "model_comparison.png")
    _write_confusion_matrices(all_results, charts_dir)

    if trained_multimodal is not None:
        export_app_model(trained_multimodal, trained_feature_names, features, results_dir / "app_model.json")
        joblib.dump(trained_multimodal, results_dir / "logistic_multimodal.joblib")

    return metrics


def export_app_model(model: Pipeline, feature_names: list[str], features: pd.DataFrame, path: Path) -> None:
    scaler: StandardScaler = model.named_steps["scaler"]
    logistic: LogisticRegression = model.named_steps["model"]
    artifact = {
        "modelName": "psycon_wesad_logistic_multimodal",
        "modelVersion": "0.1.0",
        "featureNames": feature_names,
        "classMapping": {"0": "calm", "1": "high_stress"},
        "scoreThresholds": STATE_THRESHOLDS,
        "scaler": {
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "logisticRegression": {
            "coefficients": logistic.coef_[0].tolist(),
            "intercept": float(logistic.intercept_[0]),
        },
        "baseline": {
            "description": "Rule baseline used only for comparison; app inference uses logisticRegression by default.",
            "edaMeanMedian": float(features["eda_mean"].median()),
            "motionMeanMedian": float(features["acc_mag_mean"].median()),
        },
        "trainingMetadata": {
            "dataset": "WESAD",
            "labelPolicy": "baseline=calm, stress=high_stress, amusement/other ignored",
            "windowSeconds": WINDOW_SECONDS,
            "hopSeconds": HOP_SECONDS,
            "commonHz": COMMON_HZ,
        },
    }
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def _evaluate(name: str, modality: str, model: Any, x_test: pd.DataFrame, y_test: np.ndarray) -> ModelResult:
    y_pred = model.predict(x_test)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="binary", zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    tn, fp, _, _ = cm.ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) else 0.0
    return ModelResult(
        name=name,
        modality=modality,
        accuracy=float(accuracy_score(y_test, y_pred)),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        false_positive_rate=fpr,
        actual_stress=int(np.sum(y_test == 1)),
        predicted_stress=int(np.sum(y_pred == 1)),
        confusion_matrix=cm.astype(int).tolist(),
    )


def _try_train_xgboost(x_train: pd.DataFrame, y_train: np.ndarray, x_test: pd.DataFrame, y_test: np.ndarray, modality: str) -> ModelResult | None:
    try:
        from xgboost import XGBClassifier
    except Exception as exc:
        print(f"Skipping XGBoost for {modality}: {exc}")
        return None
    model = XGBClassifier(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return _evaluate("xgboost", modality, model, x_test, y_test)


def _try_train_lightgbm(x_train: pd.DataFrame, y_train: np.ndarray, x_test: pd.DataFrame, y_test: np.ndarray, modality: str) -> ModelResult | None:
    try:
        from lightgbm import LGBMClassifier
    except Exception as exc:
        print(f"Skipping LightGBM for {modality}: {exc}")
        return None
    model = LGBMClassifier(
        n_estimators=160,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(x_train, y_train)
    return _evaluate("lightgbm", modality, model, x_test, y_test)


def _write_model_comparison_chart(comparison: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    plt.figure(figsize=(12, 6))
    sns.barplot(data=comparison, x="modality", y="accuracy", hue="name")
    plt.ylim(0, 1)
    plt.title("WESAD Stress Detection Accuracy by Modality and Model")
    plt.ylabel("Accuracy")
    plt.xlabel("Modality")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _write_confusion_matrices(results: list[ModelResult], charts_dir: Path) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    for result in results:
        if result.modality != "multimodal":
            continue
        plt.figure(figsize=(4, 3))
        sns.heatmap(result.confusion_matrix, annot=True, fmt="d", cmap="Blues", xticklabels=["calm", "stress"], yticklabels=["calm", "stress"])
        plt.title(f"{result.name} ({result.modality})")
        plt.xlabel("Predicted")
        plt.ylabel("Actual")
        plt.tight_layout()
        plt.savefig(charts_dir / f"confusion_matrix_{result.name}_{result.modality}.png", dpi=180)
        plt.close()
