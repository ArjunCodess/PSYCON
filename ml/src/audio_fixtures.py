"""Deterministic synthetic audio used by tests and the Week 3 demo."""

from __future__ import annotations

import numpy as np


def silence(sample_rate_hz: int, duration_s: float = 2.0) -> np.ndarray:
    return np.zeros(_sample_count(sample_rate_hz, duration_s), dtype=np.int16)


def impulse(sample_rate_hz: int, duration_s: float = 2.0) -> np.ndarray:
    samples = silence(sample_rate_hz, duration_s)
    samples[len(samples) // 2] = 24_000
    return samples


def tone(
    sample_rate_hz: int,
    duration_s: float = 2.0,
    frequency_hz: float = 220.0,
    amplitude: float = 0.35,
) -> np.ndarray:
    time_s = np.arange(_sample_count(sample_rate_hz, duration_s)) / sample_rate_hz
    return _pcm16(amplitude * np.sin(2 * np.pi * frequency_hz * time_s))


def clipped_tone(sample_rate_hz: int, duration_s: float = 2.0) -> np.ndarray:
    time_s = np.arange(_sample_count(sample_rate_hz, duration_s)) / sample_rate_hz
    signal = 1.8 * np.sin(2 * np.pi * 220.0 * time_s)
    return _pcm16(np.clip(signal, -1.0, 1.0))


def speech_like(sample_rate_hz: int, duration_s: float = 2.0) -> np.ndarray:
    """Return an amplitude-modulated voiced signal, not simulated human speech."""

    time_s = np.arange(_sample_count(sample_rate_hz, duration_s)) / sample_rate_hz
    envelope = 0.5 * (1.0 + np.sin(2 * np.pi * 2.4 * time_s))
    carrier = np.sin(2 * np.pi * 180.0 * time_s) + 0.3 * np.sin(2 * np.pi * 360.0 * time_s)
    return _pcm16(0.3 * envelope * carrier)


def white_noise(
    sample_rate_hz: int,
    duration_s: float = 2.0,
    seed: int = 20260806,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return _pcm16(rng.normal(0.0, 0.25, _sample_count(sample_rate_hz, duration_s)))


def all_fixtures(sample_rate_hz: int = 16_000) -> dict[str, np.ndarray]:
    return {
        "silence": silence(sample_rate_hz),
        "impulse": impulse(sample_rate_hz),
        "tone": tone(sample_rate_hz),
        "clipping": clipped_tone(sample_rate_hz),
        "speech_like": speech_like(sample_rate_hz),
        "noise": white_noise(sample_rate_hz),
    }


def _sample_count(sample_rate_hz: int, duration_s: float) -> int:
    if sample_rate_hz <= 0 or duration_s <= 0:
        raise ValueError("sample rate and duration must be positive")
    return int(round(sample_rate_hz * duration_s))


def _pcm16(signal: np.ndarray) -> np.ndarray:
    return np.rint(np.clip(signal, -1.0, 1.0) * 32_767).astype(np.int16)
