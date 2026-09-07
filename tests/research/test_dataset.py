from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.dataset import assemble_feature_windows, build_dataset_manifest, modality_dataset, write_manifest
from research.schema import MetadataError, validate_session_metadata


def valid_metadata() -> dict:
    return {
        "schema_version": "1.0.0",
        "session_id": "SESSION-01",
        "participant_id": "P-7F3A91",
        "protocol_version": "1.0.0",
        "approval_id": "IRB-2026-01",
        "consent_version": "1.0.0",
        "consent": {
            "physiology": True,
            "audio": True,
            "transcription": True,
            "voice_profile": False,
            "withdrawn": False,
        },
        "demographics": {"age_group": "18-24", "biological_sex": "not_collected"},
        "recording": {
            "started_at_utc": "2026-09-07T10:00:00Z",
            "duration_seconds": 120,
            "environment": "quiet_indoor",
            "motion_condition": "seated",
            "stop_reason": "completed",
        },
        "device": {
            "hardware_revision": "wrist-a1",
            "wrist_firmware_version": "0.3.0",
            "audio_firmware_version": "0.3.0",
            "calibration_record_ids": ["CAL-01"],
        },
        "synchronization": {"max_uncertainty_ms": 12.5, "quality": "verified"},
        "eligibility": {"included": True, "reason_codes": []},
        "operator_id": "OP-01",
    }


def feature_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    keys = {
        "participant_id": ["P-AAAAAA", "P-AAAAAA"],
        "session_id": ["SESSION-01", "SESSION-01"],
        "window_start_ms": [0, 10_000],
        "window_end_ms": [10_000, 20_000],
        "label": [0, 1],
    }
    physiology = pd.DataFrame({**keys, "quality_state": ["usable", "low_quality"], "eda_mean": [0.4, 0.8]})
    speech = pd.DataFrame({**keys, "quality_state": ["usable", "untranscribable"], "pitch_mean": [180.0, None]})
    context = pd.DataFrame({**keys, "quality_state": ["usable", "usable"], "ambient_light": [0.2, 0.7]})
    return physiology, speech, context


def test_metadata_accepts_anonymous_approved_session() -> None:
    metadata = valid_metadata()
    result = validate_session_metadata(metadata)
    assert result == metadata
    assert result is not metadata


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.update({"name": "identifying"}), "direct identifier"),
        (lambda item: item["consent"].update({"withdrawn": True}), "withdrawn"),
        (lambda item: item.update({"approval_id": "pending-approval"}), "approval_id"),
        (lambda item: item["consent"].update({"audio": False}), "transcription consent"),
    ],
)
def test_metadata_rejects_unsafe_or_unapproved_records(mutation, message: str) -> None:
    metadata = valid_metadata()
    mutation(metadata)
    with pytest.raises(MetadataError, match=message):
        validate_session_metadata(metadata)


def test_assembly_preserves_bad_and_missing_modalities() -> None:
    physiology, speech, context = feature_tables()
    speech = speech.iloc[:1]
    windows = assemble_feature_windows(physiology, speech, context)

    assert windows["speech__quality_state"].tolist() == ["usable", "missing"]
    assert windows["physiology__usable"].tolist() == [True, False]
    assert pd.isna(windows.loc[1, "physiology__eda_mean"])
    assert windows["usable_modality_count"].tolist() == [3, 1]
    assert windows["missing_or_bad"].tolist() == [False, True]


def test_assembly_rejects_label_conflicts() -> None:
    physiology, speech, context = feature_tables()
    speech.loc[0, "label"] = 1
    with pytest.raises(ValueError, match="conflicting labels"):
        assemble_feature_windows(physiology, speech, context)


def test_modality_views_reuse_identical_windows() -> None:
    windows = assemble_feature_windows(*feature_tables())
    physiology, physiology_columns = modality_dataset(windows, "physiology")
    combined, combined_columns = modality_dataset(windows, "combined")
    assert physiology[["participant_id", "session_id", "window_start_ms"]].equals(
        combined[["participant_id", "session_id", "window_start_ms"]]
    )
    assert physiology_columns == ["physiology__eda_mean"]
    assert set(combined_columns) == {"physiology__eda_mean", "speech__pitch_mean", "context__ambient_light"}


def test_manifest_hashes_only_explicit_files_inside_root(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "sample.json"
    source.parent.mkdir()
    source.write_text('{"sample": 1}\n', encoding="utf-8")
    manifest = build_dataset_manifest(
        tmp_path,
        [source],
        dataset_version="fixture-1.0.0",
        protocol_version="1.0.0",
        source_kind="fixture",
        created_at_utc="2026-09-07T00:00:00Z",
    )
    output = tmp_path / "manifest.json"
    write_manifest(output, manifest)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["files"][0]["path"] == "raw/sample.json"
    assert loaded["created_at_utc"] == "2026-09-07T00:00:00Z"
    assert len(loaded["files"][0]["sha256"]) == 64
    with pytest.raises(ValueError, match="outside dataset root"):
        build_dataset_manifest(tmp_path, [Path(__file__)], dataset_version="x", protocol_version="x", source_kind="fixture")
