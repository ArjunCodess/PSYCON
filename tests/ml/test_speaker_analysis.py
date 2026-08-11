from __future__ import annotations

import io
import json
import os
from pathlib import Path

import av
import numpy as np
import pytest
from scipy.io import wavfile

from demo.audio_web_app import create_app
from ml.src.speaker_analysis import (
    DiarizationResult,
    PyannoteDiarizer,
    SpeakerTurn,
    SpeechBrainEmbedder,
    VoiceProfile,
    VoiceProfileError,
    VoiceProfileStore,
    analyze_speakers,
    enroll_wearer,
)
from ml.src.transcription import (
    TranscriptSegment,
    TranscriptWord,
    TranscriptionResult,
    TranscriptionStatus,
)


SAMPLE_RATE = 16_000


class FakeDiarizer:
    @property
    def engine_name(self) -> str:
        return "fake-diarizer"

    def diarize(self, samples: np.ndarray, sample_rate_hz: int) -> DiarizationResult:
        regular = (
            SpeakerTurn(0.0, 2.0, "A"),
            SpeakerTurn(2.5, 4.0, "B"),
            SpeakerTurn(4.5, 6.0, "A"),
            SpeakerTurn(5.8, 7.0, "B"),
        )
        exclusive = (
            SpeakerTurn(0.0, 2.0, "A"),
            SpeakerTurn(2.5, 4.0, "B"),
            SpeakerTurn(4.5, 5.8, "A"),
            SpeakerTurn(5.8, 7.0, "B"),
        )
        return DiarizationResult(regular, exclusive, self.engine_name)


def test_pyannote_token_is_trimmed_and_blank_values_are_missing() -> None:
    assert PyannoteDiarizer(token="  hf_example  ").token == "hf_example"
    assert PyannoteDiarizer(token="   ").token is None


