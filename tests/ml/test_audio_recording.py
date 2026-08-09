from __future__ import annotations

import io

import numpy as np
import pytest
from scipy.io import wavfile

from demo.audio_web_app import create_app
from ml.src.audio_fixtures import tone
from ml.src.audio_recording import AudioRecordingError, analyze_wav_upload, decode_wav
from ml.src.transcription import TranscriptSegment, TranscriptionResult, TranscriptionStatus


def _wav_bytes(samples: np.ndarray, sample_rate_hz: int = 16_000) -> bytes:
    output = io.BytesIO()
    wavfile.write(output, sample_rate_hz, samples)
    return output.getvalue()


class FakeWebTranscriber:
    @property
    def engine_name(self) -> str:
        return "fake-web-transcriber"

    def transcribe(self, samples: np.ndarray, sample_rate_hz: int) -> TranscriptionResult:
        return TranscriptionResult(
            status=TranscriptionStatus.COMPLETE,
            text="I feel calm and good today.",
            language="en",
            language_confidence=0.98,
            confidence=0.91,
            segments=(TranscriptSegment(0.1, 1.7, "I feel calm and good today.", 0.91, 1600, 27200),),
            engine=self.engine_name,
        )


def test_decodes_stereo_wav_and_resamples_to_pipeline_format() -> None:
    mono = tone(8_000, duration_s=1.5)
    stereo = np.column_stack((mono, mono // 2))
    decoded = decode_wav(_wav_bytes(stereo, 8_000))
    assert decoded.original_sample_rate_hz == 8_000
    assert decoded.sample_rate_hz == 16_000
    assert decoded.channels == 2
    assert decoded.samples.dtype == np.int16
    assert len(decoded.samples) == pytest.approx(24_000, abs=2)


def test_real_wav_upload_runs_as_protocol_windows() -> None:
    result = analyze_wav_upload(_wav_bytes(tone(16_000, duration_s=4.0)), "tone.wav")
    assert result["overall_status"] == "usable"
    assert result["extractor"] == "psycon_audio"
    assert result["window_count"] == 2
    assert all(window["status"] == "usable" for window in result["windows"])
    assert all(window["features"]["f0_hz"] == pytest.approx(220, abs=3) for window in result["windows"])
    assert len(result["source_sha256"]) == 64


def test_balances_windows_instead_of_creating_a_short_tail() -> None:
    result = analyze_wav_upload(_wav_bytes(tone(16_000, duration_s=10.5)), "long-tone.wav")
    durations = [window["end_s"] - window["start_s"] for window in result["windows"]]
    assert result["window_count"] == 6
    assert durations == pytest.approx([1.75] * 6)
    assert all(window["status"] == "usable" for window in result["windows"])


def test_rejects_non_wav_upload() -> None:
    with pytest.raises(AudioRecordingError, match="readable WAV"):
        decode_wav(b"not audio")


def test_web_page_renders_upload_and_results() -> None:
    client = create_app(testing=True).test_client()
    empty_page = client.get("/")
    assert empty_page.status_code == 200
    assert b"Select a WAV file" in empty_page.data

    response = client.post(
        "/",
        data={
            "audio": (io.BytesIO(_wav_bytes(tone(16_000))), "real-tone.wav"),
            "consent": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"real-tone.wav" in response.data
    assert b"usable" in response.data
    assert b"220.6" in response.data


def test_web_page_shows_invalid_file_error() -> None:
    client = create_app(testing=True).test_client()
    response = client.post(
        "/",
        data={"audio": (io.BytesIO(b"bad wav"), "broken.wav"), "consent": "yes"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert b"not a readable WAV recording" in response.data


def test_web_page_requires_recording_permission() -> None:
    client = create_app(testing=True).test_client()
    response = client.post(
        "/",
        data={"audio": (io.BytesIO(_wav_bytes(tone(16_000))), "tone.wav")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert b"permission to process" in response.data


def test_web_page_renders_transcription_and_language_features() -> None:
    client = create_app(testing=True, transcriber=FakeWebTranscriber()).test_client()
    response = client.post(
        "/",
        data={
            "audio": (io.BytesIO(_wav_bytes(tone(16_000))), "consented.wav"),
            "consent": "yes",
            "transcribe": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"I feel calm and good today" in response.data
    assert b"Vocabulary diversity" in response.data
    assert b"positive" in response.data
