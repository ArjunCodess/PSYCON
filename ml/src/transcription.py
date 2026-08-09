"""Quality-gated, local speech transcription with timestamp provenance."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import numpy as np


TRANSCRIPTION_PIPELINE = "psycon_transcription"


class TranscriptionStatus(str, Enum):
    COMPLETE = "complete"
    NO_SPEECH = "no_speech"
    SKIPPED_QUALITY = "skipped_quality"
    NOT_REQUESTED = "not_requested"
    UNAVAILABLE = "transcription_unavailable"
    FAILED = "failed_transcription"


@dataclass(frozen=True)
class TranscriptSegment:
    start_s: float
    end_s: float
    text: str
    confidence: float
    source_start_sample: int
    source_end_sample: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "text": self.text,
            "confidence": self.confidence,
            "source_start_sample": self.source_start_sample,
            "source_end_sample": self.source_end_sample,
        }


@dataclass(frozen=True)
class TranscriptionResult:
    status: TranscriptionStatus
    text: str
    language: str | None
    language_confidence: float
    confidence: float
    segments: tuple[TranscriptSegment, ...]
    engine: str
    reasons: tuple[str, ...] = ()
    pipeline: str = TRANSCRIPTION_PIPELINE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "pipeline": self.pipeline,
            "text": self.text,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "confidence": self.confidence,
            "segments": [segment.to_dict() for segment in self.segments],
            "engine": self.engine,
            "reasons": list(self.reasons),
        }


class Transcriber(Protocol):
    @property
    def engine_name(self) -> str: ...

    def transcribe(self, samples: np.ndarray, sample_rate_hz: int) -> TranscriptionResult: ...


class FasterWhisperTranscriber:
    """Lazy faster-whisper implementation backed by a local model cache."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self.model_size = model_size or os.getenv("PSYCON_WHISPER_MODEL", "small")
        self.device = device or os.getenv("PSYCON_WHISPER_DEVICE", "cpu")
        default_compute_type = "float16" if self.device == "cuda" else "int8"
        self.compute_type = compute_type or os.getenv(
            "PSYCON_WHISPER_COMPUTE_TYPE", default_compute_type
        )
        self._model = None

    @property
    def engine_name(self) -> str:
        return f"faster-whisper/{self.model_size}/{self.device}-{self.compute_type}"

    def transcribe(self, samples: np.ndarray, sample_rate_hz: int) -> TranscriptionResult:
        if sample_rate_hz != 16_000:
            return _failure(
                TranscriptionStatus.FAILED,
                self.engine_name,
                "transcriber_requires_16khz_audio",
            )
        try:
            model = self._load_model()
            audio = np.asarray(samples, dtype=np.float32) / 32_768.0
            generated, info = model.transcribe(
                audio,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
            )
            raw_segments = list(generated)
        except ImportError:
            return _failure(
                TranscriptionStatus.UNAVAILABLE,
                self.engine_name,
                "install_faster_whisper_from_requirements",
            )
        except Exception as error:  # model download/runtime errors become explicit data states
            return _failure(
                TranscriptionStatus.FAILED,
                self.engine_name,
                f"{type(error).__name__}: {error}",
            )

        segments = tuple(
            TranscriptSegment(
                start_s=float(segment.start),
                end_s=float(segment.end),
                text=segment.text.strip(),
                confidence=_log_probability_to_confidence(float(segment.avg_logprob)),
                source_start_sample=round(float(segment.start) * sample_rate_hz),
                source_end_sample=round(float(segment.end) * sample_rate_hz),
            )
            for segment in raw_segments
            if segment.text.strip()
        )
        if not segments:
            return TranscriptionResult(
                status=TranscriptionStatus.NO_SPEECH,
                text="",
                language=getattr(info, "language", None),
                language_confidence=float(getattr(info, "language_probability", 0.0)),
                confidence=0.0,
                segments=(),
                engine=self.engine_name,
                reasons=("model_returned_no_speech_segments",),
            )
        return TranscriptionResult(
            status=TranscriptionStatus.COMPLETE,
            text=" ".join(segment.text for segment in segments),
            language=getattr(info, "language", None),
            language_confidence=float(getattr(info, "language_probability", 0.0)),
            confidence=float(np.mean([segment.confidence for segment in segments])),
            segments=segments,
            engine=self.engine_name,
        )

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model


