from __future__ import annotations

from types import SimpleNamespace
import io
import wave

import numpy as np
import pytest
import torch

from backend.group import nvidia
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupError, GroupObservationService
from backend.group.voice import assigned_audio_for_slot
from tests.backend.test_group_workflow import MemoryStorage


def test_streaming_cache_continues_across_chunks() -> None:
    class Inputs(dict):
        def to(self, *_args, **_kwargs):
            return self

    class Processor:
        num_samples_first_audio_chunk = 16000
        num_samples_per_audio_chunk = 16000
        num_mel_frames_per_step = 1

        def set_streaming_mode(self, mode):
            assert mode == "low_latency"

        def audio_chunk_start(self, index):
            return index * 16000

        def __call__(self, chunk, **kwargs):
            assert kwargs["sampling_rate"] == 16000
            return Inputs(length=len(chunk), last=kwargs.get("is_last_audio_chunk", False))

    class Model:
        device = "cpu"
        dtype = torch.float32

        def __init__(self):
            self.caches = []
            self.last_flags = []

        def __call__(self, *, length, last, speaker_cache):
            self.caches.append(speaker_cache)
            self.last_flags.append(last)
            value = -5.0 * torch.ones((1, length // 160, 8))
            value[:, :, 3] = 5.0
            return SimpleNamespace(logits=value, speaker_cache=len(self.caches))

    model = Model()
    probs = nvidia.streaming_logits(np.zeros(3 * 16000, dtype=np.int16), 16000,
                                    processor=Processor(), model=model)
    assert model.caches == [None, 1, 2, 3]
    assert model.last_flags == [False, False, False, True]
    assert probs.shape == (300, 8)
    assert all(row["cluster_label"] == "nemotron-speaker-3" for row in nvidia.activity_segments(probs))


def test_overlaps_and_anonymous_channels_never_become_face_numbers() -> None:
    probabilities = np.zeros((500, 8))
    probabilities[:400, 0] = 0.9
    probabilities[100:300, 1] = 0.9
    turns = nvidia.activity_segments(probabilities)
    rows = nvidia.clean_windows(turns, duration_s=5)
    assert any(row["evidence"]["reason"] == "overlapping_speakers" for row in rows)
    assert all(row["slot_number"] is None for row in rows)
    assert nvidia.map_speakers(rows, [], {1, 2}) == {}
    assert all(row["status"] == "unknown" for row in rows)


def test_boundary_scraps_do_not_enter_usable_audio() -> None:
    rows = nvidia.clean_windows([{"cluster_label": "nemotron-speaker-0",
                                  "start_s": 1.0, "end_s": 1.55}], duration_s=2)
    assert rows == []


def test_short_speech_turns_receive_visual_review_windows() -> None:
    rows = [
        {"id": "short", "cluster_label": "nemotron-speaker-0", "start_s": 1.0, "end_s": 1.65, "overlap_refused_s": 0},
        {"id": "long", "cluster_label": "nemotron-speaker-0", "start_s": 4.0, "end_s": 11.0, "overlap_refused_s": 0},
        {"cluster_label": None, "start_s": 12.0, "end_s": 13.0, "overlap_refused_s": 1.0},
    ]
    assert nvidia._visual_windows(rows) == [
        ("nemotron-speaker-0", 1.0, 1.65, "short"),
        ("nemotron-speaker-0", 4.0, 6.0, "long"),
        ("nemotron-speaker-0", 6.5, 8.5, "long"),
        ("nemotron-speaker-0", 9.0, 11.0, "long"),
    ]


def test_repeated_evidence_propagates_but_conflicts_abstain() -> None:
    turns = [{"cluster_label": "nemotron-speaker-0", "start_s": start, "end_s": start + 2}
             for start in (0, 4, 8, 12)]
    rows = nvidia.clean_windows(turns, duration_s=14)
    support = [{"cluster_label": "nemotron-speaker-0", "slot_number": 7, "start_s": start,
                "end_s": start + 1, "reliable": True} for start in (0, 4, 8)]
    mapping = nvidia.map_speakers(rows, support, {7})
    assert mapping == {"nemotron-speaker-0": 7}
    assert all(row["slot_number"] == 7 for row in rows)
    assert all(row["evidence"]["reason"] == "speaker_identity_propagated" for row in rows)
    conflict = [{**support[0], "slot_number": 6, "start_s": 12, "end_s": 12.2}]
    rows = nvidia.clean_windows(turns, duration_s=14)
    nvidia.map_speakers(rows, support + conflict, {6, 7})
    assert rows[-1]["status"] == "unknown"
    assert rows[-1]["evidence"]["reason"] == "local_identity_conflict"


def test_local_evidence_recovers_a_turn_without_relabeling_conflicting_channels() -> None:
    rows = nvidia.clean_windows([
        {"cluster_label": "nemotron-speaker-3", "start_s": 0, "end_s": 7},
        {"cluster_label": "nemotron-speaker-6", "start_s": 10, "end_s": 17},
        {"cluster_label": "nemotron-speaker-6", "start_s": 20, "end_s": 27},
    ], duration_s=27)
    observations = []
    for row in rows:
        for start in (row["start_s"], row["end_s"] - 2):
            observations.append({"cluster_label": row["cluster_label"], "source_segment_id": row["id"],
                                 "slot_number": 3, "start_s": start, "end_s": start + 2,
                                 "score": .9, "reliable": True})
    for start in (30, 34):
        observations.append({"cluster_label": "nemotron-speaker-6", "source_segment_id": f"elsewhere:{start}",
                             "slot_number": 4, "start_s": start, "end_s": start + 2,
                             "score": .9, "reliable": True})
    assert nvidia.map_speakers(rows, observations, {3, 4}) == {}
    assert rows[0]["status"] == "unknown"
    assert [row["status"] for row in rows[1:]] == ["assigned", "assigned"]
    assert rows[1]["evidence"]["reason"] == "local_repeated_visual_evidence"


def test_one_visual_vote_cannot_make_a_short_unknown_voice_training_ready() -> None:
    rows = nvidia.clean_windows([{"cluster_label": "nemotron-speaker-7",
                                  "start_s": 1, "end_s": 2}], duration_s=2)
    nvidia.map_speakers(rows, [{"cluster_label": "nemotron-speaker-7", "source_segment_id": rows[0]["id"],
                                "slot_number": 4, "start_s": 1.15, "end_s": 1.85,
                                "score": .99, "reliable": True}], {4})
    assert rows[0]["status"] == "unknown"


def test_method_storage_and_playback_intervals_stay_independent() -> None:
    store = MemoryGroupStore()
    rows = nvidia.clean_windows([
        {"cluster_label": "nemotron-speaker-0", "start_s": 0., "end_s": 4.},
        {"cluster_label": "nemotron-speaker-1", "start_s": 1., "end_s": 2.},
    ], duration_s=4)
    nvidia.map_speakers(rows, [
        {"cluster_label": "nemotron-speaker-0", "slot_number": 1, "start_s": t,
         "end_s": t + .5, "reliable": True} for t in (0, .5, 2)
    ], {1})
    store.replace_voice_analysis("session", [{"id": "old"}], [{"status": "ready"}])
    store.replace_voice_analysis("session", rows, [], "nvidia")
    assert store.voice_segments_for("session") == [{"id": "old"}]
    samples = np.arange(4 * 16000, dtype=np.int16)
    audio, intervals = assigned_audio_for_slot(samples, 16000, store.voice_segments_for("session", "nvidia"), 1)
    assert intervals == [(0.15, 0.85), (2.15, 3.85)]
    expected = np.concatenate([samples[2400:13600], samples[34400:61600]])
    np.testing.assert_array_equal(audio, expected)


def test_invalid_pcm_and_capacity_are_explicit() -> None:
    with pytest.raises(ValueError, match="16khz"):
        nvidia.streaming_logits(np.zeros(10, dtype=np.int16), 8000)
    with pytest.raises(ValueError, match="eight_speaker"):
        nvidia.activity_segments(np.zeros((10, 4)))


def test_nvidia_failure_clears_old_nvidia_profiles_without_touching_existing(monkeypatch) -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage)
    actor = service.local_principal()
    session_id = "session"
    pcm = io.BytesIO()
    with wave.open(pcm, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    storage.put_immutable("pcm", pcm.getvalue(), "audio/wav")
    store.insert_recording({"group_session_id": session_id, "audio_object_key": "pcm",
                            "processing": {"voice_matching": {"status": "complete"}}})
    store.replace_face_samples(session_id, [{"slot_number": 1}])
    store.replace_voice_analysis(session_id, [{"id": "existing"}], [{"status": "ready"}])
    store.replace_voice_analysis(session_id, [], [{"status": "ready"}], "nvidia")
    monkeypatch.setattr(nvidia, "streaming_logits", lambda *_: (_ for _ in ()).throw(RuntimeError("gpu_failed")))
    job = service.enqueue_nvidia(actor, session_id)["job"]
    service.run_job(job)
    assert store.voice_segments_for(session_id) == [{"id": "existing"}]
    assert store.voice_profiles_for(session_id) == [{"status": "ready"}]
    assert store.voice_profiles_for(session_id, "nvidia") == []
    assert store.recording_for_session(session_id)["processing"]["nvidia_matching"]["reason"] == "RuntimeError:gpu_failed"


def test_reviewed_short_interval_is_playable_but_not_training_ready() -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage)
    actor = service.local_principal()
    session_id = "session"
    pcm = io.BytesIO()
    with wave.open(pcm, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        tone = (1200 * np.sin(2 * np.pi * 220 * np.arange(4 * 16000) / 16000)).astype(np.int16)
        handle.writeframes(tone.tobytes())
    storage.put_immutable("pcm", pcm.getvalue(), "audio/wav")
    store.insert_recording({"group_session_id": session_id, "audio_object_key": "pcm",
                            "processing": {"nvidia_matching": {"status": "complete",
                                         "version": nvidia.MATCHING_VERSION,
                                         "model_revision": nvidia.MODEL_REVISION}}})
    store.replace_face_samples(session_id, [{"slot_number": 4}])
    store.insert_participant({"id": "person-4", "group_session_id": session_id,
                              "slot_number": 4, "withdrawn_at": None})
    rows = nvidia.clean_windows([
        {"cluster_label": "nemotron-speaker-7", "start_s": .2, "end_s": 2.8},
        {"cluster_label": "nemotron-speaker-6", "start_s": 1.3, "end_s": 1.5},
    ], duration_s=4)
    clean = next(row for row in rows if row["cluster_label"] == "nemotron-speaker-7")
    overlap = next(row for row in rows if row["overlap_refused_s"])
    store.replace_voice_analysis(session_id, rows, [], "nvidia")
    with pytest.raises(GroupError, match="non-overlapping"):
        service.review_nvidia_interval(actor, session_id,
                                       {"segment_id": overlap["id"], "slot_number": 4, "note": "visible"})
    service.review_nvidia_interval(actor, session_id,
                                   {"segment_id": clean["id"], "slot_number": 4,
                                    "note": "Compared the original video and audio at 1 second"})
    reviewed = next(row for row in store.voice_segments_for(session_id, "nvidia") if row["id"] == clean["id"])
    assert reviewed["slot_number"] == 4
    assert reviewed["evidence"]["reason"] == "operator_confirmed_from_original_video"
    profile = store.voice_profiles_for(session_id, "nvidia")[0]
    assert 0 < profile["usable_seconds"] < 3
    assert profile["status"] == "insufficient_speech"
    with pytest.raises(GroupError, match="non-overlapping"):
        service.review_nvidia_interval(actor, session_id,
                                       {"segment_id": clean["id"], "slot_number": 4, "note": "repeat"})


def test_two_reviewed_turns_propagate_only_without_visual_conflict() -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage)
    actor = service.local_principal()
    session_id = "review-session"
    pcm = io.BytesIO()
    with wave.open(pcm, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        tone = (1200 * np.sin(2 * np.pi * 220 * np.arange(16 * 16000) / 16000)).astype(np.int16)
        handle.writeframes(tone.tobytes())
    storage.put_immutable("pcm-review", pcm.getvalue(), "audio/wav")
    store.insert_recording({"group_session_id": session_id, "audio_object_key": "pcm-review",
                            "processing": {"nvidia_matching": {"status": "complete",
                                         "version": nvidia.MATCHING_VERSION,
                                         "model_revision": nvidia.MODEL_REVISION}}})
    store.replace_face_samples(session_id, [{"slot_number": 4}])
    store.insert_participant({"id": "person-4", "group_session_id": session_id,
                              "slot_number": 4, "withdrawn_at": None})
    rows = [dict(id=str(index), start_s=start, end_s=end, cluster_label="nemotron-speaker-0",
                 slot_number=None, status="unknown", confidence=0.0, overlap_refused_s=0.0,
                 evidence={"reason": "speaker_unmapped", **evidence})
            for index, (start, end, evidence) in enumerate([
                (1.0, 2.0, {}), (8.0, 9.0, {}), (10.0, 11.0, {}),
                (12.0, 13.0, {"visual_observations": [{"candidate_slot": 2}]})])]
    store.replace_voice_analysis(session_id, rows, [], "nvidia")
    for index in (0, 1):
        service.review_nvidia_interval(actor, session_id,
                                       {"segment_id": str(index), "slot_number": 4,
                                        "note": "Verified speaker in original video"})
    saved = store.voice_segments_for(session_id, "nvidia")
    assert saved[2]["status"] == "assigned"
    assert saved[2]["evidence"]["reason"] == "operator_confirmed_speaker_identity_propagated"
    assert saved[3]["status"] == "unknown"
