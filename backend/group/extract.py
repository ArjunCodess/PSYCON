"""Turn one group video into audio, frames, anonymous clusters, and a transcript.

Diarization is attempted first. If that model is unavailable, energy segments are
kept under their own name and are not treated as participant identities.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .processing import PROCESSING_VERSION, build_processing_baseline


def extract_group_recording(data: bytes, recording: dict) -> dict:
    reasons: list[str] = []
    duration_s = float(recording["duration_s"])
    samples, sample_rate, audio_wav = _audio_from_video(data, reasons)
    turns: list[dict] = []
    engine = None
    if samples is not None:
        diarized, diarization_reason = _diarize(samples, sample_rate)
        if diarization_reason:
            reasons.append(diarization_reason)
        if diarized:
            turns = diarized
            engine = turns[0]["engine"]
        else:
            turns = _energy_segments(samples, sample_rate)
            engine = "unverified_energy_segments_v2"
            if turns:
                reasons.append("diarization_replaced_by_unverified_energy_segments")
            else:
                reasons.append("no_speech_segments")
    transcript = _transcribe(samples, sample_rate, turns, reasons) if samples is not None else []
    frames, thumbnail = _frames_from_video(data, duration_s, reasons)
    derived = build_processing_baseline(
        source_sha256=recording["sha256"],
        duration_s=duration_s,
        samples=samples,
        sample_rate_hz=sample_rate,
        turns=turns,
        transcript=transcript,
        frames=frames,
        seat_count=0,
        diarization_engine=engine,
        failure_reasons=reasons,
    )
    derived["tool_version"] = PROCESSING_VERSION
    derived["audio_wav"] = audio_wav
    derived["thumbnail_jpeg"] = thumbnail
    derived["pcm_samples"] = samples
    derived["sample_rate_hz"] = sample_rate
    return derived


def _audio_from_video(data: bytes, reasons: list[str]) -> tuple[np.ndarray | None, int | None, bytes | None]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        reasons.append("audio_extraction_failed:ffmpeg_missing")
        reasons.append("audio_samples_not_extracted")
        return None, None, None
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        target = Path(directory) / "audio.wav"
        source.write_bytes(data)
        completed = subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0 or not target.exists():
            reasons.append("audio_extraction_failed:ffmpeg")
            reasons.append("audio_samples_not_extracted")
            return None, None, None
        with wave.open(str(target), "rb") as handle:
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).copy()
        return samples, rate, target.read_bytes()


def _frames_from_video(data: bytes, duration_s: float, reasons: list[str]) -> tuple[list[dict], bytes | None]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        reasons.append("frame_sampling_unavailable:ffmpeg_missing")
        return [], None
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        source.write_bytes(data)
        folder = Path(directory) / "frames"
        folder.mkdir()
        completed = subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-vf", "fps=1/30", "-frames:v", "8", str(folder / "frame-%02d.jpg")],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            reasons.append("frame_sampling_unavailable:ffmpeg")
            return [], None
        paths = sorted(folder.glob("frame-*.jpg"))
        frames = []
        for index, path in enumerate(paths):
            frames.append({"time_s": min(duration_s, index * 30.0), "visible_slots": []})
        thumbnail = paths[0].read_bytes() if paths else None
        if thumbnail is None:
            reasons.append("thumbnail_not_created")
        return frames, thumbnail


def _diarize(samples: np.ndarray, sample_rate: int) -> tuple[list[dict] | None, str | None]:
    try:
        from ml.src.speaker_analysis import PyannoteDiarizer

        result = PyannoteDiarizer().diarize(samples, sample_rate)
    except Exception as exc:
        return None, f"diarization_unavailable:{type(exc).__name__}"
    turns = []
    for turn in result.regular_turns:
        label = str(turn.speaker_id)
        if label.lower().startswith("participant"):
            label = f"cluster-{label}"
        turns.append(
            {
                "cluster_label": label,
                "start_s": float(turn.start_s),
                "end_s": float(turn.end_s),
                "overlap": False,
                "engine": result.engine,
            }
        )
    _mark_overlap(turns)
    return turns, None


def _energy_segments(samples: np.ndarray, sample_rate: int) -> list[dict]:
    frame = max(1, int(sample_rate * 0.03))
    length = len(samples) // frame
    if not length:
        return []
    levels = np.fromiter(
        (float(np.sqrt(np.mean(samples[index * frame:(index + 1) * frame].astype(np.float64) ** 2)))
         for index in range(length)),
        dtype=np.float64, count=length,
    )
    # A single shout or microphone knock must not set the threshold for the
    # entire discussion. Smooth short syllable gaps before extracting turns.
    threshold = max(80.0, min(400.0, float(np.percentile(levels, 25)) * 2.0))
    active = np.convolve(levels, np.ones(5) / 5, mode="same") >= threshold
    edges = np.flatnonzero(np.diff(np.r_[False, active, False].astype(np.int8)))
    merged: list[tuple[int, int]] = []
    max_gap = max(1, round(0.36 * sample_rate / frame))
    for start, end in zip(edges[::2], edges[1::2]):
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((int(start), int(end)))
    segments = [(start, end) for start, end in merged if end - start >= round(0.6 * sample_rate / frame)]
    turns = []
    for index, (start, end) in enumerate(segments, start=1):
        turns.append(
            {
                "cluster_label": f"segment-{index}",
                "start_s": start * frame / sample_rate,
                "end_s": end * frame / sample_rate,
                "overlap": False,
                "engine": "unverified_energy_segments_v2",
            }
        )
    return turns


def _transcribe(samples: np.ndarray, sample_rate: int, turns: list[dict], reasons: list[str]) -> list[dict]:
    try:
        from ml.src.audio import analyze_pcm16
        from ml.src.transcription import FasterWhisperTranscriber, transcribe_usable_regions

        analysis = analyze_pcm16(samples, sample_rate)
        if analysis.status.value != "usable":
            reasons.append("transcription_skipped_quality")
            return []
        result = transcribe_usable_regions(
            samples,
            sample_rate,
            [{"start_s": 0.0, "end_s": len(samples) / sample_rate, "status": "usable"}],
            FasterWhisperTranscriber(),
        )
    except Exception as exc:
        reasons.append(f"transcription_unavailable:{type(exc).__name__}")
        return []
    if result.status.value != "complete":
        reasons.extend(result.reasons or [result.status.value])
        return []
    rows = []
    for segment in result.segments:
        cluster = _cluster_at(turns, segment.start_s, segment.end_s)
        rows.append(
            {
                "start_s": segment.start_s,
                "end_s": segment.end_s,
                "cluster_label": cluster,
                "text": segment.text,
            }
        )
    return rows


def _cluster_at(turns: list[dict], start_s: float, end_s: float) -> str | None:
    best = None
    best_overlap = 0.0
    for turn in turns:
        overlap = min(end_s, turn["end_s"]) - max(start_s, turn["start_s"])
        if overlap > best_overlap:
            best = turn["cluster_label"]
            best_overlap = overlap
    return best


def _mark_overlap(turns: list[dict]) -> None:
    for index, left in enumerate(turns):
        for right in turns[index + 1 :]:
            if left["cluster_label"] == right["cluster_label"]:
                continue
            if left["start_s"] < right["end_s"] and right["start_s"] < left["end_s"]:
                left["overlap"] = True
                right["overlap"] = True