def transcribe_usable_regions(
    samples: np.ndarray,
    sample_rate_hz: int,
    quality_windows: list[dict[str, Any]],
    transcriber: Transcriber,
) -> TranscriptionResult:
    """Transcribe only contiguous windows accepted by the acoustic quality gate."""

    regions = _usable_regions(quality_windows, sample_rate_hz)
    if not regions:
        return _failure(
            TranscriptionStatus.SKIPPED_QUALITY,
            transcriber.engine_name,
            "no_usable_acoustic_windows",
        )

    combined: list[TranscriptSegment] = []
    languages: list[tuple[str, float]] = []
    reasons: list[str] = []
    for start_sample, end_sample in regions:
        region = np.asarray(samples[start_sample:end_sample], dtype=np.int16)
        result = transcriber.transcribe(region, sample_rate_hz)
        if result.status is TranscriptionStatus.COMPLETE:
            combined.extend(
                TranscriptSegment(
                    start_s=segment.start_s + start_sample / sample_rate_hz,
                    end_s=segment.end_s + start_sample / sample_rate_hz,
                    text=segment.text,
                    confidence=segment.confidence,
                    source_start_sample=segment.source_start_sample + start_sample,
                    source_end_sample=segment.source_end_sample + start_sample,
                )
                for segment in result.segments
            )
            if result.language:
                languages.append((result.language, result.language_confidence))
        elif result.status in (TranscriptionStatus.UNAVAILABLE, TranscriptionStatus.FAILED):
            return result
        else:
            reasons.extend(result.reasons)

    if not combined:
        return TranscriptionResult(
            status=TranscriptionStatus.NO_SPEECH,
            text="",
            language=_best_language(languages)[0],
            language_confidence=_best_language(languages)[1],
            confidence=0.0,
            segments=(),
            engine=transcriber.engine_name,
            reasons=tuple(reasons or ["no_speech_in_usable_regions"]),
        )
    language, language_confidence = _best_language(languages)
    return TranscriptionResult(
        status=TranscriptionStatus.COMPLETE,
        text=" ".join(segment.text for segment in combined),
        language=language,
        language_confidence=language_confidence,
        confidence=float(np.mean([segment.confidence for segment in combined])),
        segments=tuple(combined),
        engine=transcriber.engine_name,
        reasons=tuple(reasons),
    )


def not_requested_transcription() -> TranscriptionResult:
    return _failure(TranscriptionStatus.NOT_REQUESTED, "none", "transcription_not_requested")


def _usable_regions(
    windows: list[dict[str, Any]],
    sample_rate_hz: int,
) -> list[tuple[int, int]]:
    accepted = [
        (round(window["start_s"] * sample_rate_hz), round(window["end_s"] * sample_rate_hz))
        for window in windows
        if window["status"] == "usable"
    ]
    if not accepted:
        return []
    merged = [accepted[0]]
    for start, end in accepted[1:]:
        previous_start, previous_end = merged[-1]
        if start == previous_end:
            merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))
    return merged


def _best_language(languages: list[tuple[str, float]]) -> tuple[str | None, float]:
    return max(languages, key=lambda item: item[1]) if languages else (None, 0.0)


def _log_probability_to_confidence(avg_log_probability: float) -> float:
    return float(np.clip(math.exp(avg_log_probability), 0.0, 1.0))


def _failure(status: TranscriptionStatus, engine: str, reason: str) -> TranscriptionResult:
    return TranscriptionResult(
        status=status,
        text="",
        language=None,
        language_confidence=0.0,
        confidence=0.0,
        segments=(),
        engine=engine,
        reasons=(reason,),
    )
