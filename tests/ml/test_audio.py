from __future__ import annotations

import numpy as np
import pytest

from ml.src.audio import AudioProvenance, AudioStatus, FEATURE_NAMES, analyze_audio_packet, analyze_pcm16
from ml.src.audio_fixtures import all_fixtures, tone
from protocol.chunk import encode_chunk_v2
from demo.audio_week3_demo import run_demo


SAMPLE_RATE = 16_000


def _packet(samples: np.ndarray) -> bytes:
    return encode_chunk_v2(
        stream_type="audio_pcm",
        device_id=19,
        sequence=7,
        device_timestamp_us=1_750_000,
        sample_count=len(samples),
        sample_period_us=62,
        payload=samples.astype("<i2").tobytes(),
    )


def test_deterministic_fixtures_cover_week_three_cases() -> None:
    fixtures = all_fixtures(SAMPLE_RATE)
    assert set(fixtures) == {"silence", "impulse", "tone", "clipping", "speech_like", "noise"}
    assert all(value.dtype == np.int16 and len(value) == 2 * SAMPLE_RATE for value in fixtures.values())
    assert np.array_equal(fixtures["noise"], all_fixtures(SAMPLE_RATE)["noise"])


def test_known_tone_is_usable_and_has_expected_frequency() -> None:
    result = analyze_pcm16(tone(SAMPLE_RATE), SAMPLE_RATE)
    assert result.status is AudioStatus.USABLE
    assert tuple(result.features) == FEATURE_NAMES
    assert result.features["duration_s"] == pytest.approx(2.0)
    assert result.features["f0_hz"] == pytest.approx(220.0, abs=3.0)
    assert result.features["f0_std_hz"] < 3.0
    assert result.features["f0_min_hz"] == pytest.approx(220.0, abs=3.0)
    assert result.features["f0_max_hz"] == pytest.approx(220.0, abs=3.0)
    assert result.features["voice_stability"] > 0.98
    assert result.features["rms_dbfs"] == pytest.approx(-12.13, abs=0.2)


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("silence", AudioStatus.INSUFFICIENT),
        ("impulse", AudioStatus.INSUFFICIENT),
        ("clipping", AudioStatus.CLIPPED),
        ("noise", AudioStatus.NOISY),
    ],
)
def test_bad_audio_abstains(fixture_name: str, expected_status: AudioStatus) -> None:
    result = analyze_pcm16(all_fixtures(SAMPLE_RATE)[fixture_name], SAMPLE_RATE)
    assert result.status is expected_status
    assert result.status is not AudioStatus.USABLE
    assert result.reasons


def test_speech_like_fixture_exposes_prosody_features() -> None:
    result = analyze_pcm16(all_fixtures(SAMPLE_RATE)["speech_like"], SAMPLE_RATE)
    assert result.status is AudioStatus.USABLE
    assert result.features["f0_hz"] == pytest.approx(180.0, abs=4.0)
    assert result.features["voiced_fraction"] > 0.5
    assert result.features["pause_duration_s"] >= 0.0
    assert 0.0 <= result.features["voice_stability"] <= 1.0


def test_packet_analysis_preserves_source_provenance() -> None:
    samples = tone(SAMPLE_RATE)
    packet = _packet(samples)
    result = analyze_audio_packet(
        packet,
        session_id="demo-session",
        first_sample_index=32_000,
        nominal_sample_rate_hz=SAMPLE_RATE,
    )
    assert result.status is AudioStatus.USABLE
    assert isinstance(result.provenance, AudioProvenance)
    assert result.provenance.session_id == "demo-session"
    assert result.provenance.device_id == 19
    assert result.provenance.sequence == 7
    assert result.provenance.first_sample_index == 32_000
    assert result.provenance.sample_count == len(samples)
    assert len(result.provenance.source_sha256) == 64


def test_missing_and_corrupt_packets_have_explicit_outcomes() -> None:
    missing = analyze_audio_packet(None, session_id="demo-session")
    corrupt = analyze_audio_packet(b"not a protocol packet", session_id="demo-session")
    wrong_shape = analyze_pcm16(np.zeros((2, 2), dtype=np.int16), SAMPLE_RATE)
    assert missing.status is AudioStatus.MISSING
    assert corrupt.status is AudioStatus.CORRUPT
    assert wrong_shape.status is AudioStatus.CORRUPT


def test_demo_writes_all_decisions(tmp_path) -> None:
    output = tmp_path / "audio_demo.json"
    rows = run_demo(output)
    assert output.is_file()
    assert {row["case"] for row in rows} == {
        "silence", "impulse", "tone", "clipping", "speech_like", "noise", "missing", "corrupt"
    }
    assert {row["status"] for row in rows} >= {
        "usable", "insufficient_audio", "clipped", "too_noisy", "missing_audio", "corrupt"
    }
