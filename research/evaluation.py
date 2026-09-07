from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score, roc_curve
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .dataset import KEY_COLUMNS, modality_dataset


@dataclass(frozen=True)
class SplitConfig:
    seed: int = 42
    train_fraction: float = 0.6
    validation_fraction: float = 0.2


def assign_participants(windows: pd.DataFrame, config: SplitConfig = SplitConfig()) -> pd.DataFrame:
    """Create one deterministic participant assignment for every modality."""
    participants = sorted(windows["participant_id"].astype(str).unique())
    if len(participants) < 5:
        raise ValueError("at least five participants are required for train, validation, and test splits")
    if not 0 < config.train_fraction < 1 or not 0 < config.validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if config.train_fraction + config.validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a non-empty test split")

    rng = np.random.default_rng(config.seed)
    shuffled = np.asarray(participants, dtype=object)
    rng.shuffle(shuffled)
    train_count = max(1, int(np.floor(len(shuffled) * config.train_fraction)))
    validation_count = max(1, int(np.floor(len(shuffled) * config.validation_fraction)))
    if train_count + validation_count >= len(shuffled):
        validation_count = 1
        train_count = len(shuffled) - 2
    split = np.full(len(shuffled), "test", dtype=object)
    split[:train_count] = "train"
    split[train_count : train_count + validation_count] = "validation"
    result = pd.DataFrame({"participant_id": shuffled, "split": split}).sort_values("participant_id").reset_index(drop=True)
    result["split_seed"] = config.seed
    return result


