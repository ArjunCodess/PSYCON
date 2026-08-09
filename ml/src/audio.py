"""Deterministic, quality-aware feature extraction for PCM16 audio."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import numpy as np

from protocol.chunk import AudioChunkV2, ChunkV2DecodeError, decode_chunk_v2


FEATURE_VERSION = "psycon_audio_v2"
FEATURE_NAMES = (
    "duration_s",
    "rms_dbfs",
    "peak_dbfs",
    "clip_fraction",
    "dc_offset",
    "zero_crossing_rate",
    "spectral_centroid_hz",
    "spectral_rolloff_85_hz",
    "spectral_flatness",
    "f0_hz",
    "f0_std_hz",
    "f0_min_hz",
    "f0_max_hz",
    "pitch_jitter_relative",
    "voice_stability",
    "voiced_fraction",
    "pause_count",
    "pause_duration_s",
)


class AudioStatus(str, Enum):
    USABLE = "usable"
    INSUFFICIENT = "insufficient_audio"
    CORRUPT = "corrupt"
    CLIPPED = "clipped"
    NOISY = "too_noisy"
    MISSING = "missing_audio"


@dataclass(frozen=True)
class AudioProvenance:
    session_id: str
    device_id: int
    sequence: int
    device_timestamp_us: int
    first_sample_index: int
    sample_count: int
    sample_rate_hz: int
    source_sha256: str
    feature_version: str = FEATURE_VERSION


@dataclass(frozen=True)
class AudioAnalysis:
    status: AudioStatus
    features: dict[str, float]
    reasons: tuple[str, ...]
    provenance: AudioProvenance | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "feature_version": FEATURE_VERSION,
            "features": self.features,
            "reasons": list(self.reasons),
            "provenance": asdict(self.provenance) if self.provenance else None,
        }


def analyze_audio_packet(
    packet: bytes | None,
    *,
    session_id: str,
    first_sample_index: int = 0,
    nominal_sample_rate_hz: int | None = None,
) -> AudioAnalysis:
    """Decode one Protocol v2 audio packet and retain source-to-feature lineage."""

    if packet is None:
        return AudioAnalysis(AudioStatus.MISSING, {}, ("packet_missing",), None)
    try:
        chunk = decode_chunk_v2(packet)
    except (ChunkV2DecodeError, TypeError) as error:
        return AudioAnalysis(AudioStatus.CORRUPT, {}, (str(error),), None)
    if not isinstance(chunk, AudioChunkV2):
        return AudioAnalysis(AudioStatus.CORRUPT, {}, ("packet_is_not_audio",), None)

    derived_rate = int(round(1_000_000 / chunk.header.sample_period_us))
    sample_rate_hz = nominal_sample_rate_hz or derived_rate
    if nominal_sample_rate_hz is not None:
        period_error_us = abs(1_000_000 / nominal_sample_rate_hz - chunk.header.sample_period_us)
        if period_error_us > 1.0:
            return AudioAnalysis(
                AudioStatus.CORRUPT,
                {},
                ("nominal_sample_rate_conflicts_with_packet_period",),
                None,
            )

    provenance = AudioProvenance(
        session_id=session_id,
        device_id=chunk.header.device_id,
        sequence=chunk.header.sequence,
        device_timestamp_us=chunk.header.device_timestamp_us,
        first_sample_index=first_sample_index,
        sample_count=chunk.header.sample_count,
        sample_rate_hz=sample_rate_hz,
        source_sha256=hashlib.sha256(packet).hexdigest(),
    )
    return analyze_pcm16(np.asarray(chunk.samples, dtype=np.int16), sample_rate_hz, provenance)


def analyze_pcm16(
    samples: np.ndarray,
    sample_rate_hz: int,
    provenance: AudioProvenance | None = None,
) -> AudioAnalysis:
    """Extract the frozen v1 feature vector and make an explicit quality decision."""

    values = np.asarray(samples)
    if sample_rate_hz < 1_000 or sample_rate_hz > 192_000:
        return AudioAnalysis(AudioStatus.CORRUPT, {}, ("invalid_sample_rate",), provenance)
    if values.ndim != 1 or values.dtype != np.int16 or len(values) == 0:
        return AudioAnalysis(AudioStatus.CORRUPT, {}, ("expected_nonempty_mono_pcm16",), provenance)

    normalized = values.astype(np.float64) / 32_768.0
    duration_s = len(normalized) / sample_rate_hz
    rms = float(np.sqrt(np.mean(normalized**2)))
    peak = float(np.max(np.abs(normalized)))
    rms_dbfs = _dbfs(rms)
    peak_dbfs = _dbfs(peak)
    clip_fraction = float(np.mean(np.abs(values.astype(np.int32)) >= 32_760))
    centered = normalized - np.mean(normalized)
    zero_crossing_rate = float(np.mean(np.signbit(centered[1:]) != np.signbit(centered[:-1])))

    frequencies = np.fft.rfftfreq(len(centered), 1 / sample_rate_hz)
    power = np.abs(np.fft.rfft(centered)) ** 2
    power_sum = float(np.sum(power))
    if power_sum > 0:
        spectral_centroid = float(np.sum(frequencies * power) / power_sum)
        cumulative = np.cumsum(power)
        rolloff_index = min(int(np.searchsorted(cumulative, 0.85 * cumulative[-1])), len(frequencies) - 1)
        spectral_rolloff = float(frequencies[rolloff_index])
        positive_power = power[1:] + np.finfo(float).tiny
        spectral_flatness = float(np.exp(np.mean(np.log(positive_power))) / np.mean(positive_power))
    else:
        spectral_centroid = 0.0
        spectral_rolloff = 0.0
        spectral_flatness = 0.0

    frame_rms = _frame_rms(normalized, sample_rate_hz)
    active = frame_rms >= 10 ** (-45 / 20)
    voiced_fraction = float(np.mean(active)) if len(active) else 0.0
    pause_count = float(np.sum((~active[1:]) & active[:-1])) if len(active) > 1 else 0.0
    pause_duration_s = float(np.sum(~active) * 0.010) if len(active) else 0.0
    pitch_track = _frame_f0(centered, sample_rate_hz)
    if len(pitch_track):
        f0_hz = float(np.mean(pitch_track))
        f0_std_hz = float(np.std(pitch_track))
        f0_min_hz = float(np.min(pitch_track))
        f0_max_hz = float(np.max(pitch_track))
        pitch_jitter_relative = (
            float(np.mean(np.abs(np.diff(pitch_track))) / f0_hz)
            if len(pitch_track) > 1 and f0_hz > 0
            else 0.0
        )
        voice_stability = float(np.clip(1.0 - pitch_jitter_relative, 0.0, 1.0))
    else:
        f0_hz = 0.0
        f0_std_hz = 0.0
        f0_min_hz = 0.0
        f0_max_hz = 0.0
        pitch_jitter_relative = 0.0
        voice_stability = 0.0

    features = dict(
        zip(
            FEATURE_NAMES,
            (
                duration_s,
                rms_dbfs,
                peak_dbfs,
                clip_fraction,
                float(np.mean(normalized)),
                zero_crossing_rate,
                spectral_centroid,
                spectral_rolloff,
                spectral_flatness,
                f0_hz,
                f0_std_hz,
                f0_min_hz,
                f0_max_hz,
                pitch_jitter_relative,
                voice_stability,
                voiced_fraction,
                pause_count,
                pause_duration_s,
            ),
            strict=True,
        )
    )

    if duration_s < 1.0:
        return AudioAnalysis(AudioStatus.INSUFFICIENT, features, ("duration_below_1s",), provenance)
    if rms_dbfs < -45 or voiced_fraction < 0.1:
        return AudioAnalysis(AudioStatus.INSUFFICIENT, features, ("insufficient_signal_energy",), provenance)
    if clip_fraction > 0.01:
        return AudioAnalysis(AudioStatus.CLIPPED, features, ("clip_fraction_above_1pct",), provenance)
    if spectral_flatness > 0.5:
        return AudioAnalysis(AudioStatus.NOISY, features, ("spectral_flatness_above_0_5",), provenance)
    return AudioAnalysis(AudioStatus.USABLE, features, (), provenance)


def _dbfs(amplitude: float) -> float:
    return max(-120.0, float(20 * np.log10(max(amplitude, np.finfo(float).tiny))))


def _frame_rms(samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
    frame_length = max(1, round(0.025 * sample_rate_hz))
    hop_length = max(1, round(0.010 * sample_rate_hz))
    if len(samples) < frame_length:
        return np.array([np.sqrt(np.mean(samples**2))])
    starts = range(0, len(samples) - frame_length + 1, hop_length)
    return np.array([np.sqrt(np.mean(samples[start : start + frame_length] ** 2)) for start in starts])


def _frame_f0(samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
    """Return a deterministic pitch track for energy-active 50 ms frames."""

    frame_length = max(1, round(0.050 * sample_rate_hz))
    hop_length = max(1, round(0.010 * sample_rate_hz))
    if len(samples) < frame_length:
        frames = [samples]
    else:
        frames = [
            samples[start : start + frame_length]
            for start in range(0, len(samples) - frame_length + 1, hop_length)
        ]
    estimates = []
    for frame in frames:
        frame_rms = float(np.sqrt(np.mean(frame**2)))
        if _dbfs(frame_rms) >= -45:
            estimates.append(_estimate_f0(frame, sample_rate_hz))
    return np.asarray([estimate for estimate in estimates if estimate > 0], dtype=np.float64)


def _estimate_f0(samples: np.ndarray, sample_rate_hz: int) -> float:
    """Estimate 70-400 Hz F0 with normalized autocorrelation."""

    analysis_length = min(len(samples), sample_rate_hz)
    windowed = samples[:analysis_length] * np.hanning(analysis_length)
    spectrum = np.fft.rfft(windowed, n=2 * analysis_length)
    autocorrelation = np.fft.irfft(spectrum * np.conj(spectrum))[:analysis_length]
    min_lag = max(1, sample_rate_hz // 400)
    max_lag = min(analysis_length - 1, sample_rate_hz // 70)
    if max_lag <= min_lag or autocorrelation[0] <= 0:
        return 0.0
    segment = autocorrelation[min_lag : max_lag + 1]
    peak_index = int(np.argmax(segment))
    lag = min_lag + peak_index
    confidence = autocorrelation[lag] / autocorrelation[0]
    if confidence < 0.2:
        return 0.0
    fractional_lag = float(lag)
    if 0 < peak_index < len(segment) - 1:
        left, center, right = segment[peak_index - 1 : peak_index + 2]
        denominator = left - 2 * center + right
        if denominator != 0:
            fractional_lag += float(0.5 * (left - right) / denominator)
    return float(sample_rate_hz / fractional_lag)
