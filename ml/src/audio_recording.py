"""Decode uploaded WAV recordings and run the Protocol v2 audio pipeline."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from ml.src.audio import AudioStatus, analyze_audio_packet
from protocol.chunk import encode_chunk_v2


TARGET_SAMPLE_RATE_HZ = 16_000
WINDOW_DURATION_S = 2.0
MAX_RECORDING_DURATION_S = 300.0


class AudioRecordingError(ValueError):
    """Raised when an uploaded recording cannot be analyzed safely."""


@dataclass(frozen=True)
class DecodedRecording:
    samples: np.ndarray
    original_sample_rate_hz: int
    sample_rate_hz: int
    channels: int
    source_dtype: str
    duration_s: float


def decode_wav(source: bytes) -> DecodedRecording:
    """Decode PCM/float WAV bytes, downmix to mono, and resample to 16 kHz PCM16."""

    if not source:
        raise AudioRecordingError("The uploaded file is empty.")
    try:
        sample_rate_hz, raw = wavfile.read(io.BytesIO(source))
    except (ValueError, EOFError, OSError) as error:
        raise AudioRecordingError("This is not a readable WAV recording.") from error

    values = np.asarray(raw)
    if values.ndim not in (1, 2) or values.size == 0:
        raise AudioRecordingError("The WAV file must contain mono or multichannel audio samples.")
    if not 1_000 <= sample_rate_hz <= 192_000:
        raise AudioRecordingError("The WAV sample rate must be between 1 kHz and 192 kHz.")

    channels = 1 if values.ndim == 1 else values.shape[1]
    if channels > 8:
        raise AudioRecordingError("Recordings with more than eight channels are not supported.")
    frame_count = values.shape[0]
    duration_s = frame_count / sample_rate_hz
    if duration_s > MAX_RECORDING_DURATION_S:
        raise AudioRecordingError("Keep the demo recording at or below five minutes.")

    normalized = _normalize_audio(values)
    if normalized.ndim == 2:
        normalized = np.mean(normalized, axis=1)
    if sample_rate_hz != TARGET_SAMPLE_RATE_HZ:
        divisor = math.gcd(sample_rate_hz, TARGET_SAMPLE_RATE_HZ)
        normalized = resample_poly(
            normalized,
            TARGET_SAMPLE_RATE_HZ // divisor,
            sample_rate_hz // divisor,
        )
    pcm16 = np.rint(np.clip(normalized, -1.0, 1.0) * 32_767).astype(np.int16)
    if len(pcm16) == 0:
        raise AudioRecordingError("The WAV file contains no decodable audio samples.")

    return DecodedRecording(
        samples=pcm16,
        original_sample_rate_hz=int(sample_rate_hz),
        sample_rate_hz=TARGET_SAMPLE_RATE_HZ,
        channels=channels,
        source_dtype=str(values.dtype),
        duration_s=duration_s,
    )


def analyze_wav_upload(source: bytes, filename: str) -> dict[str, Any]:
    """Analyze a real WAV upload as sequential, provenance-preserving windows."""

    decoded = decode_wav(source)
    source_sha256 = hashlib.sha256(source).hexdigest()
    return analyze_decoded_recording(decoded, filename, source_sha256)


def analyze_decoded_recording(
    decoded: DecodedRecording,
    filename: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Analyze an already decoded recording without decoding or hashing it again."""

    session_id = f"upload-{source_sha256[:12]}"
    maximum_window_samples = int(TARGET_SAMPLE_RATE_HZ * WINDOW_DURATION_S)
    window_count = max(1, math.ceil(len(decoded.samples) / maximum_window_samples))
    window_samples = math.ceil(len(decoded.samples) / window_count)
    windows: list[dict[str, Any]] = []

    for sequence, start in enumerate(range(0, len(decoded.samples), window_samples), start=1):
        samples = decoded.samples[start : start + window_samples]
        packet = encode_chunk_v2(
            stream_type="audio_pcm",
            device_id=0,
            sequence=sequence,
            device_timestamp_us=round(start * 1_000_000 / TARGET_SAMPLE_RATE_HZ),
            sample_count=len(samples),
            sample_period_us=62,
            payload=samples.astype("<i2").tobytes(),
        )
        analysis = analyze_audio_packet(
            packet,
            session_id=session_id,
            first_sample_index=start,
            nominal_sample_rate_hz=TARGET_SAMPLE_RATE_HZ,
        )
        windows.append(
            {
                "number": sequence,
                "start_s": start / TARGET_SAMPLE_RATE_HZ,
                "end_s": (start + len(samples)) / TARGET_SAMPLE_RATE_HZ,
                **analysis.to_dict(),
            }
        )

    counts = {status.value: 0 for status in AudioStatus}
    for window in windows:
        counts[window["status"]] += 1
    usable_count = counts[AudioStatus.USABLE.value]
    if usable_count == len(windows):
        overall_status = "usable"
        summary = "Every window passed the current engineering quality checks."
    elif usable_count:
        overall_status = "partially_usable"
        summary = "Some windows passed; rejected windows should stay out of downstream inference."
    else:
        overall_status = "no_usable_audio"
        summary = "No window passed the current engineering quality checks."

    return {
        "filename": filename or "recording.wav",
        "source_sha256": source_sha256,
        "session_id": session_id,
        "overall_status": overall_status,
        "summary": summary,
        "duration_s": decoded.duration_s,
        "original_sample_rate_hz": decoded.original_sample_rate_hz,
        "analysis_sample_rate_hz": decoded.sample_rate_hz,
        "channels": decoded.channels,
        "source_dtype": decoded.source_dtype,
        "window_count": len(windows),
        "extractor": windows[0]["extractor"],
        "counts": counts,
        "windows": windows,
        "decoder": {
            "samples": f"{len(decoded.samples)} PCM16 samples",
            "original_sample_rate_hz": decoded.original_sample_rate_hz,
            "sample_rate_hz": decoded.sample_rate_hz,
            "channels": decoded.channels,
            "source_dtype": decoded.source_dtype,
        },
    }


def _normalize_audio(values: np.ndarray) -> np.ndarray:
    if np.issubdtype(values.dtype, np.floating):
        normalized = values.astype(np.float64)
        if not np.all(np.isfinite(normalized)):
            raise AudioRecordingError("The WAV file contains non-finite audio samples.")
        return np.clip(normalized, -1.0, 1.0)
    if values.dtype == np.uint8:
        return (values.astype(np.float64) - 128.0) / 128.0
    if np.issubdtype(values.dtype, np.signedinteger):
        scale = float(max(abs(np.iinfo(values.dtype).min), np.iinfo(values.dtype).max))
        return values.astype(np.float64) / scale
    raise AudioRecordingError(f"Unsupported WAV sample format: {values.dtype}.")
