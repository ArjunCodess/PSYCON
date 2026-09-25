from __future__ import annotations

from types import SimpleNamespace
import io
import wave

import numpy as np
import pytest
import torch

from backend.group import nvidia
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupObservationService
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
