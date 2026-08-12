"""Quality-gated Praat measurements for conversational and sustained-vowel audio."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


PITCH_FLOOR_HZ = 70.0
PITCH_CEILING_HZ = 400.0
MAX_PERIOD_FACTOR = 1.3
MIN_REGION_S = 1.0
MIN_VOWEL_S = 3.0
MAX_VOWEL_S = 8.0
VOWEL_EDGE_TRIM_S = 0.5
VOWEL_SELECTION_S = 2.0
MIN_CONVERSATIONAL_VOICED_FRACTION = 0.3


def unavailable_vocal_jitter(*reasons: str, context: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "measurement_context": context,
        "reasons": sorted(set(reasons or ("no_valid_voiced_regions",))),
        "valid_region_count": 0,
        "valid_period_count": 0,
        "coverage_s": 0.0,
        "provenance": _provenance(),
    }


def analyze_vocal_jitter_regions(
    samples: np.ndarray,
    sample_rate_hz: int,
    intervals: Iterable[tuple[float, float]],
    *,
    context: str = "conversational_research_estimate",
) -> dict[str, Any]:
    """Measure and pulse-weight valid continuous regions without joining their boundaries."""

    try:
        import parselmouth  # noqa: F401
    except ImportError:
        return unavailable_vocal_jitter("install_praat_parselmouth", context=context)

    accepted: list[tuple[int, float, float, dict[str, float]]] = []
    rejection_reasons: set[str] = set()
    for start_s, end_s in intervals:
        duration_s = max(0.0, end_s - start_s)
        if duration_s < MIN_REGION_S:
            rejection_reasons.add("insufficient_clean_continuous_speech")
            continue
        region = np.asarray(
            samples[round(start_s * sample_rate_hz) : round(end_s * sample_rate_hz)],
            dtype=np.int16,
        )
        quality_reason = _signal_rejection_reason(region)
        if quality_reason:
            rejection_reasons.add(quality_reason)
            continue
        periodicity = _periodicity_quality(region, sample_rate_hz)
        if periodicity is None:
            rejection_reasons.add("insufficient_pitch_periods")
            continue
        if periodicity["voiced_fraction"] < MIN_CONVERSATIONAL_VOICED_FRACTION:
            rejection_reasons.add("insufficient_voiced_coverage")
            continue
        measurement = _measure_region(region, sample_rate_hz)
        if measurement["status"] != "complete":
            rejection_reasons.update(measurement["reasons"])
            continue
        accepted.append(
            (
                int(measurement["valid_period_count"]),
                duration_s,
                periodicity["voiced_fraction"],
                {name: float(measurement[name]) for name in _metric_names()},
            )
        )

    if not accepted:
        return unavailable_vocal_jitter(*rejection_reasons, context=context)

    total_periods = sum(periods for periods, _, _, _ in accepted)
    total_duration = sum(duration for _, duration, _, _ in accepted)
    aggregate = {
        name: sum(periods * values[name] for periods, _, _, values in accepted) / total_periods
        for name in _metric_names()
    }
    return {
        "status": "complete",
        "measurement_context": context,
        **aggregate,
        "pitch_jitter_relative": aggregate["local_relative"],
        "valid_region_count": len(accepted),
        "valid_period_count": total_periods,
        "coverage_s": total_duration,
        "mean_voiced_fraction": sum(
            duration * voiced_fraction for _, duration, voiced_fraction, _ in accepted
        )
        / total_duration,
        "reasons": sorted(rejection_reasons),
        "provenance": _provenance(),
    }


def analyze_sustained_vowel(samples: np.ndarray, sample_rate_hz: int) -> dict[str, Any]:
    """Select a clean central two-second region from an optional sustained vowel."""

    duration_s = len(samples) / sample_rate_hz if sample_rate_hz else 0.0
    context = "controlled_sustained_vowel"
    if duration_s < MIN_VOWEL_S:
        return unavailable_vocal_jitter("vowel_duration_below_3s", context=context)
    if duration_s > MAX_VOWEL_S:
        return unavailable_vocal_jitter("vowel_duration_above_8s", context=context)

    selection, rejection_reasons = _select_vowel_region(samples, sample_rate_hz)
    if selection is None:
        return unavailable_vocal_jitter(*rejection_reasons, context=context)
    start_s, end_s, quality = selection
    result = analyze_vocal_jitter_regions(
        samples, sample_rate_hz, ((start_s, end_s),), context=context
    )
    result["input_duration_s"] = duration_s
    result["selected_start_s"] = start_s
    result["selected_end_s"] = end_s
    result["selected_voiced_fraction"] = quality["voiced_fraction"]
    result["selected_f0_mean_hz"] = quality["f0_mean_hz"]
    result["selected_f0_cv"] = quality["f0_cv"]
    return result


def not_supplied_sustained_vowel() -> dict[str, Any]:
    return unavailable_vocal_jitter("sustained_vowel_not_supplied", context="controlled_sustained_vowel")


def _select_vowel_region(
    samples: np.ndarray, sample_rate_hz: int
) -> tuple[tuple[float, float, dict[str, float]] | None, set[str]]:
    first_start = VOWEL_EDGE_TRIM_S
    last_start = len(samples) / sample_rate_hz - VOWEL_EDGE_TRIM_S - VOWEL_SELECTION_S
    if last_start < first_start:
        return None, {"insufficient_trimmed_vowel_duration"}
    candidates: list[tuple[tuple[float, float, float], float, dict[str, float]]] = []
    rejection_reasons: set[str] = set()
    for start_s in np.arange(first_start, last_start + 1e-9, 0.25):
        region = np.asarray(
            samples[
                round(start_s * sample_rate_hz) : round((start_s + VOWEL_SELECTION_S) * sample_rate_hz)
            ],
            dtype=np.int16,
        )
        signal_reason = _signal_rejection_reason(region)
        if signal_reason:
            rejection_reasons.add(signal_reason)
            continue
        quality = _periodicity_quality(region, sample_rate_hz)
        if quality is None:
            rejection_reasons.add("insufficient_pitch_periods")
            continue
        if quality["voiced_fraction"] < 0.9:
            rejection_reasons.add("insufficient_voiced_coverage")
            continue
        if quality["f0_cv"] > 0.08:
            rejection_reasons.add("unstable_f0")
            continue
        score = (quality["voiced_fraction"], -quality["f0_cv"], -quality["spectral_flatness"])
        candidates.append((score, float(start_s), quality))
    if not candidates:
        return None, rejection_reasons or {"no_stable_voiced_vowel_region"}
    _, start_s, quality = max(candidates, key=lambda candidate: candidate[0])
    return (start_s, start_s + VOWEL_SELECTION_S, quality), rejection_reasons


def _measure_region(region: np.ndarray, sample_rate_hz: int) -> dict[str, Any]:
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return {"status": "unavailable", "reasons": ["install_praat_parselmouth"]}

    try:
        sound = parselmouth.Sound(region.astype(np.float64) / 32768.0, sample_rate_hz)
        pitch = sound.to_pitch_cc(
            pitch_floor=PITCH_FLOOR_HZ,
            pitch_ceiling=PITCH_CEILING_HZ,
        )
        points = call([sound, pitch], "To PointProcess (cc)")
        arguments = (0, 0, _period_floor_s(), _period_ceiling_s(), MAX_PERIOD_FACTOR)
        valid_period_count = int(call(points, "Get number of periods", *arguments))
        if valid_period_count < 5:
            return {"status": "unavailable", "reasons": ["insufficient_pitch_periods"]}
        values = {
            "local_absolute_s": float(call(points, "Get jitter (local, absolute)", *arguments)),
            "local_relative": float(call(points, "Get jitter (local)", *arguments)),
            "rap": float(call(points, "Get jitter (rap)", *arguments)),
            "ppq5": float(call(points, "Get jitter (ppq5)", *arguments)),
            "ddp": float(call(points, "Get jitter (ddp)", *arguments)),
        }
        if not all(math.isfinite(value) for value in values.values()):
            return {"status": "unavailable", "reasons": ["insufficient_pitch_periods"]}
        return {"status": "complete", **values, "valid_period_count": valid_period_count}
    except Exception:
        return {"status": "unavailable", "reasons": ["insufficient_pitch_periods"]}


def _periodicity_quality(region: np.ndarray, sample_rate_hz: int) -> dict[str, float] | None:
    try:
        import parselmouth
    except ImportError:
        return None
    sound = parselmouth.Sound(region.astype(np.float64) / 32768.0, sample_rate_hz)
    pitch = sound.to_pitch_cc(pitch_floor=PITCH_FLOOR_HZ, pitch_ceiling=PITCH_CEILING_HZ)
    frequencies = np.asarray(pitch.selected_array["frequency"], dtype=np.float64)
    voiced = frequencies[frequencies > 0]
    if len(voiced) < 5:
        return None
    power = np.abs(np.fft.rfft(region.astype(np.float64))) ** 2
    positive = power[1:] + np.finfo(float).tiny
    flatness = float(np.exp(np.mean(np.log(positive))) / np.mean(positive))
    mean_f0 = float(np.mean(voiced))
    return {
        "voiced_fraction": float(len(voiced) / len(frequencies)),
        "f0_mean_hz": mean_f0,
        "f0_cv": float(np.std(voiced) / mean_f0),
        "spectral_flatness": flatness,
    }


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
    power = np.abs(np.fft.rfft(normalized)) ** 2
    positive = power[1:] + np.finfo(float).tiny
    flatness = float(np.exp(np.mean(np.log(positive))) / np.mean(positive))
    if flatness > 0.5:
        return "spectral_flatness_above_0_5"
    return None


def _period_floor_s() -> float:
    return 0.8 / PITCH_CEILING_HZ


def _period_ceiling_s() -> float:
    return 1.25 / PITCH_FLOOR_HZ


def _metric_names() -> tuple[str, ...]:
    return "local_absolute_s", "local_relative", "rap", "ppq5", "ddp"


def _provenance() -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "analyzer": "praat_vocal_jitter",
        "pitch_method": "raw_cross_correlation",
        "pulse_method": "sound_and_pitch_cross_correlation",
        "pitch_floor_hz": PITCH_FLOOR_HZ,
        "pitch_ceiling_hz": PITCH_CEILING_HZ,
        "period_floor_s": _period_floor_s(),
        "period_ceiling_s": _period_ceiling_s(),
        "maximum_period_factor": MAX_PERIOD_FACTOR,
    }
    try:
        import parselmouth

        provenance["parselmouth_version"] = parselmouth.VERSION
        provenance["praat_version"] = parselmouth.PRAAT_VERSION
        provenance["praat_version_date"] = parselmouth.PRAAT_VERSION_DATE
    except ImportError:
        provenance["parselmouth_version"] = None
        provenance["praat_version"] = None
        provenance["praat_version_date"] = None
    return provenance
