from __future__ import annotations

import json

import numpy as np

from research.group_observation import (
    assign_group_splits,
    associate_turns,
    claim_is_valid,
    evaluate_group_observations,
    interpret_examples,
    playback_fragment,
    predict_examples,
    speaker_mapping_error,
    split_hash,
)


def sessions_for(ids: list[str]) -> list[dict]:
    return [{"group_session_id": session_id, "participant_ids": [session_id]} for session_id in ids]


def example(session: str, score: str, *, participant: str | None = None, item: str = "A") -> dict:
    person = participant or session
    supervised = None if score == "N/O" else score
    return {
        "group_session_id": session,
        "participant_id": person,
        "research_code": person,
        "rater_id": "rater",
        "marksheet_version": "4.0",
        "rating_role": "primary",
        "item_letter": item,
        "score": score,
        "supervised_score": supervised,
        "evidence_start_s": 1.0,
        "evidence_end_s": 4.0,
        "evidence_intervals": [],
        "context_note": "The prior point was restated and the response stayed with it.",
        "baseline_start_s": 0.0 if item in "QRST" else None,
        "baseline_end_s": 1.0 if item in "QRST" else None,
        "trigger_start_s": 1.0 if item in "QRST" else None,
        "trigger_end_s": 1.5 if item in "QRST" else None,
        "quality_state": "usable",
        "source_recording_sha256": "a" * 64,
        "language": "en",
        "topic": "water",
        "features": {
            "speaking_s": 8.0,
            "overlap_s": 0.0,
            "turn_count": 1,
            "pause_count": 0,
            "transcript_tokens": 4,
            "transcript_text": "water policy point",
            "visibility": 1.0,
            "visible_interval": (5.0, 9.0) if item == "T" else None,
        },
        "transcript_text": "water policy point",
        "component": session,
    }


def test_shared_recording_and_repeat_participant_stay_in_one_split() -> None:
    sessions = [
        {"group_session_id": "video-a", "participant_ids": ["RED", "BLUE"]},
        {"group_session_id": "video-b", "participant_ids": ["BLUE", "GREEN"]},
        {"group_session_id": "video-c", "participant_ids": ["YELLOW"]},
        {"group_session_id": "video-d", "participant_ids": ["ORANGE"]},
        {"group_session_id": "video-e", "participant_ids": ["PURPLE"]},
    ]
    assignments = assign_group_splits(sessions, seed=7)
    split_of = {row["group_session_id"]: row["split"] for row in assignments}
    assert split_of["video-a"] == split_of["video-b"]
    people = {}
    for session in sessions:
        for person in session["participant_ids"]:
            people.setdefault(person, set()).add(split_of[session["group_session_id"]])
    assert all(len(splits) == 1 for splits in people.values())


def test_no_score_is_not_zero_and_small_samples_do_not_report_model_metrics() -> None:
    rows = [example("s1", "N/O"), example("s2", "0")]
    assert rows[0]["score"] == "N/O"
    assert rows[0]["supervised_score"] is None
    sessions = sessions_for(["s1", "s2"])
    digest = split_hash(assign_group_splits(sessions, seed=1))
    report = evaluate_group_observations(rows, sessions, frozen_split_hash=digest, seed=1)
    assert report["items"]["A"]["status"] == "unavailable"
    assert report["items"]["A"]["test_metrics"] is None
    assert report["validated_model"] is False
    assert report["items"]["A"]["descriptive"]["score_counts"]["N/O"] == 1
    try:
        evaluate_group_observations(rows, sessions, frozen_split_hash="0" * 64, seed=1)
    except ValueError as exc:
        assert "frozen" in str(exc)
    else:
        raise AssertionError("a changed split hash must be rejected before test metrics")


def test_frequency_baseline_and_cited_interval_when_evidence_is_sufficient() -> None:
    session_ids = [f"s{index}" for index in range(6)]
    rows = [example(session_id, "3") for session_id in session_ids]
    sessions = sessions_for(session_ids)
    digest = split_hash(assign_group_splits(sessions, seed=3))
    report = evaluate_group_observations(rows, sessions, frozen_split_hash=digest, seed=3)
    metrics = report["items"]["A"]["test_metrics"]
    assert report["items"]["A"]["status"] == "evaluated"
    assert metrics["exact_agreement"] == 1
    assert metrics["mean_absolute_error"] == 0
    assert "weighted_kappa" in metrics
    assert "abstention_rate" in metrics
    assert report["split_assignment_sha256"] == digest
    turns = [
        {
            "cluster_label": "cluster-a",
            "start_s": 5.0,
            "end_s": 9.0,
            "confirmed_participant_id": "s0",
            "overlap": False,
            "modality": "audio",
            "text": "water policy point",
        }
    ]
    training = [example(session_id, "3") for session_id in session_ids[1:]]
    predictions = predict_examples([rows[0]], training, turns, seed=3)
    prediction = next(row for row in predictions if row["item_letter"] == "A")
    assert prediction["abstained"] is False
    assert playback_fragment(prediction) == "#t=5.000,9.000"
    forged = dict(prediction, participant_id="someone-else")
    assert claim_is_valid(forged, "s0", turns) is False


