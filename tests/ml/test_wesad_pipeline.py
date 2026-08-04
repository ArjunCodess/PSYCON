from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.src.features import add_subject_baseline_features, extract_windows, feature_columns
from ml.src.models.baseline import RuleBaseline
from ml.src.models.train import export_app_model
from ml.src.preprocess import subject_to_frame
from ml.src.wesad import discover_subjects, load_subject, map_wesad_label


def require_wesad_subject():
    subjects = discover_subjects()
    if not subjects:
        pytest.skip("raw WESAD files are external; see README.md for data/raw/wesad layout")
    return subjects[0]


def test_discover_subjects_finds_local_wesad_data() -> None:
    assert require_wesad_subject().path.exists()


def test_loader_reads_one_subject() -> None:
    subject = require_wesad_subject()
    data = load_subject(subject)
    assert "signal" in data
    assert "wrist" in data["signal"]
    assert "label" in data


def test_label_mapping_keeps_only_baseline_and_stress() -> None:
    assert map_wesad_label(1) == "calm"
    assert map_wesad_label(2) == "high_stress"
    assert map_wesad_label(3) is None
    assert map_wesad_label(0) is None


def test_windowing_and_feature_extraction_from_synthetic_frame() -> None:
    samples = 40
    frame = pd.DataFrame({
        "subject": "S0",
        "time_s": np.arange(samples) / 4,
        "acc_x": np.ones(samples),
        "acc_y": np.zeros(samples),
        "acc_z": np.zeros(samples),
        "bvp": np.linspace(0, 1, samples),
        "eda": np.linspace(1, 2, samples),
        "temp": np.linspace(33, 34, samples),
        "wesad_label": np.ones(samples, dtype=int),
    })
    windows = extract_windows(frame)
    assert len(windows) == 1
    assert {"eda_mean", "eda_slope", "eda_peak_count", "bvp_range", "bvp_peak_count", "acc_mag_mean", "jerk_max", "temp_change"}.issubset(windows.columns)
    assert feature_columns(windows.columns)


def test_subject_baseline_features_add_personalized_deltas() -> None:
    features = pd.DataFrame({
        "subject": ["S0", "S0", "S1", "S1"],
        "window_start_s": [0.0, 2.0, 0.0, 2.0],
        "window_end_s": [10.0, 12.0, 10.0, 12.0],
        "label": ["calm", "high_stress", "calm", "high_stress"],
        "label_binary": [0, 1, 0, 1],
        "bvp_mean": [70.0, 80.0, 90.0, 100.0],
        "bvp_std": [1.0, 2.0, 1.0, 2.0],
        "eda_mean": [0.5, 0.9, 1.5, 1.9],
        "eda_slope": [0.0, 0.1, 0.0, 0.2],
        "eda_peak_count": [0.0, 3.0, 1.0, 4.0],
        "temp_mean": [33.0, 32.8, 34.0, 33.7],
        "acc_mag_mean": [1.0, 1.8, 1.2, 2.0],
        "jerk_mean": [0.1, 0.4, 0.2, 0.5],
    })
    output = add_subject_baseline_features(features)
    assert output.loc[0, "eda_mean_baseline_diff"] == 0.0
    assert output.loc[1, "eda_mean_baseline_diff"] == 0.4
    assert output.loc[3, "acc_mag_mean_baseline_diff"] == 0.8


def test_subject_preprocess_smoke_uses_wrist_signals() -> None:
    subject = require_wesad_subject()
    frame = subject_to_frame(subject.subject_id, load_subject(subject))
    assert {"acc_x", "acc_y", "acc_z", "bvp", "eda", "temp", "wesad_label"}.issubset(frame.columns)
    assert len(frame) > 100


def test_model_export_writes_valid_json(tmp_path: Path) -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    features = pd.DataFrame({
        "eda_mean": [0.1, 0.2, 2.0, 2.2],
        "acc_mag_mean": [1.0, 1.1, 4.0, 4.2],
        "label_binary": [0, 0, 1, 1],
    })
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression().fit([[0, 0], [0.1, 0.1], [2, 3], [2.1, 3.2]], [0, 0, 1, 1])),
    ])
    model.fit(features[["eda_mean", "acc_mag_mean"]], features["label_binary"])
    path = tmp_path / "app_model.json"
    export_app_model(model, ["eda_mean", "acc_mag_mean"], features, path)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["modelName"] == "psycon_wesad_logistic_multimodal"
    assert artifact["featureNames"] == ["eda_mean", "acc_mag_mean"]


def test_rule_baseline_works_without_eda_or_motion_columns() -> None:
    x_train = pd.DataFrame({
        "temp_mean": [33.0, 33.1, 35.0, 35.2],
        "temp_change": [0.0, 0.1, 1.4, 1.5],
    })
    y_train = np.array([0, 0, 1, 1])
    x_test = pd.DataFrame({
        "temp_mean": [33.05, 35.1],
        "temp_change": [0.0, 1.6],
    })

    predictions = RuleBaseline().fit(x_train, y_train).predict(x_test)

    assert predictions.tolist() == [0, 1]
