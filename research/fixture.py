from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .dataset import assemble_feature_windows, build_dataset_manifest, write_manifest


DATASET_VERSION = "week5-fixture-1.0.0"
PROTOCOL_VERSION = "1.0.0"
SEED = 20260907


def generate_fixture_tables(*, participant_count: int = 15, windows_per_participant: int = 12) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate deterministic non-human records that exercise the Week 5 pipeline."""
    if participant_count < 5 or windows_per_participant < 4:
        raise ValueError("fixture requires at least five participants and four windows per participant")
    rng = np.random.default_rng(SEED)
    physiology_rows: list[dict] = []
    speech_rows: list[dict] = []
    context_rows: list[dict] = []

    for participant_number in range(participant_count):
        participant_id = f"F-{participant_number:06d}"
        session_id = f"FIXTURE-{participant_number:04d}"
        participant_offset = rng.normal(0, 0.08)
        environment = ("quiet_indoor", "conversation_noise", "outdoor")[participant_number % 3]
        for window_number in range(windows_per_participant):
            label = int((window_number // 3 + participant_number) % 2)
            motion = "walking" if window_number % 4 == 3 else "seated"
            start_ms = window_number * 10_000
            keys = {
                "participant_id": participant_id,
                "session_id": session_id,
                "window_start_ms": start_ms,
                "window_end_ms": start_ms + 10_000,
                "label": label,
            }
            motion_noise = 0.3 if motion == "walking" else 0.0
            physiology_rows.append({
                **keys,
                "quality_state": "low_quality" if motion == "walking" and window_number % 8 == 3 else "usable",
                "eda_mean": 0.8 + label * 0.9 + participant_offset + rng.normal(0, 0.12 + motion_noise),
                "heart_rate": 66 + label * 13 + participant_offset * 5 + rng.normal(0, 2.5 + motion_noise * 4),
                "temperature_mean": 33.4 - label * 0.15 + rng.normal(0, 0.08),
                "motion_rms": (0.2 if motion == "seated" else 1.4) + rng.normal(0, 0.08),
            })
            speech_quality = "untranscribable" if environment == "conversation_noise" and window_number % 6 == 5 else "usable"
            speech_rows.append({
                **keys,
                "quality_state": speech_quality,
                "pitch_mean": 145 + label * 18 + participant_offset * 10 + rng.normal(0, 7),
                "speaking_rate": 2.9 + label * 0.35 + rng.normal(0, 0.18),
                "pause_fraction": 0.27 - label * 0.06 + rng.normal(0, 0.03),
                "negative_word_rate": 0.05 + label * 0.22 + rng.normal(0, 0.04),
            })
            context_rows.append({
                **keys,
                "quality_state": "usable",
                "ambient_light": (0.2, 0.55, 0.85)[participant_number % 3] + rng.normal(0, 0.03),
                "environment": environment,
                "motion_condition": motion,
            })

    speech = pd.DataFrame(speech_rows)
    missing_rows = (speech.index % 37) == 0
    speech.loc[missing_rows, ["pitch_mean", "speaking_rate", "pause_fraction", "negative_word_rate"]] = np.nan
    speech.loc[missing_rows, "quality_state"] = "missing"
    return pd.DataFrame(physiology_rows), speech, pd.DataFrame(context_rows)


def write_fixture_dataset(root: Path) -> pd.DataFrame:
    physiology, speech, context = generate_fixture_tables()
    raw_dir = root / "raw"
    metadata_dir = root / "metadata"
    feature_dir = root / "features"
    for directory in (raw_dir, metadata_dir, feature_dir):
        directory.mkdir(parents=True, exist_ok=True)
    physiology.to_csv(raw_dir / "physiology.csv", index=False)
    speech.to_csv(raw_dir / "speech.csv", index=False)
    context.to_csv(raw_dir / "context.csv", index=False)

    windows = assemble_feature_windows(physiology, speech, context)
    windows.to_csv(feature_dir / "synchronized_windows.csv", index=False)
    sessions = [
        {
            "participant_id": participant_id,
            "session_id": group["session_id"].iloc[0],
            "source_kind": "synthetic_fixture",
            "human_participant": False,
            "environment": group["context__environment"].iloc[0],
            "duration_seconds": int(group["window_end_ms"].max() / 1000),
        }
        for participant_id, group in windows.groupby("participant_id", sort=True)
    ]
    (metadata_dir / "sessions.json").write_text(json.dumps(sessions, indent=2) + "\n", encoding="utf-8")
    versions = {
        "dataset_version": DATASET_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "generator_seed": SEED,
        "source_kind": "synthetic_fixture",
        "claim_limits": [
            "No record came from a person or PSYCON hardware.",
            "Results test software behavior only and do not count as external validation.",
        ],
    }
    (metadata_dir / "versions.json").write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")

    files = [
        raw_dir / "physiology.csv",
        raw_dir / "speech.csv",
        raw_dir / "context.csv",
        metadata_dir / "sessions.json",
        metadata_dir / "versions.json",
        feature_dir / "synchronized_windows.csv",
    ]
    manifest = build_dataset_manifest(
        root,
        files,
        dataset_version=DATASET_VERSION,
        protocol_version=PROTOCOL_VERSION,
        source_kind="synthetic_fixture",
        created_at_utc="2026-09-07T00:00:00Z",
    )
    write_manifest(root / "manifest.json", manifest)
    return windows
