from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.src.features import extract_windows, feature_columns
from ml.src.models.train import export_app_model
from ml.src.preprocess import subject_to_frame
from ml.src.wesad import discover_subjects, load_subject, map_wesad_label


def test_discover_subjects_finds_local_wesad_data() -> None:
    subjects = discover_subjects()
    assert len(subjects) >= 1
    assert subjects[0].path.exists()


def test_loader_reads_one_subject() -> None:
    subject = discover_subjects()[0]
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
    assert len(windows) == 6
    assert {"eda_mean", "eda_slope", "bvp_range", "acc_mag_mean", "jerk_max", "temp_slope"}.issubset(windows.columns)
    assert feature_columns(windows.columns)


def test_subject_preprocess_smoke_uses_wrist_signals() -> None:
    subject = discover_subjects()[0]
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
