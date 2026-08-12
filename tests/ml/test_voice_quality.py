from __future__ import annotations

import sys

import numpy as np
import pytest

from ml.src.voice_quality import (
    PITCH_CEILING_HZ,
    PITCH_FLOOR_HZ,
    analyze_sustained_vowel,
    analyze_vocal_jitter_regions,
)


SAMPLE_RATE = 16_000


def _steady_vowel(duration_s: float = 4.0) -> np.ndarray:
    time = np.arange(round(duration_s * SAMPLE_RATE)) / SAMPLE_RATE
    return (0.15 * np.sin(2 * np.pi * 180 * time) * 32767).astype(np.int16)


def _perturbed_vowel(duration_s: float = 4.0) -> np.ndarray:
    time = np.arange(round(duration_s * SAMPLE_RATE)) / SAMPLE_RATE
    frequency = 180 + 6 * np.sin(2 * np.pi * 5 * time)
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    return (0.15 * np.sin(phase) * 32767).astype(np.int16)


def _unstable_vowel(duration_s: float = 4.0) -> np.ndarray:
    time = np.arange(round(duration_s * SAMPLE_RATE)) / SAMPLE_RATE
    frequency = 190 + 80 * np.sin(2 * np.pi * 1.5 * time)
    phase = 2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    return (0.15 * np.sin(phase) * 32767).astype(np.int16)


def test_uses_praat_voice_analysis_period_limits_and_golden_values() -> None:
    result = analyze_vocal_jitter_regions(
        _steady_vowel(), SAMPLE_RATE, ((0.0, 4.0),)
    )

    assert result["status"] == "complete"
    assert result["local_absolute_s"] == pytest.approx(1.407936096e-8, rel=0.02)
    assert result["local_relative"] == pytest.approx(2.534283959e-6, rel=0.02)
    assert result["valid_period_count"] == pytest.approx(717, abs=2)
    assert result["ddp"] == pytest.approx(3 * result["rap"])
    provenance = result["provenance"]
    assert provenance["pitch_method"] == "raw_cross_correlation"
    assert provenance["pulse_method"] == "sound_and_pitch_cross_correlation"
    assert provenance["period_floor_s"] == 0.8 / PITCH_CEILING_HZ
    assert provenance["period_ceiling_s"] == 1.25 / PITCH_FLOOR_HZ
    assert provenance["parselmouth_version"]
    assert provenance["praat_version"]


def test_period_perturbation_increases_praat_jitter() -> None:
    steady = analyze_vocal_jitter_regions(_steady_vowel(), SAMPLE_RATE, ((0.0, 4.0),))
    perturbed = analyze_vocal_jitter_regions(
        _perturbed_vowel(), SAMPLE_RATE, ((0.0, 4.0),)
    )

    assert perturbed["local_relative"] > steady["local_relative"] * 100
    assert perturbed["local_absolute_s"] > steady["local_absolute_s"] * 100


def test_missing_parselmouth_returns_an_unavailable_reason(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "parselmouth", None)

    result = analyze_vocal_jitter_regions(
        _steady_vowel(), SAMPLE_RATE, ((0.0, 4.0),)
    )

    assert result["status"] == "unavailable"
    assert result["reasons"] == ["install_praat_parselmouth"]


def test_regions_are_aggregated_by_valid_period_count() -> None:
    samples = np.concatenate((_steady_vowel(2.0), _perturbed_vowel(2.0)))
    first = analyze_vocal_jitter_regions(samples, SAMPLE_RATE, ((0.0, 2.0),))
    second = analyze_vocal_jitter_regions(samples, SAMPLE_RATE, ((2.0, 4.0),))
    combined = analyze_vocal_jitter_regions(
        samples, SAMPLE_RATE, ((0.0, 2.0), (2.0, 4.0))
    )
    expected = (
        first["valid_period_count"] * first["local_relative"]
        + second["valid_period_count"] * second["local_relative"]
    ) / (first["valid_period_count"] + second["valid_period_count"])

    assert combined["valid_region_count"] == 2
    assert combined["local_relative"] == pytest.approx(expected)


def test_selects_clean_two_second_sustained_vowel_region() -> None:
    result = analyze_sustained_vowel(_steady_vowel(), SAMPLE_RATE)

    assert result["status"] == "complete"
    assert result["measurement_context"] == "controlled_sustained_vowel"
    assert result["selected_start_s"] >= 0.5
    assert result["selected_end_s"] <= 3.5
    assert result["selected_end_s"] - result["selected_start_s"] == pytest.approx(2.0)
    assert result["selected_voiced_fraction"] >= 0.9


@pytest.mark.parametrize(
    ("samples", "reason"),
    [
        (_steady_vowel(2.9), "vowel_duration_below_3s"),
        (_steady_vowel(8.1), "vowel_duration_above_8s"),
        (np.zeros(4 * SAMPLE_RATE, dtype=np.int16), "insufficient_signal_energy"),
        (np.full(4 * SAMPLE_RATE, 32767, dtype=np.int16), "clip_fraction_above_1pct"),
        (
            np.random.default_rng(7).integers(
                -8000, 8000, 4 * SAMPLE_RATE, dtype=np.int16
            ),
            "spectral_flatness_above_0_5",
        ),
        (_unstable_vowel(), "unstable_f0"),
    ],
)
def test_sustained_vowel_reports_quality_abstentions(
    samples: np.ndarray, reason: str
) -> None:
    result = analyze_sustained_vowel(samples, SAMPLE_RATE)

    assert result["status"] == "unavailable"
    assert reason in result["reasons"]