class SignEmbedder:
    @property
    def engine_name(self) -> str:
        return "fake-embedding"

    @property
    def verification_threshold(self) -> float:
        return 0.7

    def embed(self, samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        return np.array([1.0, 0.0]) if float(np.mean(samples)) >= 0 else np.array([0.0, 1.0])


class AmbiguousEmbedder(SignEmbedder):
    def embed(self, samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        return np.array([1.0, 0.0])


class AmbiguousDiarizer(FakeDiarizer):
    def diarize(self, samples: np.ndarray, sample_rate_hz: int) -> DiarizationResult:
        turns = (SpeakerTurn(0.0, 3.0, "A"), SpeakerTurn(3.5, 6.5, "B"))
        return DiarizationResult(turns, turns, self.engine_name)


class SingleSpeakerDiarizer(FakeDiarizer):
    def diarize(self, samples: np.ndarray, sample_rate_hz: int) -> DiarizationResult:
        turns = (SpeakerTurn(0.0, len(samples) / sample_rate_hz, "A"),)
        return DiarizationResult(turns, turns, self.engine_name)


def _conversation_samples() -> np.ndarray:
    samples = np.zeros(8 * SAMPLE_RATE, dtype=np.int16)
    samples[0 : 2 * SAMPLE_RATE] = 2000
    samples[round(2.5 * SAMPLE_RATE) : 4 * SAMPLE_RATE] = -2000
    samples[round(4.5 * SAMPLE_RATE) : round(5.8 * SAMPLE_RATE)] = 2000
    samples[round(5.8 * SAMPLE_RATE) : 7 * SAMPLE_RATE] = -2000
    return samples


def _transcription() -> TranscriptionResult:
    words = (
        TranscriptWord(0.2, 0.6, "hello", 0.9, 3200, 9600),
        TranscriptWord(2.7, 3.1, "there", 0.9, 43200, 49600),
        TranscriptWord(5.0, 5.4, "again", 0.9, 80000, 86400),
        TranscriptWord(7.4, 7.7, "outside", 0.9, 118400, 123200),
    )
    return TranscriptionResult(
        status=TranscriptionStatus.COMPLETE,
        text="hello there again outside",
        language="en",
        language_confidence=0.9,
        confidence=0.9,
        segments=(TranscriptSegment(0.2, 7.7, "hello there again outside", 0.9, 3200, 123200, words),),
        engine="fixture",
    )


def test_identifies_only_wearer_and_computes_speaker_timing() -> None:
    result = analyze_speakers(
        _conversation_samples(),
        SAMPLE_RATE,
        _transcription(),
        FakeDiarizer(),
        SignEmbedder(),
        VoiceProfile(np.array([1.0, 0.0]), "fixture", 3, 18.0),
    )
    assert result["status"] == "complete"
    assert result["participant_status"] == "identified"
    assert set(result["speakers"]) == {"participant", "speaker_02"}
    assert result["speakers"]["participant"]["word_count"] == 2
    assert result["speakers"]["speaker_02"]["word_count"] == 1
    assert result["attributed_words"][-1]["speaker_id"] == "unknown"
    assert result["conversation"]["response_gaps"]["count"] == 2
    assert result["conversation"]["overlap_duration_s"] == pytest.approx(0.2)
    assert result["conversation"]["interruption_count"] == 1
    assert '"embedding":' not in json.dumps(result)


def test_ambiguous_match_abstains_and_keeps_everyone_anonymous() -> None:
    result = analyze_speakers(
        _conversation_samples(),
        SAMPLE_RATE,
        _transcription(),
        AmbiguousDiarizer(),
        AmbiguousEmbedder(),
        VoiceProfile(np.array([1.0, 0.0]), "fixture", 3, 18.0),
    )
    assert result["participant_status"] == "ambiguous_match"
    assert "participant" not in result["speakers"]
    assert set(result["speakers"]) == {"speaker_01", "speaker_02"}


def test_missing_profile_abstains_without_blocking_anonymous_metrics() -> None:
    result = analyze_speakers(
        _conversation_samples(), SAMPLE_RATE, _transcription(), FakeDiarizer(), SignEmbedder(), None
    )
    assert result["status"] == "complete"
    assert result["participant_status"] == "not_enrolled"
    assert len(result["speakers"]) == 2


def test_praat_jitter_distinguishes_stable_and_modulated_pitch() -> None:
    time = np.arange(3 * SAMPLE_RATE) / SAMPLE_RATE
    stable = (0.15 * np.sin(2 * np.pi * 180 * time) * 32767).astype(np.int16)
    instantaneous_frequency = 180 + 14 * np.sin(2 * np.pi * 5 * time)
    phase = 2 * np.pi * np.cumsum(instantaneous_frequency) / SAMPLE_RATE
    modulated = (0.15 * np.sin(phase) * 32767).astype(np.int16)
    empty_transcript = TranscriptionResult(
        TranscriptionStatus.NO_SPEECH, "", None, 0.0, 0.0, (), "fixture"
    )
    stable_result = analyze_speakers(
        stable, SAMPLE_RATE, empty_transcript, SingleSpeakerDiarizer(), SignEmbedder(), None
    )
    modulated_result = analyze_speakers(
        modulated, SAMPLE_RATE, empty_transcript, SingleSpeakerDiarizer(), SignEmbedder(), None
    )
    stable_jitter = stable_result["speakers"]["speaker_01"]["jitter"]
    modulated_jitter = modulated_result["speakers"]["speaker_01"]["jitter"]
    assert stable_jitter["status"] == "complete"
    assert modulated_jitter["status"] == "complete"
    assert modulated_jitter["local_relative"] > stable_jitter["local_relative"]
    assert modulated_jitter["ddp"] == pytest.approx(3 * modulated_jitter["rap"])


def test_enrollment_is_encrypted_and_raw_audio_is_not_stored(tmp_path) -> None:
    path = tmp_path / "wearer.enc"
    store = VoiceProfileStore(path, "a sufficiently long test-only encryption secret")
    clip = np.full(6 * SAMPLE_RATE, 2000, dtype=np.int16)
    profile = enroll_wearer([(clip, SAMPLE_RATE)] * 3, SignEmbedder(), store)
    stored = path.read_bytes()
    assert b"embedding" not in stored
    assert np.array_equal(store.load().embedding, profile.embedding)
    assert store.delete() is True
    assert not path.exists()


def test_enrollment_requires_three_quality_checked_clips(tmp_path) -> None:
    store = VoiceProfileStore(tmp_path / "wearer.enc", "a sufficiently long test-only encryption secret")
    clip = np.full(6 * SAMPLE_RATE, 2000, dtype=np.int16)
    with pytest.raises(ValueError, match="exactly three"):
        enroll_wearer([(clip, SAMPLE_RATE)] * 2, SignEmbedder(), store)
    with pytest.raises(ValueError, match="5 to 10 seconds"):
        enroll_wearer([(clip[: SAMPLE_RATE], SAMPLE_RATE)] * 3, SignEmbedder(), store)


def test_profile_store_requires_a_long_encryption_secret(tmp_path) -> None:
    store = VoiceProfileStore(tmp_path / "wearer.enc", "short")
    profile = VoiceProfile(np.array([1.0, 0.0]), "fixture", 3, 18.0)
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        store.save(profile)


def test_profile_store_explains_an_encryption_key_change(tmp_path) -> None:
    path = tmp_path / "wearer.enc"
    profile = VoiceProfile(np.array([1.0, 0.0]), "fixture", 3, 18.0)
    VoiceProfileStore(path, "first sufficiently long test-only encryption secret").save(profile)
    changed = VoiceProfileStore(path, "other sufficiently long test-only encryption secret")
    with pytest.raises(VoiceProfileError, match="profile_key_changed_reenroll_wearer"):
        changed.load()


def _wav_bytes(samples: np.ndarray) -> bytes:
    output = io.BytesIO()
    wavfile.write(output, SAMPLE_RATE, samples)
    return output.getvalue()


def _mp3_bytes(samples: np.ndarray) -> bytes:
    output = io.BytesIO()
    with av.open(output, mode="w", format="mp3") as container:
        stream = container.add_stream("mp3", rate=SAMPLE_RATE)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return output.getvalue()


def test_demo_enrolls_and_deletes_profile(tmp_path) -> None:
    store = VoiceProfileStore(tmp_path / "wearer.enc", "a sufficiently long test-only encryption secret")
    client = create_app(testing=True, embedder=SignEmbedder(), profile_store=store).test_client()
    clip = np.full(6 * SAMPLE_RATE, 2000, dtype=np.int16)
    response = client.post(
        "/enroll",
        data={
            "enrollment_1": (io.BytesIO(_wav_bytes(clip)), "one.wav"),
            "enrollment_2": (io.BytesIO(_wav_bytes(clip)), "two.wav"),
            "enrollment_3": (io.BytesIO(_wav_bytes(clip)), "three.wav"),
            "enrollment_consent": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert store.exists
    response = client.post("/profile/delete")
    assert response.status_code == 302
    assert not store.exists


def test_demo_enrolls_from_mp3_samples(tmp_path) -> None:
    store = VoiceProfileStore(tmp_path / "wearer.enc", "a sufficiently long test-only encryption secret")
    client = create_app(testing=True, embedder=SignEmbedder(), profile_store=store).test_client()
    clip = np.full(6 * SAMPLE_RATE, 2000, dtype=np.int16)
    source = _mp3_bytes(clip)
    response = client.post(
        "/enroll",
        data={
            "enrollment_1": (io.BytesIO(source), "one.mp3"),
            "enrollment_2": (io.BytesIO(source), "two.mp3"),
            "enrollment_3": (io.BytesIO(source), "three.mp3"),
            "enrollment_consent": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert store.exists


def test_demo_renders_speaker_timing_without_real_models(tmp_path) -> None:
    store = VoiceProfileStore(tmp_path / "wearer.enc", "a sufficiently long test-only encryption secret")
    store.save(VoiceProfile(np.array([1.0, 0.0]), "fixture", 3, 18.0))
    client = create_app(
        testing=True,
        diarizer=FakeDiarizer(),
        embedder=SignEmbedder(),
        profile_store=store,
    ).test_client()
    time = np.arange(8 * SAMPLE_RATE) / SAMPLE_RATE
    recording = (0.15 * np.sin(2 * np.pi * 180 * time) * 32767).astype(np.int16)
    response = client.post(
        "/",
        data={
            "audio": (io.BytesIO(_wav_bytes(recording)), "conversation.wav"),
            "consent": "yes",
            "speakers": "yes",
            "biometric_consent": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"Who spoke and when" in response.data
    assert b"Response gaps" in response.data
    assert b"Articulation" in response.data


@pytest.mark.skipif(
    not os.getenv("HF_TOKEN")
    or not (os.getenv("PSYCON_REAL_SPEAKER_AUDIO") or os.getenv("PSYCON_REAL_SPEAKER_WAV")),
    reason="set HF_TOKEN and PSYCON_REAL_SPEAKER_AUDIO for the opt-in model integration",
)
def test_opt_in_real_diarization_and_embedding() -> None:
    from ml.src.audio_recording import decode_audio

    recording_path = os.getenv("PSYCON_REAL_SPEAKER_AUDIO") or os.environ["PSYCON_REAL_SPEAKER_WAV"]
    decoded = decode_audio(Path(recording_path).read_bytes())
    diarization = PyannoteDiarizer().diarize(decoded.samples, decoded.sample_rate_hz)
    assert diarization.exclusive_turns
    first = diarization.exclusive_turns[0]
    speech = decoded.samples[
        round(first.start_s * decoded.sample_rate_hz) : round(first.end_s * decoded.sample_rate_hz)
    ]
    if len(speech) / decoded.sample_rate_hz < 3:
        pytest.skip("the first diarized speaker turn is shorter than three seconds")
    embedding = SpeechBrainEmbedder().embed(speech, decoded.sample_rate_hz)
    assert embedding.ndim == 1
    assert np.linalg.norm(embedding) == pytest.approx(1.0, abs=1e-5)
