"""Consent-aware speaker, conversation-timing, and vocal-jitter analysis."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from ml.src.transcription import TranscriptWord, TranscriptionResult


SPEAKER_ANALYZER = "psycon_speaker_analysis"
MIN_ENROLLMENT_CLIP_S = 5.0
MAX_ENROLLMENT_CLIP_S = 10.0
MIN_CLUSTER_SPEECH_S = 3.0
MIN_JITTER_REGION_S = 1.0


@dataclass(frozen=True)
class SpeakerTurn:
    start_s: float
    end_s: float
    speaker_id: str

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiarizationResult:
    regular_turns: tuple[SpeakerTurn, ...]
    exclusive_turns: tuple[SpeakerTurn, ...]
    engine: str


class Diarizer(Protocol):
    @property
    def engine_name(self) -> str: ...

    def diarize(self, samples: np.ndarray, sample_rate_hz: int) -> DiarizationResult: ...


class SpeakerEmbedder(Protocol):
    @property
    def engine_name(self) -> str: ...

    @property
    def verification_threshold(self) -> float: ...

    def embed(self, samples: np.ndarray, sample_rate_hz: int) -> np.ndarray: ...


class PyannoteDiarizer:
    """Lazy local Community-1 adapter; model access requires an HF token."""

    def __init__(self, token: str | None = None, device: str | None = None) -> None:
        self.token = token or os.getenv("HF_TOKEN")
        self.device = device or os.getenv("PSYCON_DIARIZATION_DEVICE", "cpu")
        self._pipeline = None

    @property
    def engine_name(self) -> str:
        return f"pyannote/speaker-diarization-community-1/{self.device}"

    def diarize(self, samples: np.ndarray, sample_rate_hz: int) -> DiarizationResult:
        if not self.token:
            raise RuntimeError("HF_TOKEN is required for local speaker diarization")
        import torch

        pipeline = self._load_pipeline()
        waveform = torch.from_numpy(np.asarray(samples, dtype=np.float32)[None, :] / 32768.0)
        output = pipeline({"waveform": waveform, "sample_rate": sample_rate_hz})
        regular = _annotation_turns(output.speaker_diarization)
        exclusive = _annotation_turns(output.exclusive_speaker_diarization)
        return DiarizationResult(regular, exclusive, self.engine_name)

    def _load_pipeline(self):
        if self._pipeline is None:
            import torch
            from pyannote.audio import Pipeline

            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1", token=self.token
            )
            if self.device == "cuda":
                self._pipeline.to(torch.device("cuda"))
        return self._pipeline


class SpeechBrainEmbedder:
    """Lazy ECAPA-TDNN adapter for enrollment and wearer verification."""

    def __init__(self, device: str | None = None) -> None:
        self.device = device or os.getenv("PSYCON_SPEAKER_DEVICE", "cpu")
        self._model = None

    @property
    def engine_name(self) -> str:
        return f"speechbrain/spkrec-ecapa-voxceleb/{self.device}"

    @property
    def verification_threshold(self) -> float:
        return float(os.getenv("PSYCON_SPEAKER_THRESHOLD", "0.25"))

    def embed(self, samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
        if sample_rate_hz != 16_000:
            raise ValueError("speaker embedding requires 16 kHz audio")
        import torch

        signal = torch.from_numpy(np.asarray(samples, dtype=np.float32) / 32768.0).unsqueeze(0)
        if self.device == "cuda":
            signal = signal.cuda()
        with torch.no_grad():
            embedding = self._load_model().encode_batch(signal).squeeze().detach().cpu().numpy()
        return _normalize_embedding(embedding)

    def _load_model(self):
        if self._model is None:
            from speechbrain.inference.speaker import EncoderClassifier

            self._model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                run_opts={"device": self.device},
            )
        return self._model


@dataclass(frozen=True)
class VoiceProfile:
    embedding: np.ndarray
    engine: str
    enrolled_clips: int
    usable_duration_s: float


class VoiceProfileStore:
    """One encrypted local wearer profile. Raw enrollment audio is never stored."""

    def __init__(self, path: str | Path, secret: str | None = None) -> None:
        self.path = Path(path)
        self.secret = secret if secret is not None else os.getenv("PSYCON_PROFILE_KEY")

    @property
    def configured(self) -> bool:
        return bool(self.secret and len(self.secret) >= 32)

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, profile: VoiceProfile) -> None:
        fernet = self._fernet()
        payload = json.dumps(
            {
                "embedding": profile.embedding.astype(float).tolist(),
                "engine": profile.engine,
                "enrolled_clips": profile.enrolled_clips,
                "usable_duration_s": profile.usable_duration_s,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = fernet.encrypt(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(dir=self.path.parent, prefix="profile-", suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as temporary:
                temporary.write(encrypted)
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def load(self) -> VoiceProfile | None:
        if not self.exists:
            return None
        payload = json.loads(self._fernet().decrypt(self.path.read_bytes()).decode("utf-8"))
        return VoiceProfile(
            embedding=_normalize_embedding(np.asarray(payload["embedding"], dtype=np.float32)),
            engine=str(payload["engine"]),
            enrolled_clips=int(payload["enrolled_clips"]),
            usable_duration_s=float(payload["usable_duration_s"]),
        )

    def delete(self) -> bool:
        if not self.exists:
            return False
        self.path.unlink()
        return True

    def _fernet(self):
        if not self.configured:
            raise RuntimeError("PSYCON_PROFILE_KEY must contain at least 32 characters")
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret.encode("utf-8")).digest())
        return Fernet(key)


def enroll_wearer(
    clips: list[tuple[np.ndarray, int]], embedder: SpeakerEmbedder, store: VoiceProfileStore
) -> VoiceProfile:
    if len(clips) != 3:
        raise ValueError("exactly three enrollment recordings are required")
    embeddings: list[np.ndarray] = []
    usable_duration = 0.0
    for samples, sample_rate_hz in clips:
        duration = len(samples) / sample_rate_hz
        if duration < MIN_ENROLLMENT_CLIP_S or duration > MAX_ENROLLMENT_CLIP_S:
            raise ValueError("each enrollment recording must be 5 to 10 seconds long")
        reason = _signal_rejection_reason(samples)
        if reason:
            raise ValueError(f"enrollment recording rejected: {reason}")
        embeddings.append(embedder.embed(samples, sample_rate_hz))
        usable_duration += duration
    profile = VoiceProfile(
        embedding=_normalize_embedding(np.mean(embeddings, axis=0)),
        engine=embedder.engine_name,
        enrolled_clips=3,
        usable_duration_s=usable_duration,
    )
    store.save(profile)
    return profile


def unavailable_speaker_analysis(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "analyzer": SPEAKER_ANALYZER,
        "participant_status": "not_identified",
        "reasons": [reason],
        "turns": [],
        "attributed_words": [],
        "speakers": {},
        "conversation": {},
    }


def analyze_speakers(
    samples: np.ndarray,
    sample_rate_hz: int,
    transcription: TranscriptionResult,
    diarizer: Diarizer,
    embedder: SpeakerEmbedder,
    profile: VoiceProfile | None,
    *,
    ambiguity_margin: float | None = None,
) -> dict[str, Any]:
    """Analyze speaker identity and timing while abstaining from uncertain identity matches."""

    try:
        diarization = diarizer.diarize(samples, sample_rate_hz)
    except Exception as error:
        return unavailable_speaker_analysis(f"{type(error).__name__}: {error}")
    if not diarization.exclusive_turns:
        return unavailable_speaker_analysis("diarization_returned_no_speech")

    margin = ambiguity_margin if ambiguity_margin is not None else float(
        os.getenv("PSYCON_SPEAKER_MARGIN", "0.05")
    )
    clusters = sorted({turn.speaker_id for turn in diarization.exclusive_turns})
    clean_turns = _non_overlapping_turns(diarization.exclusive_turns, diarization.regular_turns)
    scores: dict[str, float] = {}
    insufficient: set[str] = set()
    if profile is not None:
        for cluster in clusters:
            cluster_samples = _join_turn_audio(samples, sample_rate_hz, clean_turns, cluster)
            if len(cluster_samples) / sample_rate_hz < MIN_CLUSTER_SPEECH_S:
                insufficient.add(cluster)
                continue
            try:
                scores[cluster] = _cosine_similarity(
                    profile.embedding, embedder.embed(cluster_samples, sample_rate_hz)
                )
            except Exception:
                insufficient.add(cluster)

    participant_cluster, participant_status = _select_participant(
        scores, embedder.verification_threshold, margin, profile is not None
    )
    label_map = _speaker_labels(diarization.exclusive_turns, participant_cluster)
    exclusive = tuple(
        SpeakerTurn(turn.start_s, turn.end_s, label_map[turn.speaker_id])
        for turn in diarization.exclusive_turns
    )
    regular = tuple(
        SpeakerTurn(turn.start_s, turn.end_s, label_map[turn.speaker_id])
        for turn in diarization.regular_turns
    )
    attributed_words = _attribute_words(transcription.words, exclusive)
    duration_s = len(samples) / sample_rate_hz
    speakers = _speaker_metrics(samples, sample_rate_hz, exclusive, regular, attributed_words, duration_s)
    conversation = _conversation_metrics(exclusive, regular)
    return {
        "status": "complete",
        "analyzer": SPEAKER_ANALYZER,
        "engine": diarization.engine,
        "embedding_engine": embedder.engine_name,
        "participant_status": participant_status,
        "participant_similarity": scores.get(participant_cluster) if participant_cluster else None,
        "verification_threshold": embedder.verification_threshold,
        "ambiguity_margin": margin,
        "reasons": (["some_speakers_have_insufficient_clean_speech"] if insufficient else []),
        "turns": [turn.to_dict() for turn in exclusive],
        "attributed_words": attributed_words,
        "speakers": speakers,
        "conversation": conversation,
    }


def _annotation_turns(annotation: Any) -> tuple[SpeakerTurn, ...]:
    return tuple(
        sorted(
            (
                SpeakerTurn(float(segment.start), float(segment.end), str(speaker))
                for segment, _, speaker in annotation.itertracks(yield_label=True)
                if float(segment.end) > float(segment.start)
            ),
            key=lambda turn: (turn.start_s, turn.end_s, turn.speaker_id),
        )
    )


def _normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    values = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(values))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("speaker embedding is empty or invalid")
    return values / norm


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(_normalize_embedding(left), _normalize_embedding(right)))


def _signal_rejection_reason(samples: np.ndarray) -> str | None:
    values = np.asarray(samples, dtype=np.int16)
    if not len(values):
        return "empty_audio"
    normalized = values.astype(np.float64) / 32768.0
    rms_dbfs = 20 * math.log10(max(float(np.sqrt(np.mean(normalized**2))), 1e-12))
    if rms_dbfs < -45:
        return "insufficient_signal_energy"
    if float(np.mean(np.abs(values.astype(np.int32)) >= 32760)) > 0.01:
        return "clip_fraction_above_1pct"
    return None


def _overlap_duration(turn: SpeakerTurn, others: tuple[SpeakerTurn, ...]) -> float:
    return sum(
        max(0.0, min(turn.end_s, other.end_s) - max(turn.start_s, other.start_s))
        for other in others
        if other.speaker_id != turn.speaker_id
    )


def _non_overlapping_turns(
    exclusive: tuple[SpeakerTurn, ...], regular: tuple[SpeakerTurn, ...]
) -> tuple[SpeakerTurn, ...]:
    return tuple(turn for turn in exclusive if _overlap_duration(turn, regular) <= 1e-6)


def _join_turn_audio(
    samples: np.ndarray, sample_rate_hz: int, turns: tuple[SpeakerTurn, ...], speaker: str
) -> np.ndarray:
    regions = [
        np.asarray(samples[round(turn.start_s * sample_rate_hz) : round(turn.end_s * sample_rate_hz)])
        for turn in turns
        if turn.speaker_id == speaker
    ]
    return np.concatenate(regions).astype(np.int16) if regions else np.array([], dtype=np.int16)


def _select_participant(
    scores: dict[str, float], threshold: float, margin: float, has_profile: bool
) -> tuple[str | None, str]:
    if not has_profile:
        return None, "not_enrolled"
    if not scores:
        return None, "insufficient_speech"
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_speaker, best_score = ranked[0]
    if best_score < threshold:
        return None, "not_identified"
    if len(ranked) > 1 and best_score - ranked[1][1] < margin:
        return None, "ambiguous_match"
    return best_speaker, "identified"


def _speaker_labels(turns: tuple[SpeakerTurn, ...], participant: str | None) -> dict[str, str]:
    ordered = list(dict.fromkeys(turn.speaker_id for turn in sorted(turns, key=lambda item: item.start_s)))
    labels: dict[str, str] = {}
    anonymous_number = 2 if participant else 1
    for speaker in ordered:
        if speaker == participant:
            labels[speaker] = "participant"
        else:
            labels[speaker] = f"speaker_{anonymous_number:02d}"
            anonymous_number += 1
    return labels


def _attribute_words(words: tuple[TranscriptWord, ...], turns: tuple[SpeakerTurn, ...]) -> list[dict[str, Any]]:
    attributed = []
    for word in words:
        overlaps = [
            (max(0.0, min(word.end_s, turn.end_s) - max(word.start_s, turn.start_s)), turn.speaker_id)
            for turn in turns
        ]
        best_overlap, speaker = max(overlaps, default=(0.0, "unknown"))
        word_duration = max(1e-9, word.end_s - word.start_s)
        if best_overlap / word_duration < 0.5:
            speaker = "unknown"
        attributed.append({**word.to_dict(), "speaker_id": speaker})
    return attributed


def _speaker_metrics(
    samples: np.ndarray,
    sample_rate_hz: int,
    exclusive: tuple[SpeakerTurn, ...],
    regular: tuple[SpeakerTurn, ...],
    words: list[dict[str, Any]],
    recording_duration_s: float,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for speaker in sorted({turn.speaker_id for turn in exclusive}):
        turns = tuple(turn for turn in exclusive if turn.speaker_id == speaker)
        speech_duration = sum(turn.duration_s for turn in turns)
        word_count = sum(word["speaker_id"] == speaker for word in words)
        turn_durations = [turn.duration_s for turn in turns]
        jitter = _jitter_metrics(samples, sample_rate_hz, turns, regular)
        metrics[speaker] = {
            "speaking_duration_s": speech_duration,
            "speaking_share": speech_duration / recording_duration_s if recording_duration_s else 0.0,
            "turn_count": len(turns),
            "mean_turn_duration_s": float(np.mean(turn_durations)) if turn_durations else 0.0,
            "median_turn_duration_s": float(np.median(turn_durations)) if turn_durations else 0.0,
            "word_count": word_count,
            "articulation_rate_wpm": word_count / speech_duration * 60 if speech_duration else 0.0,
            "session_speaking_rate_wpm": word_count / recording_duration_s * 60 if recording_duration_s else 0.0,
            "jitter": jitter,
        }
    return metrics


def _conversation_metrics(
    exclusive: tuple[SpeakerTurn, ...], regular: tuple[SpeakerTurn, ...]
) -> dict[str, Any]:
    turns = sorted(exclusive, key=lambda turn: (turn.start_s, turn.end_s))
    within_pauses: list[float] = []
    response_gaps: list[float] = []
    signed_latencies: list[float] = []
    for previous, current in zip(turns, turns[1:]):
        gap = current.start_s - previous.end_s
        if previous.speaker_id == current.speaker_id and gap >= 0.2:
            within_pauses.append(gap)
        elif previous.speaker_id != current.speaker_id:
            signed_latencies.append(gap)
            if gap > 0:
                response_gaps.append(gap)

    overlap_intervals: list[tuple[float, float]] = []
    interruption_events: set[tuple[str, int]] = set()
    ordered_regular = sorted(regular, key=lambda turn: (turn.start_s, turn.end_s))
    for index, left in enumerate(ordered_regular):
        for right in ordered_regular[index + 1 :]:
            if right.start_s >= left.end_s:
                break
            if right.speaker_id == left.speaker_id:
                continue
            start, end = max(left.start_s, right.start_s), min(left.end_s, right.end_s)
            if end > start:
                overlap_intervals.append((start, end))
                if left.end_s - right.start_s >= 0.2 and right.duration_s >= 0.5:
                    interruption_events.add((right.speaker_id, round(right.start_s * 1000)))
    merged_overlap = _merge_intervals(overlap_intervals)
    overlap_duration = sum(end - start for start, end in merged_overlap)
    return {
        "within_speaker_pauses": _duration_summary(within_pauses),
        "response_gaps": _duration_summary(response_gaps),
        "signed_transition_latencies_s": signed_latencies,
        "overlap_count": len(merged_overlap),
        "overlap_duration_s": overlap_duration,
        "interruption_count": len(interruption_events),
    }


def _duration_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "total_s": float(sum(values)),
        "mean_s": float(np.mean(values)) if values else 0.0,
        "median_s": float(np.median(values)) if values else 0.0,
        "max_s": max(values, default=0.0),
    }


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _jitter_metrics(
    samples: np.ndarray,
    sample_rate_hz: int,
    turns: tuple[SpeakerTurn, ...],
    regular: tuple[SpeakerTurn, ...],
) -> dict[str, Any]:
    regions: list[tuple[float, dict[str, float]]] = []
    rejection_reasons: set[str] = set()
    for turn in turns:
        if turn.duration_s < MIN_JITTER_REGION_S or _overlap_duration(turn, regular) > 1e-6:
            rejection_reasons.add("insufficient_clean_continuous_speech")
            continue
        region = np.asarray(
            samples[round(turn.start_s * sample_rate_hz) : round(turn.end_s * sample_rate_hz)],
            dtype=np.int16,
        )
        reason = _signal_rejection_reason(region)
        if reason:
            rejection_reasons.add(reason)
            continue
        try:
            import parselmouth
            from parselmouth.praat import call

            sound = parselmouth.Sound(region.astype(np.float64) / 32768.0, sample_rate_hz)
            points = call(sound, "To PointProcess (periodic, cc)", 70.0, 400.0)
            values = {
                "local_absolute_s": float(call(points, "Get jitter (local, absolute)", 0, 0, 0.0001, 0.02, 1.3)),
                "local_relative": float(call(points, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)),
                "rap": float(call(points, "Get jitter (rap)", 0, 0, 0.0001, 0.02, 1.3)),
                "ppq5": float(call(points, "Get jitter (ppq5)", 0, 0, 0.0001, 0.02, 1.3)),
                "ddp": float(call(points, "Get jitter (ddp)", 0, 0, 0.0001, 0.02, 1.3)),
            }
            if all(math.isfinite(value) for value in values.values()):
                regions.append((turn.duration_s, values))
            else:
                rejection_reasons.add("insufficient_pitch_periods")
        except ImportError:
            return {"status": "unavailable", "reasons": ["install_praat_parselmouth"]}
        except Exception:
            rejection_reasons.add("insufficient_pitch_periods")
    if not regions:
        return {
            "status": "unavailable",
            "reasons": sorted(rejection_reasons or {"no_valid_voiced_regions"}),
            "valid_region_count": 0,
            "coverage_s": 0.0,
        }
    total_duration = sum(duration for duration, _ in regions)
    aggregate = {
        name: sum(duration * values[name] for duration, values in regions) / total_duration
        for name in regions[0][1]
    }
    return {
        "status": "complete",
        **aggregate,
        "pitch_jitter_relative": aggregate["local_relative"],
        "valid_region_count": len(regions),
        "coverage_s": total_duration,
        "reasons": sorted(rejection_reasons),
    }