def test_evidence_intervals_and_speaker_errors_are_scored() -> None:
    session_ids = [f"s{index}" for index in range(6)]
    rows = []
    for session_id in session_ids:
        row = example(session_id, "3")
        row["features"] = dict(row["features"])
        row["features"]["cited_interval"] = [1.0, 4.0]
        rows.append(row)
    sessions = sessions_for(session_ids)
    digest = split_hash(assign_group_splits(sessions, seed=3))
    turns = [{"proposed_participant_id": "other", "confirmed_participant_id": "s0"}]
    report = evaluate_group_observations(rows, sessions, frozen_split_hash=digest, seed=3, speaker_turns=turns)
    assert report["items"]["A"]["test_metrics"]["evidence_interval_accuracy"] == 1
    assert report["speaker_mapping_error"] == 1


def test_group_study_runner_writes_a_frozen_split(tmp_path) -> None:
    from research.run_group_study import run

    session_ids = [f"s{index}" for index in range(6)]
    rows = [example(session_id, "3") for session_id in session_ids]
    sessions = sessions_for(session_ids)
    examples_path = tmp_path / "examples.json"
    sessions_path = tmp_path / "sessions.json"
    examples_path.write_text(json.dumps(rows), encoding="utf-8")
    sessions_path.write_text(json.dumps(sessions), encoding="utf-8")
    report = run(examples_path=examples_path, sessions_path=sessions_path, output_dir=tmp_path / "out", seed=3)
    assert (tmp_path / "out" / "split_assignment.json").exists()
    assert (tmp_path / "out" / "evaluation.json").exists()
    assert (tmp_path / "out" / "manifest.json").exists()
    assert report["split_assignment_sha256"]


def test_energy_segments_stay_anonymous_and_missing_ffmpeg_is_recorded(monkeypatch) -> None:
    from backend.group.extract import _energy_segments, extract_group_recording

    samples = np.zeros(16_000, dtype=np.int16)
    samples[4_000:12_000] = 2_000
    turns = _energy_segments(samples, 16_000)
    assert turns
    assert all(not turn["cluster_label"].lower().startswith("participant") for turn in turns)
    monkeypatch.setattr("backend.group.extract.shutil.which", lambda _name: None)
    derived = extract_group_recording(b"video", {"sha256": "abc", "duration_s": 60})
    assert "audio_samples_not_extracted" in derived["failure_reasons"]
    assert derived["audio_wav"] is None


def test_ffmpeg_extracts_audio_and_a_thumbnail_without_naming_participants(monkeypatch, tmp_path) -> None:
    import shutil
    import subprocess

    import pytest

    from backend.group.extract import extract_group_recording

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    monkeypatch.setattr("backend.group.extract._transcribe", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("backend.group.extract._diarize", lambda *_args, **_kwargs: (None, "diarization_unavailable:test"))
    output = tmp_path / "talk.mp4"
    completed = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1:d=60",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(output),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        pytest.skip("ffmpeg could not encode the rehearsal recording")
    derived = extract_group_recording(output.read_bytes(), {"sha256": "abc", "duration_s": 60})
    assert derived["audio_wav"]
    assert derived["thumbnail_jpeg"]
    assert "audio_samples_not_extracted" not in derived["failure_reasons"]
    assert all(not turn["cluster_label"].lower().startswith("participant") for turn in derived["turns"])


def test_unknown_mappings_and_interpretation_rules() -> None:
    turns = associate_turns(
        [{"cluster_label": "cluster-1", "start_s": 0, "end_s": 2, "proposed_participant_id": "P-OTHER"}],
        [
            {"cluster_label": "cluster-1", "participant_id": "P1", "status": "uncertain"},
            {"cluster_label": "cluster-1", "participant_id": "P2", "status": "confirmed"},
        ],
    )
    assert turns[0]["confirmed_participant_id"] is None
    assert speaker_mapping_error(
        [{"proposed_participant_id": "P2", "confirmed_participant_id": "P1"}, {"proposed_participant_id": None, "confirmed_participant_id": "P1"}]
    ) == 1
    patterns = interpret_examples(
        [
            example("s", "0"),
            example("s", "1", item="B"),
            example("s", "2", item="C"),
            example("s", "4", item="D"),
            example("s", "4", item="Q"),
        ]
    )
    letters = {row["item_letter"] for row in patterns["psychologist_session_patterns"]}
    assert letters == {"D", "Q"}
    withheld = example("s", "4", item="Q")
    withheld["baseline_start_s"] = None
    withheld["trigger_start_s"] = None
    assert interpret_examples([withheld])["psychologist_session_patterns"] == []
