from __future__ import annotations

import io

import av
import numpy as np
import pytest
from scipy.io import wavfile

from demo.audio_web_app import create_app
from ml.src.audio_fixtures import tone
from ml.src.audio_recording import (
    AudioRecordingError,
    analyze_audio_upload,
    analyze_wav_upload,
    decode_audio,
    decode_wav,
)
from ml.src.transcription import TranscriptSegment, TranscriptionResult, TranscriptionStatus


def _wav_bytes(samples: np.ndarray, sample_rate_hz: int = 16_000) -> bytes:
    output = io.BytesIO()
    wavfile.write(output, sample_rate_hz, samples)
    return output.getvalue()


def _mp3_bytes(samples: np.ndarray, sample_rate_hz: int = 16_000) -> bytes:
    output = io.BytesIO()
    with av.open(output, mode="w", format="mp3") as container:
        stream = container.add_stream("mp3", rate=sample_rate_hz)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = sample_rate_hz
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
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


def test_decodes_and_analyzes_real_mp3_upload() -> None:
    source = _mp3_bytes(tone(16_000, duration_s=4.0))
    decoded = decode_audio(source)
    assert decoded.sample_rate_hz == 16_000
    assert decoded.channels == 1
    assert decoded.duration_s == pytest.approx(4.0, abs=0.05)
    assert "mp3" in decoded.source_dtype
    result = analyze_audio_upload(source, "tone.mp3")
    assert result["filename"] == "tone.mp3"
    assert result["overall_status"] == "usable"
    assert result["window_count"] == 2


def test_balances_windows_instead_of_creating_a_short_tail() -> None:
    result = analyze_wav_upload(_wav_bytes(tone(16_000, duration_s=10.5)), "long-tone.wav")
    durations = [window["end_s"] - window["start_s"] for window in result["windows"]]
    assert result["window_count"] == 6
    assert durations == pytest.approx([1.75] * 6)
    assert all(window["status"] == "usable" for window in result["windows"])


def test_rejects_unsupported_audio_upload() -> None:
    with pytest.raises(AudioRecordingError, match="readable WAV or MP3"):
        decode_audio(b"not audio")


def test_web_page_renders_upload_and_results() -> None:
    client = create_app(testing=True).test_client()
    empty_page = client.get("/")
    assert empty_page.status_code == 200
    assert b"Select a WAV or MP3 file" in empty_page.data

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
    assert b"not a readable WAV or MP3 recording" in response.data


def test_web_page_accepts_mp3_upload() -> None:
    client = create_app(testing=True).test_client()
    response = client.post(
        "/",
        data={
            "audio": (io.BytesIO(_mp3_bytes(tone(16_000, duration_s=2.0))), "voice.mp3"),
            "consent": "yes",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"voice.mp3" in response.data
    assert b"data:audio/mpeg;base64" in response.data


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
