from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.dataset import assemble_feature_windows
from research.evaluation import SplitConfig, assign_participants, evaluate_modalities, write_evaluation_artifacts


def fixture_windows(participant_prefix: str = "P") -> pd.DataFrame:
    physiology_rows = []
    speech_rows = []
    context_rows = []
    for participant_number in range(10):
        participant_id = f"{participant_prefix}-{participant_number:06d}"
        for window_number in range(8):
            label = window_number % 2
            keys = {
                "participant_id": participant_id,
                "session_id": f"SESSION-{participant_prefix}{participant_number:02d}",
                "window_start_ms": window_number * 10_000,
                "window_end_ms": (window_number + 1) * 10_000,
                "label": label,
            }
            offset = participant_number * 0.01
            physiology_rows.append({**keys, "quality_state": "usable", "eda_mean": label + offset, "heart_rate": 65 + label * 12 + offset})
            speech_rows.append({**keys, "quality_state": "usable" if window_number != 7 else "untranscribable", "pitch_mean": 130 + label * 25 + offset, "negative_word_rate": label * 0.5})
            context_rows.append({
                **keys,
                "quality_state": "usable",
                "ambient_light": float(participant_number % 3),
                "environment": "quiet" if participant_number % 2 == 0 else "noisy",
                "motion_condition": "seated" if window_number < 4 else "walking",
            })
    return assemble_feature_windows(pd.DataFrame(physiology_rows), pd.DataFrame(speech_rows), pd.DataFrame(context_rows))


def test_participant_assignment_is_deterministic_and_disjoint() -> None:
    windows = fixture_windows()
    first = assign_participants(windows, SplitConfig(seed=19))
    second = assign_participants(windows, SplitConfig(seed=19))
    assert first.equals(second)
    assert set(first["split"]) == {"train", "validation", "test"}
    assert first.groupby("participant_id")["split"].nunique().max() == 1


def test_evaluation_compares_same_holdout_and_reports_required_metrics() -> None:
    windows = fixture_windows()
    assignments = assign_participants(windows)
    report, predictions = evaluate_modalities(windows, assignments, bootstrap_iterations=20)

    assert set(report["modalities"]) == {"physiology", "speech", "combined"}
    assert report["split"]["leakage_detected"] is False
    assert report["external_validation"]["status"] == "blocked"
    assert set(predictions["modality"]) == {"physiology", "speech", "combined"}
    assert predictions.groupby("modality").size().nunique() == 1
    for result in report["modalities"].values():
        assert {"accuracy", "precision", "recall", "f1", "roc_auc", "confusion_matrix"}.issubset(result["test"])
        assert result["test"]["confidence_intervals_95"]["f1"] is not None
        assert result["environment_slices"]["status"] == "descriptive"
        assert result["motion_slices"]["status"] == "descriptive"


def test_external_validation_rejects_overlapping_participants() -> None:
    windows = fixture_windows()
    with pytest.raises(ValueError, match="overlap"):
        evaluate_modalities(windows, assign_participants(windows), external_windows=windows, bootstrap_iterations=2)


def test_artifact_writer_creates_tables_and_charts(tmp_path: Path) -> None:
    windows = fixture_windows()
    assignments = assign_participants(windows)
    report, predictions = evaluate_modalities(windows, assignments, bootstrap_iterations=2)
    write_evaluation_artifacts(tmp_path, report, predictions, assignments, windows)
    assert (tmp_path / "evaluation.json").is_file()
    assert (tmp_path / "predictions.csv").is_file()
    assert (tmp_path / "errors.csv").is_file()
    assert (tmp_path / "descriptive_statistics.csv").is_file()
    assert (tmp_path / "correlations.csv").is_file()
    assert (tmp_path / "charts" / "modality_f1.png").is_file()
    assert len(list((tmp_path / "charts").glob("confusion_matrix_*.png"))) == 3
    assert len(list((tmp_path / "charts").glob("roc_curve_*.png"))) == 3