def evaluate_modalities(
    windows: pd.DataFrame,
    assignments: pd.DataFrame,
    *,
    external_windows: pd.DataFrame | None = None,
    bootstrap_iterations: int = 500,
    seed: int = 42,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Train candidates and compare frozen modalities on one participant split."""
    prepared = windows.merge(assignments[["participant_id", "split"]], on="participant_id", how="left", validate="many_to_one")
    if prepared["split"].isna().any():
        raise ValueError("every participant must have a split assignment")
    _validate_split(prepared)

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "purpose": "non-clinical research comparison",
        "split": {
            "participant_counts": assignments.groupby("split")["participant_id"].nunique().to_dict(),
            "leakage_detected": False,
            "assignment_sha256": _assignment_hash(assignments),
        },
        "data_integrity": _data_integrity(prepared),
        "modalities": {},
        "ablation": {},
        "external_validation": {"status": "blocked", "reason": "no separate external dataset supplied"},
        "limitations": [
            "Outputs are research indicators and are not clinical diagnoses.",
            "Performance on one dataset does not validate PSYCON hardware or another participant population.",
            "Context slices are descriptive and may be unreliable when participant or class counts are small.",
        ],
    }
    all_predictions: list[pd.DataFrame] = []
    fitted: dict[str, tuple[BaseEstimator, list[str]]] = {}

    for modality in ("physiology", "speech", "combined"):
        view, feature_columns = modality_dataset(prepared, modality)
        view = view.join(prepared[["split"]])
        train = view[view["split"] == "train"]
        validation = view[view["split"] == "validation"]
        test = view[view["split"] == "test"]
        _require_binary_labels(train, f"{modality} training")
        _require_binary_labels(test, f"{modality} test")

        candidates = _candidate_models(seed)
        candidate_results: dict[str, Any] = {}
        selected_name = ""
        selected_score = -1.0
        for name, candidate in candidates.items():
            candidate.fit(train[feature_columns], train["label"].astype(int))
            validation_predictions = candidate.predict(validation[feature_columns])
            validation_probabilities = _positive_probability(candidate, validation[feature_columns])
            result = classification_metrics(validation["label"], validation_predictions, validation_probabilities)
            result["group_cross_validation"] = _group_cross_validation(
                candidate_factory=lambda name=name: _candidate_models(seed)[name],
                development=pd.concat([train, validation], ignore_index=True),
                feature_columns=feature_columns,
            )
            candidate_results[name] = result
            selection_score = float(result["f1"])
            if selection_score > selected_score or (selection_score == selected_score and name < selected_name):
                selected_name = name
                selected_score = selection_score

        selected = _candidate_models(seed)[selected_name]
        development = pd.concat([train, validation], ignore_index=True)
        selected.fit(development[feature_columns], development["label"].astype(int))
        predictions = selected.predict(test[feature_columns]).astype(int)
        probabilities = _positive_probability(selected, test[feature_columns])
        test_metrics = classification_metrics(test["label"], predictions, probabilities)
        test_metrics["confidence_intervals_95"] = participant_bootstrap_intervals(
            test,
            predictions,
            probabilities,
            iterations=bootstrap_iterations,
            seed=seed,
        )

        prediction_frame = prepared.loc[test.index, KEY_COLUMNS + ["label", "data_quality_score"]].copy()
        prediction_frame["modality"] = modality
        prediction_frame["model"] = selected_name
        prediction_frame["prediction"] = predictions
        prediction_frame["probability"] = probabilities
        all_predictions.append(prediction_frame)

        modality_report = {
            "features": feature_columns,
            "selected_model": selected_name,
            "selection_metric": "validation_f1",
            "candidates": candidate_results,
            "test": test_metrics,
            "quality": _quality_summary(test),
            "environment_slices": _slice_metrics(prepared.loc[test.index], predictions, probabilities, "context__environment"),
            "motion_slices": _slice_metrics(prepared.loc[test.index], predictions, probabilities, "context__motion_condition"),
            "duration_analysis": _duration_analysis(prepared.loc[test.index], predictions, probabilities),
        }
        report["modalities"][modality] = modality_report
        fitted[modality] = (selected, feature_columns)

    combined_f1 = report["modalities"]["combined"]["test"]["f1"]
    report["ablation"] = {
        "combined_minus_physiology_f1": combined_f1 - report["modalities"]["physiology"]["test"]["f1"],
        "combined_minus_speech_f1": combined_f1 - report["modalities"]["speech"]["test"]["f1"],
    }

    if external_windows is not None:
        overlap = set(prepared["participant_id"].astype(str)) & set(external_windows["participant_id"].astype(str))
        if overlap:
            raise ValueError("external validation participants overlap the development dataset")
        external_report: dict[str, Any] = {"status": "evaluated", "participant_count": int(external_windows["participant_id"].nunique()), "modalities": {}}
        for modality, (model, feature_columns) in fitted.items():
            external_view, external_columns = modality_dataset(external_windows, modality)
            if external_columns != feature_columns:
                raise ValueError(f"external {modality} features do not match development features")
            predictions = model.predict(external_view[feature_columns]).astype(int)
            probabilities = _positive_probability(model, external_view[feature_columns])
            external_report["modalities"][modality] = classification_metrics(external_view["label"], predictions, probabilities)
        report["external_validation"] = external_report

    return report, pd.concat(all_predictions, ignore_index=True)


def write_evaluation_artifacts(
    output_dir: Path,
    report: dict[str, Any],
    predictions: pd.DataFrame,
    assignments: pd.DataFrame,
    windows: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    (output_dir / "evaluation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    predictions[predictions["label"] != predictions["prediction"]].to_csv(output_dir / "errors.csv", index=False)
    assignments.to_csv(output_dir / "split_assignments.csv", index=False)
    _descriptive_statistics(windows).to_csv(output_dir / "descriptive_statistics.csv", index=False)
    _correlations(windows).to_csv(output_dir / "correlations.csv", index=False)
    _write_charts(report, predictions, charts_dir)


def classification_metrics(y_true: pd.Series | np.ndarray, y_pred: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    truth = np.asarray(y_true, dtype=int)
    predicted = np.asarray(y_pred, dtype=int)
    precision, recall, f1, _ = precision_recall_fscore_support(truth, predicted, average="binary", zero_division=0)
    matrix = confusion_matrix(truth, predicted, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    auc = float(roc_auc_score(truth, probability)) if len(np.unique(truth)) == 2 else None
    return {
        "samples": int(len(truth)),
        "accuracy": float(accuracy_score(truth, predicted)),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": auc,
        "confusion_matrix": matrix.astype(int).tolist(),
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
    }


def participant_bootstrap_intervals(
    test: pd.DataFrame,
    predictions: np.ndarray,
    probabilities: np.ndarray,
    *,
    iterations: int,
    seed: int,
) -> dict[str, list[float] | None]:
    if iterations < 1:
        return {name: None for name in ("accuracy", "precision", "recall", "f1", "roc_auc")}
    working = test[["participant_id", "label"]].reset_index(drop=True).copy()
    working["prediction"] = predictions
    working["probability"] = probabilities
    participants = working["participant_id"].unique()
    rng = np.random.default_rng(seed)
    values: dict[str, list[float]] = {name: [] for name in ("accuracy", "precision", "recall", "f1", "roc_auc")}
    for _ in range(iterations):
        sampled = rng.choice(participants, size=len(participants), replace=True)
        sample = pd.concat([working[working["participant_id"] == participant] for participant in sampled], ignore_index=True)
        metrics = classification_metrics(sample["label"], sample["prediction"].to_numpy(), sample["probability"].to_numpy())
        for name in values:
            value = metrics[name]
            if value is not None:
                values[name].append(float(value))
    return {
        name: [float(np.quantile(items, 0.025)), float(np.quantile(items, 0.975))] if items else None
        for name, items in values.items()
    }


def _candidate_models(seed: int) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestClassifier(n_estimators=160, max_depth=8, class_weight="balanced", random_state=seed, n_jobs=-1)),
        ]),
    }


def _positive_probability(model: BaseEstimator, features: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict_proba(features))[:, 1]


def _group_cross_validation(
    candidate_factory: Callable[[], BaseEstimator],
    development: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, Any]:
    group_count = development["participant_id"].nunique()
    folds = min(5, group_count)
    if folds < 2:
        return {"folds": 0, "f1_mean": None, "f1_std": None, "scores": []}
    scores: list[float] = []
    splitter = GroupKFold(n_splits=folds)
    for train_index, validation_index in splitter.split(development, development["label"], development["participant_id"]):
        train = development.iloc[train_index]
        validation = development.iloc[validation_index]
        if train["label"].nunique() < 2:
            continue
        model = candidate_factory()
        model.fit(train[feature_columns], train["label"].astype(int))
        predicted = model.predict(validation[feature_columns])
        score = precision_recall_fscore_support(validation["label"], predicted, average="binary", zero_division=0)[2]
        scores.append(float(score))
    return {
        "folds": len(scores),
        "f1_mean": float(np.mean(scores)) if scores else None,
        "f1_std": float(np.std(scores)) if scores else None,
        "scores": scores,
    }


def _quality_summary(test: pd.DataFrame) -> dict[str, Any]:
    return {
        "mean_data_quality_score": float(test["data_quality_score"].mean()),
        "complete_windows": int((test["data_quality_score"] == 1.0).sum()),
        "incomplete_windows": int((test["data_quality_score"] < 1.0).sum()),
    }


def _slice_metrics(frame: pd.DataFrame, predictions: np.ndarray, probabilities: np.ndarray, column: str) -> dict[str, Any]:
    if column not in frame:
        return {"status": "not_available", "slices": {}}
    working = frame[[column, "label"]].reset_index(drop=True).copy()
    working["prediction"] = predictions
    working["probability"] = probabilities
    slices: dict[str, Any] = {}
    for value, group in working.groupby(column, dropna=False):
        name = "missing" if pd.isna(value) else str(value)
        slices[name] = classification_metrics(group["label"], group["prediction"].to_numpy(), group["probability"].to_numpy())
    return {"status": "descriptive", "slices": slices}


def _duration_analysis(frame: pd.DataFrame, predictions: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    working = frame[["participant_id", "session_id", "window_start_ms", "window_end_ms", "label"]].reset_index(drop=True).copy()
    working["prediction"] = predictions
    working["probability"] = probabilities
    session_start = working.groupby(["participant_id", "session_id"])["window_start_ms"].transform("min")
    working["elapsed_seconds"] = (working["window_end_ms"] - session_start) / 1000.0
    full_session_probability = working.groupby(["participant_id", "session_id"])["probability"].transform("mean")
    durations: dict[str, Any] = {}
    for seconds in (10, 30, 60):
        subset = working[working["elapsed_seconds"] <= seconds]
        if subset.empty:
            durations[str(seconds)] = {"status": "insufficient_data"}
            continue
        metrics = classification_metrics(subset["label"], subset["prediction"].to_numpy(), subset["probability"].to_numpy())
        metrics["mean_probability_difference_from_full_session"] = float(
            np.mean(np.abs(subset["probability"] - full_session_probability.loc[subset.index]))
        )
        durations[str(seconds)] = metrics
    return {
        "status": "descriptive",
        "stability_tolerance": "must be frozen in the approved protocol before participant collection",
        "durations_seconds": durations,
    }


def _data_integrity(frame: pd.DataFrame) -> dict[str, Any]:
    numeric = frame.select_dtypes(include=[np.number])
    return {
        "windows": int(len(frame)),
        "participants": int(frame["participant_id"].nunique()),
        "sessions": int(frame["session_id"].nunique()),
        "duplicate_windows": int(frame.duplicated(KEY_COLUMNS).sum()),
        "missing_labels": int(frame["label"].isna().sum()),
        "nonfinite_numeric_values": int(np.isinf(numeric.to_numpy(dtype=float)).sum()),
        "windows_with_missing_or_bad_modality": int(frame["missing_or_bad"].sum()),
    }


def _descriptive_statistics(windows: pd.DataFrame) -> pd.DataFrame:
    numeric_columns = [column for column in windows.select_dtypes(include=[np.number]).columns if column not in {"label", "window_start_ms", "window_end_ms"}]
    if not numeric_columns:
        return pd.DataFrame(columns=["feature", "count", "mean", "std", "min", "median", "max", "missing"])
    rows: list[dict[str, Any]] = []
    for column in numeric_columns:
        series = windows[column]
        rows.append({
            "feature": column,
            "count": int(series.count()),
            "mean": float(series.mean()),
            "std": float(series.std()) if series.count() > 1 else None,
            "min": float(series.min()),
            "median": float(series.median()),
            "max": float(series.max()),
            "missing": int(series.isna().sum()),
        })
    return pd.DataFrame(rows)


def _correlations(windows: pd.DataFrame) -> pd.DataFrame:
    numeric = windows.select_dtypes(include=[np.number]).drop(columns=["window_start_ms", "window_end_ms"], errors="ignore")
    if "label" not in numeric or len(numeric.columns) < 2:
        return pd.DataFrame(columns=["feature", "label_pearson_correlation"])
    correlations = numeric.corr(numeric_only=True)["label"].drop(labels=["label"], errors="ignore")
    return correlations.rename("label_pearson_correlation").rename_axis("feature").reset_index()


def _write_charts(report: dict[str, Any], predictions: pd.DataFrame, charts_dir: Path) -> None:
    import matplotlib.pyplot as plt

    modalities = list(report["modalities"])
    f1_scores = [report["modalities"][modality]["test"]["f1"] for modality in modalities]
    fig, axis = plt.subplots(figsize=(7, 4))
    axis.bar(modalities, f1_scores, color=["#315c8c", "#8c5a31", "#3f7d58"])
    axis.set_ylim(0, 1)
    axis.set_ylabel("F1")
    axis.set_title("Participant-separated modality comparison")
    fig.tight_layout()
    fig.savefig(charts_dir / "modality_f1.png", dpi=160)
    plt.close(fig)

    for modality in modalities:
        subset = predictions[predictions["modality"] == modality]
        matrix = confusion_matrix(subset["label"], subset["prediction"], labels=[0, 1])
        fig, axis = plt.subplots(figsize=(4, 4))
        image = axis.imshow(matrix, cmap="Blues")
        for row in range(2):
            for column in range(2):
                axis.text(column, row, str(matrix[row, column]), ha="center", va="center")
        axis.set_xticks([0, 1], ["calm", "target"])
        axis.set_yticks([0, 1], ["calm", "target"])
        axis.set_xlabel("Predicted")
        axis.set_ylabel("Actual")
        axis.set_title(f"{modality} confusion matrix")
        fig.colorbar(image, ax=axis)
        fig.tight_layout()
        fig.savefig(charts_dir / f"confusion_matrix_{modality}.png", dpi=160)
        plt.close(fig)

        if subset["label"].nunique() == 2:
            false_positive_rate, true_positive_rate, _ = roc_curve(subset["label"], subset["probability"])
            fig, axis = plt.subplots(figsize=(4, 4))
            axis.plot(false_positive_rate, true_positive_rate, color="#315c8c")
            axis.plot([0, 1], [0, 1], linestyle="--", color="#777777")
            axis.set_xlim(0, 1)
            axis.set_ylim(0, 1)
            axis.set_xlabel("False-positive rate")
            axis.set_ylabel("True-positive rate")
            axis.set_title(f"{modality} ROC curve")
            fig.tight_layout()
            fig.savefig(charts_dir / f"roc_curve_{modality}.png", dpi=160)
            plt.close(fig)


def _validate_split(frame: pd.DataFrame) -> None:
    if frame.duplicated(KEY_COLUMNS).any():
        raise ValueError("evaluation input has duplicate windows")
    if frame["label"].isna().any():
        raise ValueError("evaluation input has missing labels")
    split_counts = frame.groupby("participant_id")["split"].nunique()
    if (split_counts != 1).any():
        raise ValueError("participant leakage detected across splits")
    if set(frame["split"].unique()) != {"train", "validation", "test"}:
        raise ValueError("train, validation, and test splits are all required")


def _require_binary_labels(frame: pd.DataFrame, name: str) -> None:
    labels = set(frame["label"].astype(int).unique())
    if labels != {0, 1}:
        raise ValueError(f"{name} data must contain both binary classes")


def _assignment_hash(assignments: pd.DataFrame) -> str:
    canonical = assignments.sort_values("participant_id").to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
