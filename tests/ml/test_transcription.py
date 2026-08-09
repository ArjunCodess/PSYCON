from __future__ import annotations

import numpy as np
import pytest

from ml.src.language_features import LanguageFeatureStatus, extract_language_features
from ml.src.transcription import (
    FasterWhisperTranscriber,
    TranscriptSegment,
    TranscriptionResult,
    TranscriptionStatus,
    transcribe_usable_regions,
)


SAMPLE_RATE = 16_000


def test_local_transcriber_defaults_to_multilingual_small_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PSYCON_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("PSYCON_WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("PSYCON_WHISPER_COMPUTE_TYPE", raising=False)
    transcriber = FasterWhisperTranscriber()
    assert transcriber.engine_name == "faster-whisper/small/cpu-int8"


def test_server_transcriber_accepts_turbo_gpu_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSYCON_WHISPER_MODEL", "turbo")
    monkeypatch.setenv("PSYCON_WHISPER_DEVICE", "cuda")
    monkeypatch.delenv("PSYCON_WHISPER_COMPUTE_TYPE", raising=False)
    transcriber = FasterWhisperTranscriber()
    assert transcriber.engine_name == "faster-whisper/turbo/cuda-float16"


class FakeTranscriber:
    def __init__(self, *, language: str = "en") -> None:
        self.language = language
        self.calls = 0

    @property
    def engine_name(self) -> str:
        return "fake-transcriber"

    def transcribe(self, samples: np.ndarray, sample_rate_hz: int) -> TranscriptionResult:
        self.calls += 1
        text = (
            "I feel calm and happy today."
            if self.calls == 1
            else "Work feels stressful and difficult now."
        )
        return TranscriptionResult(
            status=TranscriptionStatus.COMPLETE,
            text=text,
            language=self.language,
            language_confidence=0.96,
            confidence=0.88,
            segments=(
                TranscriptSegment(
                    start_s=0.25,
                    end_s=1.75,
                    text=text,
                    confidence=0.88,
                    source_start_sample=4_000,
                    source_end_sample=28_000,
                ),
            ),
            engine=self.engine_name,
        )


class StatusTranscriber:
    def __init__(self, status: TranscriptionStatus) -> None:
        self.status = status

    @property
    def engine_name(self) -> str:
        return "status-transcriber"

    def transcribe(self, samples: np.ndarray, sample_rate_hz: int) -> TranscriptionResult:
        return TranscriptionResult(
            status=self.status,
            text="",
            language=None,
            language_confidence=0.0,
            confidence=0.0,
            segments=(),
            engine=self.engine_name,
            reasons=(f"fixture_{self.status.value}",),
        )
def _quality_window(number: int, start_s: float, end_s: float, status: str) -> dict[str, object]:
    return {"number": number, "start_s": start_s, "end_s": end_s, "status": status}


def test_transcribes_only_contiguous_usable_regions_with_source_offsets() -> None:
    transcriber = FakeTranscriber()
    samples = np.zeros(6 * SAMPLE_RATE, dtype=np.int16)
    windows = [
        _quality_window(1, 0.0, 2.0, "usable"),
        _quality_window(2, 2.0, 4.0, "clipped"),
        _quality_window(3, 4.0, 6.0, "usable"),
    ]
    result = transcribe_usable_regions(samples, SAMPLE_RATE, windows, transcriber)
    assert result.status is TranscriptionStatus.COMPLETE
    assert transcriber.calls == 2
    assert len(result.segments) == 2
    assert result.segments[0].start_s == pytest.approx(0.25)
    assert result.segments[1].start_s == pytest.approx(4.25)
    assert result.segments[1].source_start_sample == 4 * SAMPLE_RATE + 4_000
    assert "calm" in result.text and "stressful" in result.text


def test_quality_gate_skips_transcription_when_no_window_is_usable() -> None:
    transcriber = FakeTranscriber()
    result = transcribe_usable_regions(
        np.zeros(2 * SAMPLE_RATE, dtype=np.int16),
        SAMPLE_RATE,
        [_quality_window(1, 0.0, 2.0, "too_noisy")],
        transcriber,
    )
    assert result.status is TranscriptionStatus.SKIPPED_QUALITY
    assert transcriber.calls == 0


@pytest.mark.parametrize(
    "status",
    [TranscriptionStatus.NO_SPEECH, TranscriptionStatus.FAILED],
)
def test_no_speech_and_failed_transcription_never_produce_language_features(
    status: TranscriptionStatus,
) -> None:
    transcription = transcribe_usable_regions(
        np.zeros(2 * SAMPLE_RATE, dtype=np.int16),
        SAMPLE_RATE,
        [_quality_window(1, 0.0, 2.0, "usable")],
        StatusTranscriber(status),
    )
    assert transcription.status is status
    features = extract_language_features(transcription)
    assert features["status"] == LanguageFeatureStatus.TRANSCRIPTION_UNAVAILABLE.value


def test_extracts_prd_language_and_conversation_features() -> None:
    transcription = TranscriptionResult(
        status=TranscriptionStatus.COMPLETE,
        text="I feel calm and happy today. Work feels stressful and difficult now.",
        language="en",
        language_confidence=0.99,
        confidence=0.9,
        segments=(
            TranscriptSegment(0.0, 2.0, "I feel calm and happy today.", 0.9, 0, 32_000),
            TranscriptSegment(3.0, 5.0, "Work feels stressful and difficult now.", 0.9, 48_000, 80_000),
        ),
        engine="fixture",
    )
    features = extract_language_features(transcription)
    assert features["status"] == LanguageFeatureStatus.COMPLETE.value
    assert features["word_count"] == 12
    assert features["sentence_count"] == 2
    assert features["emotion_word_counts"]["positive"] == 2
    assert features["topic_transition_count"] == 1
    assert features["pause_duration_s"] == pytest.approx(1.0)
    assert features["speaker_diarization_available"] is False


def test_language_features_abstain_for_unsupported_language() -> None:
    transcription = FakeTranscriber(language="hi").transcribe(
        np.zeros(SAMPLE_RATE, dtype=np.int16), SAMPLE_RATE
    )
    result = extract_language_features(transcription)
    assert result["status"] == LanguageFeatureStatus.UNSUPPORTED_LANGUAGE.value
    assert result["reasons"] == ["language_hi_not_supported_by_english_lexicons"]


def test_language_features_abstain_when_language_is_unknown() -> None:
    transcription = FakeTranscriber(language="en").transcribe(
        np.zeros(SAMPLE_RATE, dtype=np.int16), SAMPLE_RATE
    )
    transcription = TranscriptionResult(
        status=transcription.status,
        text=transcription.text,
        language=None,
        language_confidence=0.0,
        confidence=transcription.confidence,
        segments=transcription.segments,
        engine=transcription.engine,
    )
    result = extract_language_features(transcription)
    assert result["status"] == LanguageFeatureStatus.UNSUPPORTED_LANGUAGE.value
    assert result["reasons"] == ["language_unknown_not_supported_by_english_lexicons"]
