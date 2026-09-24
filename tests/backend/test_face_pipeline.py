from __future__ import annotations

import io
import subprocess
import sys
import shutil
from pathlib import Path

import numpy as np
import pytest

from backend.group.faces import face_feature, number_faces
from backend.group.extract import _energy_segments
from backend.group.labels import parse_label_csv
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupObservationService
from backend.group.voice import assign_windows, SCALAR_NAMES, training_feature
from backend.group.voice import build_profiles
from research.face_training import train_face_items
from tests.backend.test_group_workflow import MemoryStorage, auth, build_app, probe


def test_faces_are_numbered_from_the_right() -> None:
    numbered = number_faces(
        [
            {"x": 0.05, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [0.0]},
            {"x": 0.72, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [1.0]},
            {"x": 0.40, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [0.5]},
        ]
    )
    assert [face["slot_number"] for face in numbered] == [1, 2, 3]
    assert numbered[0]["x"] == 0.72
    image = np.full((32, 32, 3), 30, dtype=np.uint8)
    assert len(face_feature(image, (0.1, 0.1, 0.4, 0.4))) == 80


def test_spreadsheet_uses_marked_participant_numbers() -> None:
    text = "participant,class,A,B,T\n1,10-A,0,2,N/O\nParticipant 2,9-B,1,NO,4\n"
    rows = parse_label_csv(text.encode())
    assert rows[0]["class_name"] == "10-A"
    assert rows[0]["scores"] == {"A": "0", "B": "2", "T": "N/O"}
    assert rows[1]["slot_number"] == 2
    assert rows[1]["class_name"] == "9-B"
    assert rows[1]["scores"]["B"] == "N/O"


