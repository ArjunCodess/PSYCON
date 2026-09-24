"""Session-local voice features tied to visible, numbered faces."""

from __future__ import annotations

import os
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import numpy as np

from ml.src.voice_quality import analyze_vocal_jitter_regions


VECTOR_SIZE = 32
SCALAR_NAMES = ("speaking_duration_s", "turn_count", "overlap_refused_s", "pause_total_s", "word_rate_wpm", "pitch_jitter_relative")


def sample_window_frames(source: bytes | Path, start_s: float, end_s: float) -> list[np.ndarray]:
    """Sample several frames within a speech window without retaining video frames."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or end_s - start_s < 0.3:
        return []
    from .faces import decode_image

    with tempfile.TemporaryDirectory() as directory:
        if isinstance(source, bytes):
            video_path = Path(directory) / "source.mp4"
            video_path.write_bytes(source)
        else:
            video_path = source
        output = Path(directory) / "frame-%03d.jpg"
        sample_start = start_s + max(0.0, (end_s - start_s - 5.0) / 2)
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", f"{sample_start:.3f}", "-t", f"{min(end_s - start_s, 5.0):.3f}",
             "-i", str(video_path), "-vf", "fps=5,scale=320:-2", "-frames:v", "25", str(output)],
            check=False, capture_output=True,
        )
        if result.returncode:
            return []
        return [frame for path in sorted(Path(directory).glob("frame-*.jpg"))
                if (frame := decode_image(path.read_bytes())) is not None]


def mouth_motion(frames: list[np.ndarray], box: dict) -> float | None:
    if len(frames) < 3:
        return None
    height, width = frames[0].shape[:2]
    x0 = max(0, round(float(box["x"]) * width))
    x1 = min(width, round((float(box["x"]) + float(box["width"])) * width))
    y0 = max(0, round((float(box["y"]) + float(box["height"]) * 0.52) * height))
    y1 = min(height, round((float(box["y"]) + float(box["height"]) * 0.9) * height))
    upper_y0 = max(0, round((float(box["y"]) + float(box["height"]) * 0.1) * height))
    upper_y1 = min(height, round((float(box["y"]) + float(box["height"]) * 0.45) * height))
    if x1 - x0 < 4 or y1 - y0 < 3 or upper_y1 - upper_y0 < 3:
        return None
    changes = []
    for previous, current in zip(frames, frames[1:]):
        if previous.shape != current.shape:
            continue
        left = previous[y0:y1, x0:x1].astype(np.float32)
        right = current[y0:y1, x0:x1].astype(np.float32)
        upper_left = previous[upper_y0:upper_y1, x0:x1].astype(np.float32)
        upper_right = current[upper_y0:upper_y1, x0:x1].astype(np.float32)
        changes.append(max(0.0, float(np.mean(np.abs(right - left))) - float(np.mean(np.abs(upper_right - upper_left)))))
    return float(np.median(changes)) if len(changes) >= 2 else None


def assign_windows(turns: list[dict], boxes: list[dict], data: bytes, *, frame_sampler=None) -> list[dict]:
    if frame_sampler is not None:
        return _assign_windows(turns, boxes, data, frame_sampler)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        source.write_bytes(data)
        return _assign_windows(turns, boxes, source, sample_window_frames)


def _assign_windows(turns: list[dict], boxes: list[dict], source: bytes | Path, frame_sampler) -> list[dict]:
    rows = []
    for index, turn in enumerate(turns):
        start, end = float(turn["start_s"]), float(turn["end_s"])
        collision_ranges = sorted(
            (max(start, float(other["start_s"])), min(end, float(other["end_s"])))
            for other_index, other in enumerate(turns) if index != other_index
            and start < float(other["end_s"]) and float(other["start_s"]) < end
        )
        merged = []
        for left, right in collision_ranges:
            if merged and left <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        overlap_seconds = sum(right - left for left, right in merged)
        overlaps = bool(turn.get("overlap")) or overlap_seconds > 0
        if overlaps and not overlap_seconds:
            overlap_seconds = max(0.0, end - start)
        slot, confidence = None, 0.0
        if end > start and not overlaps:
            frames = frame_sampler(source, start, end)
            measured = [(int(box["slot_number"]), mouth_motion(frames, box)) for box in boxes]
            if measured and all(value is not None for _, value in measured):
                ranked = sorted(measured, key=lambda pair: pair[1], reverse=True)
                best = ranked[0][1]
                second = ranked[1][1] if len(ranked) > 1 else 0.0
                if best >= 5.0 and best >= second * 1.75 and best - second >= 3.0:
                    slot = ranked[0][0]
                    confidence = float(min(1.0, (best - second) / max(best, 1e-9)))
        rows.append({"id": str(uuid4()), "start_s": start, "end_s": end,
                     "cluster_label": turn.get("cluster_label"), "overlap_refused_s": overlap_seconds,
                     "slot_number": slot,
                     "confidence": confidence, "status": "assigned" if slot is not None else "unknown"})
    return rows


def _spectral_vector(samples: np.ndarray) -> list[float]:
    signal = samples.astype(np.float32) / 32768.0
    spectrum = np.zeros(257, dtype=np.float64)
    count = 0
    window = np.hanning(512)
    for index in range(0, len(signal) - 511, 256):
        spectrum += np.abs(np.fft.rfft(signal[index:index + 512] * window))
        count += 1
    if not count:
        return [0.0] * VECTOR_SIZE
    bands = np.array_split(np.log1p(spectrum / count), VECTOR_SIZE)
    vector = np.asarray([float(np.mean(band)) for band in bands], dtype=np.float32)
    return (vector / max(float(np.linalg.norm(vector)), 1e-9)).tolist()


def build_profiles(samples: np.ndarray, sample_rate_hz: int, segments: list[dict],
                   boxes: list[dict], transcript: list[dict], *, embedder=None) -> list[dict]:
    if sample_rate_hz != 16000:
        raise ValueError("voice profiles require 16 kHz PCM")
    profiles = []
    embedding_enabled = embedder is not None or bool(os.getenv("HF_TOKEN"))
    cluster_slots: dict[str, set[int]] = {}
    for segment in segments:
        if segment.get("status") == "assigned" and segment.get("cluster_label") and segment.get("slot_number") is not None:
            cluster_slots.setdefault(str(segment["cluster_label"]), set()).add(int(segment["slot_number"]))
    for box in boxes:
        slot = int(box["slot_number"])
        assigned = sorted((row for row in segments if row["slot_number"] == slot), key=lambda row: row["start_s"])
        recording_end = len(samples) / sample_rate_hz
        intervals = [(max(0.0, float(row["start_s"])), min(recording_end, float(row["end_s"])))
                     for row in assigned if float(row["end_s"]) > 0 and float(row["start_s"]) < recording_end]
        intervals = [(start, end) for start, end in intervals if end > start]
        chunks = [samples[round(start * sample_rate_hz):round(end * sample_rate_hz)] for start, end in intervals]
        audio = np.concatenate(chunks).astype(np.int16) if chunks else np.array([], dtype=np.int16)
        usable = len(audio) / sample_rate_hz
        base = {"id": str(uuid4()), "slot_number": slot, "usable_seconds": usable,
                "engine": None, "vector": None, "embedding_engine": None, "embedding": None,
                "metrics": {}, "status": "insufficient_speech"}
        if usable < 3.0:
            profiles.append(base)
            continue
        voice_engine = "numpy_spectral_v1"
        vector = _spectral_vector(audio)
        embedding = None
        embedding_engine = None
        try:
            if embedder is None and embedding_enabled:
                from ml.src.speaker_analysis import SpeechBrainEmbedder
                embedder = SpeechBrainEmbedder()
            if embedding_enabled and embedder is not None:
                candidate = np.asarray(embedder.embed(audio, sample_rate_hz), dtype=np.float32).reshape(-1)
                if candidate.size and np.all(np.isfinite(candidate)):
                    embedding = candidate.astype(float).tolist()
                    embedding_engine = embedder.engine_name
        except Exception:
            embedding_enabled = False
        matched_transcript = [row for row in transcript
                              if any(float(row["start_s"]) >= start and float(row["end_s"]) <= end
                                     for start, end in intervals)]
        words = sum(len(str(row.get("text") or "").split()) for row in matched_transcript)
        pauses = sum(max(0.0, right[0] - left[1]) for left, right in zip(intervals, intervals[1:]))
        assigned_clusters = {cluster for cluster, slots in cluster_slots.items() if slots == {slot}}
        refused = sum(float(row.get("overlap_refused_s") or 0.0) for row in segments
                      if row.get("cluster_label") in assigned_clusters
                      and row.get("cluster_label") is not None)
        jitter = analyze_vocal_jitter_regions(samples, sample_rate_hz,
                                               [region for region in intervals if region[1] - region[0] >= 1.0])
        base.update(engine=voice_engine, vector=vector, embedding=embedding,
                    embedding_engine=embedding_engine, status="ready", metrics={
            "speaking_duration_s": usable, "turn_count": len(intervals), "overlap_refused_s": refused,
            "pause_total_s": pauses, "word_rate_wpm": words / usable * 60 if words else None,
            "pitch_jitter_relative": jitter.get("pitch_jitter_relative"), "jitter": jitter,
        })
        profiles.append(base)
    return profiles


def training_feature(face: list[float], profile: dict) -> list[float] | None:
    if profile.get("status") != "ready" or len(profile.get("vector") or []) != VECTOR_SIZE:
        return None
    metrics = profile.get("metrics") or {}
    if any(metrics.get(name) is None for name in SCALAR_NAMES):
        return None
    feature = [*map(float, face), *map(float, profile["vector"]), *(float(metrics[name]) for name in SCALAR_NAMES)]
    return feature if len(face) == 80 and all(math.isfinite(value) for value in feature) else None