def test_upload_marks_faces_and_stores_the_spreadsheet() -> None:
    def marker(_data: bytes) -> dict:
        return {
            "jpeg": b"\xff\xd8marked",
            "time_s": 0,
            "faces": [
                {"x": 0.08, "y": 0.35, "width": 0.16, "height": 0.22, "feature": [0.1] * 80},
                {"x": 0.70, "y": 0.35, "width": 0.16, "height": 0.22, "feature": [0.9] * 80},
            ],
        }

    service = GroupObservationService(MemoryGroupStore(), MemoryStorage(), probe=probe, face_marker=marker)
    _operator, token = service.provision_account(label="Operator", role="operator", account_code="OP-FACE")
    client = build_app(service).test_client()
    uploaded = client.post(
        "/api/v1/group-sessions/from-video",
        data={"file": (io.BytesIO(b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"), "WhatsApp Video 2026-09-23 at 11.35.12 PM.mp4")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    body = uploaded.get_json()
    assert body["face_count"] == 2
    assert body["marked_frame_base64"]
    session_id = body["group_session"]["session"]["id"]
    seats = body["group_session"]["seats"]
    assert seats[0]["slot_number"] == 1
    assert seats[0]["center_x"] > seats[1]["center_x"]
    assert body["group_session"]["session"]["session_code"] == "WhatsApp-Video-2026-09-23-at-11.35.12-PM"
    sheet = "participant,class,A,T\n1,10-A,3,1\n2,9-B,0,4\n".encode()
    stored = client.post(
        f"/api/v1/group-sessions/{session_id}/labels",
        data={"file": (io.BytesIO(sheet), "session.csv")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert stored.status_code == 200
    assert stored.get_json()["participants"] == [1, 2]
    assert stored.get_json()["classes"] == {"1": "10-A", "2": "9-B"}
    service.store.replace_voice_analysis(session_id, [
        {"id": "assigned", "slot_number": 1, "start_s": 1.0, "end_s": 5.0,
         "confidence": 0.8, "overlap_refused_s": 0.0, "status": "assigned"},
        {"id": "unknown", "slot_number": None, "start_s": 6.0, "end_s": 8.0,
         "confidence": 0.0, "overlap_refused_s": 0.0, "status": "unknown"},
    ], [
        {"id": "voice-1", "slot_number": 1, "status": "ready", "engine": "numpy_spectral_v1",
         "embedding_engine": None, "embedding": None, "usable_seconds": 4.0,
         "vector": [0.2] * 32, "metrics": {"speaking_duration_s": 4.0, "turn_count": 1,
         "overlap_refused_s": 0.0, "pause_total_s": 0.0, "word_rate_wpm": None,
         "pitch_jitter_relative": None}},
        {"id": "voice-2", "slot_number": 2, "status": "insufficient_speech", "engine": None,
         "embedding_engine": None, "embedding": None, "usable_seconds": 0.0,
         "vector": None, "metrics": {}},
    ])
    details = client.get(f"/api/v1/group-sessions/{session_id}/face-voices", headers=auth(token))
    assert details.status_code == 200
    people = details.get_json()["people"]
    assert [person["slot_number"] for person in people] == [1, 2]
    assert people[0]["voice"]["status"] == "ready"
    assert people[0]["combined_feature_ready"] is True
    assert people[0]["marksheet"]["scores"]["A"] == "3"
    assert people[0]["segments"][0]["confidence"] == 0.8
    assert people[1]["voice"]["status"] == "insufficient_speech"
    assert people[1]["combined_feature_ready"] is False
    assert people[1]["segments"] == []
    assert len(details.get_json()["unknown_segments"]) == 1
    missing = client.post(
        f"/api/v1/group-sessions/{session_id}/labels",
        data={"file": (io.BytesIO(b"participant,A\n9,1\n"), "bad.csv")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert missing.status_code == 400
    page = client.get("/group")
    assert b"Submit recording" in page.data
    assert b"Submit spreadsheet" in page.data
    assert b'id="intake-video"' in page.data
    assert b'id="screen-mark" class="intake-screen" hidden' in page.data
    assert b'id="face-voice-list"' in page.data


def test_image_training_stays_unavailable_until_enough_sessions_exist() -> None:
    one = train_face_items(
        [
            {
                "group_session_id": "s1",
                "slot_number": 1,
                "item_letter": "T",
                "score": "2",
                "feature": [0.2] * 80,
            }
        ]
    )
    assert one["items"][0]["status"] == "unavailable"
    assert one["validated_psychological_result"] is False
    examples = []
    for session in range(5):
        examples.append(
            {
                "group_session_id": f"s{session}",
                "slot_number": 1,
                "item_letter": "T",
                "score": "1",
                "feature": [float(session), 0.1] + [0.0] * 78,
            }
        )
        examples.append(
            {
                "group_session_id": f"s{session}",
                "slot_number": 2,
                "item_letter": "T",
                "score": "3",
                "feature": [float(session), 0.9] + [0.0] * 78,
            }
        )
    fitted = train_face_items(examples, seed=42)
    item = fitted["items"][0]
    assert item["status"] == "fitted"
    assert item["test_metrics"]["test_examples"] > 0


def test_mouth_motion_assigns_the_right_hand_face_and_abstains_on_tie() -> None:
    boxes = [
        {"slot_number": 1, "x": 0.6, "y": 0.2, "width": 0.2, "height": 0.4},
        {"slot_number": 2, "x": 0.1, "y": 0.2, "width": 0.2, "height": 0.4},
    ]
    turn = [{"start_s": 0.0, "end_s": 4.0, "cluster_label": "cluster-7", "overlap": False}]

    def frames(*, both: bool) -> list[np.ndarray]:
        result = []
        for index in range(5):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[45:55, 60:80] = index % 2 * 60
            if both:
                frame[45:55, 10:30] = index % 2 * 60
            result.append(frame)
        return result

    assigned = assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: frames(both=False), face_checker=lambda *_: True)
    assert assigned[0]["slot_number"] == 1
    assert assigned[0]["status"] == "assigned"
    tied = assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: frames(both=True), face_checker=lambda *_: True)
    assert tied[0]["slot_number"] is None
    assert tied[0]["status"] == "unknown"
    overlapping = assign_windows(
        [turn[0], {"start_s": 2.0, "end_s": 3.0, "cluster_label": "cluster-8", "overlap": False}],
        boxes, b"video", frame_sampler=lambda *_: frames(both=False), face_checker=lambda *_: True,
    )
    assert all(row["status"] == "unknown" for row in overlapping)
    assert overlapping[0]["overlap_refused_s"] == 1.0
    moving_heads = []
    for index in range(5):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[24:56, 60:80] = index % 2 * 60
        moving_heads.append(frame)
    assert assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: moving_heads,
                          face_checker=lambda *_: True)[0]["status"] == "unknown"
    assert assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: frames(both=False),
                          face_checker=lambda *_: False)[0]["status"] == "unknown"
    partly_visible = frames(both=False)
    partly_visible[0][0, 0] = 1
    partly_visible[-1][0, 0] = 1
    assert assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: partly_visible,
                          face_checker=lambda frame, _box: bool(frame[0, 0, 0]))[0]["status"] == "assigned"
    two_moving = frames(both=True)
    for frame in two_moving:
        frame[:, :50] //= 3
    assert assign_windows(turn, boxes, b"video", frame_sampler=lambda *_: two_moving,
                          face_checker=lambda *_: True)[0]["status"] == "unknown"


def test_energy_segments_do_not_disappear_after_one_loud_peak() -> None:
    rate = 16000
    tone = (np.sin(np.arange(rate * 2) * 2 * np.pi * 220 / rate) * 700).astype(np.int16)
    loud = (np.sin(np.arange(rate // 3) * 2 * np.pi * 220 / rate) * 15000).astype(np.int16)
    audio = np.concatenate([tone, np.zeros(rate, dtype=np.int16), loud, tone])
    turns = _energy_segments(audio, rate)
    assert any(row["start_s"] < 0.1 and row["end_s"] > 1.9 for row in turns)
    assert any(row["start_s"] > 2.9 and row["end_s"] > 5.1 for row in turns)


def test_training_requires_ready_voice_for_the_same_session_and_slot() -> None:
    store = MemoryGroupStore()
    service = GroupObservationService(store, MemoryStorage(), probe=probe)
    service.provision_account(label="Operator", role="operator", account_code="OP-VOICE")
    actor = service.local_principal()
    for index in range(5):
        session = f"s{index}"
        store.insert_recording({"group_session_id": session, "processing_state": "complete",
                                "processing": {"voice_matching": {"status": "complete"}}})
        faces = [{"group_session_id": session, "slot_number": slot,
                  "feature": [float(index), float(slot)] + [0.0] * 78} for slot in (1, 2)]
        store.replace_face_samples(session, faces)
        store.replace_training_labels(session, [
            {"group_session_id": session, "slot_number": slot, "item_letter": "T", "score": str(slot)}
            for slot in (1, 2)
        ])
        store.replace_voice_profiles(session, [
            {"group_session_id": session, "slot_number": 1, "status": "ready", "vector": [0.1] * 32,
             "metrics": {name: 1.0 for name in SCALAR_NAMES}},
            {"group_session_id": session, "slot_number": 2, "status": "insufficient_speech", "vector": None,
             "metrics": {}},
        ])
    first = service.train_faces(actor)
    assert first["examples"] == 5
    assert first["ready_voices"] == first["trainable_voices"] == 5
    assert first["items"][0]["status"] == "unavailable"
    for index in range(5):
        session = f"s{index}"
        store.replace_voice_profiles(session, [
            {"group_session_id": session, "slot_number": slot, "status": "ready", "vector": [float(slot)] * 32,
             "metrics": {name: float(slot) for name in SCALAR_NAMES}} for slot in (1, 2)
        ])
    fitted = service.train_faces(actor)
    assert fitted["feature"] == "face_and_voice_v2"
    assert fitted["examples"] == 10
    assert fitted["trainable_voices"] == 10
    assert fitted["items"][0]["status"] == "fitted"
    store.update_recording("s0", processing_state="running")
    assert service.train_faces(actor)["examples"] == 8


def test_profile_uses_only_assigned_pcm_and_falls_back_without_token(monkeypatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr("backend.group.voice._embedding_available", lambda: False)
    monkeypatch.setattr("backend.group.voice.analyze_vocal_jitter_regions", lambda *_: {"status": "unavailable"})
    clean = (1500 * np.sin(2 * np.pi * 160 * np.arange(4 * 16000) / 16000)).astype(np.int16)
    samples = np.concatenate([clean, np.full(4 * 16000, -1000, dtype=np.int16)])
    segments = [
        {"slot_number": 1, "start_s": 0.0, "end_s": 4.0, "status": "assigned", "cluster_label": "cluster-A"},
        {"slot_number": None, "start_s": 4.0, "end_s": 8.0, "status": "unknown", "cluster_label": "cluster-B"},
    ]
    profiles = build_profiles(samples, 16000, segments, [{"slot_number": 1}, {"slot_number": 2}], [])
    assert profiles[0]["status"] == "ready"
    assert profiles[0]["engine"] == "numpy_spectral_v1"
    assert profiles[0]["usable_seconds"] == 4.0
    assert len(profiles[0]["vector"]) == 32
    feature = training_feature([0.1] * 80, profiles[0])
    assert feature is not None
    assert feature[-4:] == [-1.0, 1.0, -1.0, 1.0]
    assert profiles[1]["status"] == "insufficient_speech"
    assert profiles[1]["metrics"] == {}
    outside = build_profiles(samples, 16000, segments, [{"slot_number": 1}],
                             [{"start_s": 4.0, "end_s": 5.0, "text": "outside words"}])[0]
    assert outside["metrics"]["word_rate_wpm"] is None

    class FakeEmbedder:
        engine_name = "test-embedder"

        def embed(self, audio: np.ndarray, rate: int) -> np.ndarray:
            assert rate == 16000
            assert len(audio) == 4 * rate
            np.testing.assert_array_equal(audio, clean)
            return np.ones(192, dtype=np.float32)

    embedded = build_profiles(samples, 16000, segments, [{"slot_number": 1}], [], embedder=FakeEmbedder())[0]
    assert embedded["engine"] == profiles[0]["engine"] == "numpy_spectral_v1"
    assert embedded["vector"] == profiles[0]["vector"]
    assert embedded["embedding_engine"] == "test-embedder"
    assert len(embedded["embedding"]) == 192

    spaced = np.zeros(24 * 16000, dtype=np.int16)
    for start in (0, 4, 20):
        spaced[start * 16000:(start + 3) * 16000] = clean[:3 * 16000]
    spaced_segments = [{"slot_number": 1, "start_s": float(start), "end_s": float(start + 3),
                        "status": "assigned"} for start in (0, 4, 20)]
    spaced_profile = build_profiles(spaced, 16000, spaced_segments, [{"slot_number": 1}], [])[0]
    assert spaced_profile["metrics"]["pause_total_s"] == 1.0


def test_worker_records_voice_matching_after_extraction(monkeypatch) -> None:
    samples = (1500 * np.sin(2 * np.pi * 160 * np.arange(4 * 16000) / 16000)).astype(np.int16)
    def extracted(_data: bytes, _recording: dict) -> dict:
        return {"pcm_samples": samples, "sample_rate_hz": 16000,
                "turns": [{"start_s": 0.0, "end_s": 4.0, "cluster_label": "speaker-X", "overlap": False}],
                "transcript": [], "failure_reasons": [], "quality_state": "usable", "tool_version": "test"}

    store = MemoryGroupStore()
    service = GroupObservationService(store, MemoryStorage(), probe=probe, extractor=extracted)
    actor = service.local_principal()
    session_id = service.create_session(actor, {"participant_count": 2})["session"]["id"]
    service.upload_recording(actor, session_id, "recording.mp4", b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom")
    store.replace_face_samples(session_id, [{"group_session_id": session_id, "slot_number": 1,
                                            "x": .6, "y": .2, "width": .2, "height": .4,
                                            "feature": [0.1] * 80}])
    frames = []
    for index in range(8):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[45:55, 60:80] = index % 2 * 60
        frames.append(frame)
    monkeypatch.setattr("backend.group.voice.sample_window_frames", lambda *_: frames)
    monkeypatch.setattr("backend.group.voice.face_visible", lambda *_: True)
    monkeypatch.setattr("backend.group.voice._embedding_available", lambda: False)
    monkeypatch.setattr("backend.group.voice.analyze_vocal_jitter_regions", lambda *_: {"status": "unavailable"})
    job = service.claim_job("test")
    service.run_job(job)
    assert store.voice_segments_for(session_id)[0]["slot_number"] == 1
    assert store.voice_profiles_for(session_id)[0]["status"] == "ready"
    processing = store.recording_for_session(session_id)["processing"]
    assert processing["voice_matching"]["ready_voices"] == 1
    assert "pcm_samples" not in processing
    profile = store.voice_profiles_for(session_id)[0]
    assert profile["metrics"]["turn_count"] == 1
    assert training_feature([.1] * 80, profile) is not None
    store.replace_training_labels(session_id, [
        {"group_session_id": session_id, "slot_number": 1, "item_letter": "A", "score": "1"},
    ])
    trained = service.train_faces(actor)
    assert trained["examples"] == 1
    assert trained["feature"] == "face_and_voice_v2"
    assert trained["items"][0]["status"] == "unavailable"  # existing five-session gate

    def fail(*_):
        raise RuntimeError("decoder failed")

    monkeypatch.setattr("backend.group.voice.sample_window_frames", fail)
    service.run_job(job)
    assert store.voice_profiles_for(session_id) == []
    assert store.voice_segments_for(session_id) == []
    assert store.recording_for_session(session_id)["processing_state"] == "failed"
    assert store.recording_for_session(session_id)["processing"]["voice_matching"]["status"] == "failed"
    assert store.jobs[0]["state"] == "failed"


def test_long_energy_turn_is_observed_in_full(monkeypatch) -> None:
    boxes = [{"slot_number": 1, "x": .6, "y": .2, "width": .2, "height": .4},
             {"slot_number": 2, "x": .1, "y": .2, "width": .2, "height": .4}]
    observed = []

    def sampler(_source, start, end):
        observed.append((start, end))
        frames = []
        for index in range(8):
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            x = 60 if start < 4 else 10
            frame[45:55, x:x + 20] = index % 2 * 60
            frames.append(frame)
        return frames

    rows = assign_windows([{"start_s": 0., "end_s": 8., "cluster_label": "segment-1"}], boxes, b"video",
                          frame_sampler=sampler, face_checker=lambda *_: True)
    assert observed == [(0., 2.), (2., 4.), (4., 6.), (6., 8.)]
    assert [row["slot_number"] for row in rows] == [1, 1, 2, 2]
    monkeypatch.setattr("backend.group.voice._embedding_available", lambda: False)
    monkeypatch.setattr("backend.group.voice.analyze_vocal_jitter_regions", lambda *_: {"status": "unavailable"})
    samples = (1000 * np.sin(2 * np.pi * 160 * np.arange(8 * 16000) / 16000)).astype(np.int16)
    profiles = build_profiles(samples, 16000, rows, boxes,
                              [{"start_s": 0., "end_s": 1., "text": "three test words"}])
    assert [row["usable_seconds"] for row in profiles] == [4., 4.]
    assert [row["metrics"]["turn_count"] for row in profiles] == [1, 1]
    assert profiles[0]["metrics"]["word_rate_wpm"] == 180.


def test_docker_copy_layout_can_import_the_worker(tmp_path) -> None:
    root = Path(__file__).resolve().parents[2]
    # Reproduce COPY contents so development-only files cannot hide a broken
    # runtime import. No Docker daemon, model downloads, or services are needed.
    for line in (root / "Dockerfile").read_text().splitlines():
        if not line.startswith("COPY "):
            continue
        _, source, destination = line.split()
        source_path, target = root / source, tmp_path / destination
        if source_path.is_dir():
            shutil.copytree(source_path, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "node_modules", ".pytest_cache"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys, site; sys.path.append(site.getusersitepackages()); sys.path.insert(0, sys.argv[1]); import backend.worker",
         str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("bad", [None, float("nan"), "broken"])
def test_bad_required_measure_abstains_without_crashing(bad) -> None:
    profile = {"status": "ready", "vector": [.1] * 32, "metrics": {name: 1. for name in SCALAR_NAMES}}
    profile["metrics"]["speaking_duration_s"] = bad
    assert training_feature([.1] * 80, profile) is None


def test_long_profile_bounds_model_inputs_and_handles_jitter_failure(monkeypatch) -> None:
    rate = 16000
    samples = (1000 * np.sin(2 * np.pi * 160 * np.arange(45 * rate) / rate)).astype(np.int16)
    seen = []

    class Embedder:
        engine_name = "fake"

        def embed(self, audio, sample_rate):
            seen.append(len(audio) / sample_rate)
            assert len(audio) <= 10 * sample_rate
            return np.ones(192)

    def jitter(_samples, _rate, intervals):
        assert intervals and all(1 <= end - start <= 10 for start, end in intervals)
        raise RuntimeError("optional praat failure")

    monkeypatch.setattr("backend.group.voice.analyze_vocal_jitter_regions", jitter)
    segment = {"slot_number": 1, "start_s": 0., "end_s": 45., "status": "assigned"}
    profile = build_profiles(samples, rate, [segment], [{"slot_number": 1}], [], embedder=Embedder())[0]
    assert seen and len(seen) <= 6
    assert profile["status"] == "ready"
    assert profile["metrics"]["jitter"]["status"] == "unavailable"
    assert training_feature([.1] * 80, profile) is not None


def test_silent_assigned_audio_does_not_become_a_ready_profile(monkeypatch) -> None:
    monkeypatch.setattr("backend.group.voice._embedding_available", lambda: False)
    profile = build_profiles(np.zeros(4 * 16000, dtype=np.int16), 16000,
                             [{"slot_number": 1, "start_s": 0., "end_s": 4., "status": "assigned"}],
                             [{"slot_number": 1}], [])[0]
    assert profile["status"] == "insufficient_speech"
    assert profile["metrics"] == {}
