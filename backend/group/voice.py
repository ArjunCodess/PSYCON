"""Session-local voice features tied to visible, numbered faces."""

from __future__ import annotations

import os
import math
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np

from ml.src.voice_quality import analyze_vocal_jitter_regions, unavailable_vocal_jitter


VECTOR_SIZE = 32
SCALAR_NAMES = ("speaking_duration_s", "turn_count", "overlap_refused_s", "pause_total_s", "word_rate_wpm", "pitch_jitter_relative")
OPTIONAL_SCALARS = frozenset({"word_rate_wpm", "pitch_jitter_relative", "overlap_refused_s"})
MAX_WINDOW_S = 2.0
MIN_MOTION = 0.55
MAX_VOICE_CLIP_S = 10.0


def sample_window_frames(source: bytes | Path, start_s: float, end_s: float) -> list[np.ndarray]:
    """Sample several frames within a speech window without retaining video frames."""
    ffmpeg = shutil.which("ffmpeg")
    if end_s - start_s < 0.3:
        return []
    from .faces import decode_image

    with tempfile.TemporaryDirectory() as directory:
        if isinstance(source, bytes):
            video_path = Path(directory) / "source.mp4"
            video_path.write_bytes(source)
        else:
            video_path = source
        if not ffmpeg:
            import cv2

            video = cv2.VideoCapture(str(video_path))
            if not video.isOpened():
                raise RuntimeError("voice_frame_decode_failed")
            try:
                video.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
                fps = video.get(cv2.CAP_PROP_FPS) or 30.0
                stride = max(1, round(fps / 12))
                count = min(round((end_s - start_s) * fps), round(MAX_WINDOW_S * fps) + 1)
                frames = []
                for index in range(max(0, count)):
                    okay, frame = video.read()
                    if not okay:
                        break
                    if index % stride == 0:
                        height, width = frame.shape[:2]
                        if width > 960:
                            frame = cv2.resize(frame, (960, round(height * 960 / width)))
                        frames.append(frame)
                return frames
            finally:
                video.release()
        output = Path(directory) / "frame-%03d.jpg"
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-nostdin", "-ss", f"{start_s:.6f}", "-t", f"{end_s - start_s:.6f}",
             "-i", str(video_path), "-vf", "fps=12,scale='min(960,iw)':-2", str(output)],
            check=False, capture_output=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError("voice_frame_decode_failed")
        return [frame for path in sorted(Path(directory).glob("frame-*.jpg"))
                if (frame := decode_image(path.read_bytes())) is not None]


def mouth_motion(frames: list[np.ndarray], box: dict) -> float | None:
    changes = _mouth_motion_series(frames, box)
    return float(np.median(changes)) if changes is not None else None


def _mouth_motion_series(frames: list[np.ndarray], box: dict) -> np.ndarray | None:
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
    return np.asarray(changes, dtype=np.float32) if len(changes) >= 2 else None


def _mouth_level_series(frames: list[np.ndarray], box: dict) -> np.ndarray:
    values = []
    for frame in frames:
        height, width = frame.shape[:2]
        x0 = max(0, round(float(box["x"]) * width))
        x1 = min(width, round((float(box["x"]) + float(box["width"])) * width))
        y0 = max(0, round((float(box["y"]) + float(box["height"]) * 0.52) * height))
        y1 = min(height, round((float(box["y"]) + float(box["height"]) * 0.9) * height))
        crop = frame[y0:y1, x0:x1]
        values.append(float(np.mean(crop)) if crop.size else 0.0)
    return np.asarray(values, dtype=np.float32)


def _head_motion_ratio(frames: list[np.ndarray], box: dict) -> float:
    height, width = frames[0].shape[:2]
    x0 = max(0, round(float(box["x"]) * width))
    x1 = min(width, round((float(box["x"]) + float(box["width"])) * width))
    y0 = max(0, round((float(box["y"]) + float(box["height"]) * 0.52) * height))
    y1 = min(height, round((float(box["y"]) + float(box["height"]) * 0.9) * height))
    upper_y0 = max(0, round((float(box["y"]) + float(box["height"]) * 0.1) * height))
    upper_y1 = min(height, round((float(box["y"]) + float(box["height"]) * 0.45) * height))
    lower, upper = [], []
    for previous, current in zip(frames, frames[1:]):
        lower.append(float(np.mean(np.abs(current[y0:y1, x0:x1].astype(np.float32) -
                                          previous[y0:y1, x0:x1].astype(np.float32)))))
        upper.append(float(np.mean(np.abs(current[upper_y0:upper_y1, x0:x1].astype(np.float32) -
                                          previous[upper_y0:upper_y1, x0:x1].astype(np.float32)))))
    return float(np.median(upper) / max(np.median(lower), 1e-9))


@lru_cache(maxsize=1)
def _frontal_face_detector():
    import cv2

    detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if detector.empty():
        raise RuntimeError("face_visibility_detector_unavailable")
    return detector


@lru_cache(maxsize=1)
def _profile_face_detector():
    import cv2

    detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"))
    if detector.empty():
        raise RuntimeError("face_visibility_detector_unavailable")
    return detector


def face_visible(frame: np.ndarray, box: dict) -> bool:
    """Require a frontal face at the saved position before using its mouth crop."""
    import cv2

    height, width = frame.shape[:2]
    x, y, w, h = (float(box[key]) for key in ("x", "y", "width", "height"))
    x0, y0 = max(0, int((x - w * .2) * width)), max(0, int((y - h * .2) * height))
    x1, y1 = min(width, int((x + w * 1.2) * width)), min(height, int((y + h * 1.2) * height))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    found = list(_frontal_face_detector().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20)))
    profile = _profile_face_detector()
    found.extend(profile.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)))
    for dx, dy, dw, dh in profile.detectMultiScale(cv2.flip(gray, 1), scaleFactor=1.1,
                                                   minNeighbors=3, minSize=(20, 20)):
        found.append((gray.shape[1] - dx - dw, dy, dw, dh))
    for dx, dy, dw, dh in found:
        overlap_w = max(0.0, min(x1, x0 + dx + dw, (x + w) * width) - max(x0 + dx, x * width))
        overlap_h = max(0.0, min(y1, y0 + dy + dh, (y + h) * height) - max(y0 + dy, y * height))
        intersection = overlap_w * overlap_h
        union = w * width * h * height + dw * dh - intersection
        if union > 0 and intersection / union >= .5:
            return True
    return False


def assign_windows(turns: list[dict], boxes: list[dict], data: bytes, *, frame_sampler=None, face_checker=None) -> list[dict]:
    checker = face_checker or face_visible
    if frame_sampler is not None:
        return _assign_windows(turns, boxes, data, frame_sampler, checker)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        source.write_bytes(data)
        return _assign_windows(turns, boxes, source, sample_window_frames, checker)


def _assign_windows(turns: list[dict], boxes: list[dict], source: bytes | Path, frame_sampler, face_checker) -> list[dict]:
    rows = []
    for index, turn in enumerate(turns):
        start, end = float(turn["start_s"]), float(turn["end_s"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            continue
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
        # An energy segment may span several speakers. Never extrapolate motion
        # observed in a short excerpt to the rest of that segment.
        count = 1 if overlaps else max(1, math.ceil((end - start) / MAX_WINDOW_S))
        for window in range(count):
            left = start + (end - start) * window / count
            right = start + (end - start) * (window + 1) / count
            slot, confidence = None, 0.0
            if not overlaps:
                frames = frame_sampler(source, left, right)
                checked_frames = [frames[0], frames[len(frames) // 2], frames[-1]] if frames else []
                series = {int(box["slot_number"]): _mouth_motion_series(frames, box) for box in boxes}
                measured = [(slot_number, float(np.median(values)) if values is not None else None)
                            for slot_number, values in series.items()]
                if measured and all(value is not None for _, value in measured):
                    ranked = sorted(measured, key=lambda pair: pair[1], reverse=True)
                    best = ranked[0][1]
                    second = ranked[1][1] if len(ranked) > 1 else 0.0
                    winning_box = next(box for box in boxes if int(box["slot_number"]) == ranked[0][0])
                    visible = checked_frames and sum(bool(face_checker(frame, winning_box)) for frame in checked_frames) >= 2
                    together = False
                    if second >= 0.1:
                        second_box = next(box for box in boxes if int(box["slot_number"]) == ranked[1][0])
                        first_levels = _mouth_level_series(frames, winning_box)
                        second_levels = _mouth_level_series(frames, second_box)
                        if np.std(first_levels) > 0.5 and np.std(second_levels) > 0.5:
                            together = float(np.corrcoef(first_levels, second_levels)[0, 1]) >= 0.8
                    stable_head = _head_motion_ratio(frames, winning_box) <= 0.82
                    if visible and stable_head and not together and best >= MIN_MOTION and best >= second * 1.8 and best - second >= 0.35:
                        slot = ranked[0][0]
                        confidence = float(min(1.0, (best - second) / max(best, 1e-9)))
            rows.append({"id": str(uuid4()), "start_s": left, "end_s": right,
                         "source_turn_index": index,
                         "cluster_label": turn.get("cluster_label"), "overlap_refused_s": overlap_seconds,
                         "slot_number": slot,
                         "confidence": confidence, "status": "assigned" if slot is not None else "unknown"})
    return rows


def _spectral_vector(samples: np.ndarray) -> list[float]:
    spectrum = np.zeros(257, dtype=np.float64)
    count = 0
    window = np.hanning(512)
    for index in range(0, len(samples) - 511, 256):
        signal = samples[index:index + 512].astype(np.float32) / 32768.0
        spectrum += np.abs(np.fft.rfft(signal * window))
        count += 1
    if not count:
        return [0.0] * VECTOR_SIZE
    bands = np.array_split(np.log1p(spectrum / count), VECTOR_SIZE)
    vector = np.asarray([float(np.mean(band)) for band in bands], dtype=np.float32)
    return (vector / max(float(np.linalg.norm(vector)), 1e-9)).tolist()


def _usable_interval(samples: np.ndarray) -> bool:
    total, squared, clipped = 0.0, 0.0, 0
    for offset in range(0, len(samples), 160_000):
        chunk = samples[offset:offset + 160_000].astype(np.float64)
        total += float(chunk.sum())
        squared += float(np.dot(chunk, chunk))
        clipped += int(np.count_nonzero(np.abs(chunk) >= 32760))
    size = len(samples)
    return bool(size and max(0.0, squared / size - (total / size) ** 2) >= 80 ** 2 and clipped / size < .01)


def _profile_embedding(embedder, audio: np.ndarray, rate: int) -> list[float]:
    # ECAPA activations grow with duration. Use bounded excerpts spread through
    # the assigned audio, never a multi-hour tensor.
    clip_size = min(len(audio), int(MAX_VOICE_CLIP_S * rate))
    starts = np.linspace(0, len(audio) - clip_size, min(6, math.ceil(len(audio) / clip_size)), dtype=int)
    vectors = [np.asarray(embedder.embed(audio[start:start + clip_size], rate), dtype=np.float32).reshape(-1)
               for start in starts]
    vector = np.mean(np.stack(vectors), axis=0)
    norm = float(np.linalg.norm(vector))
    if not vector.size or not np.all(np.isfinite(vector)) or norm <= 0:
        raise ValueError("invalid_speaker_embedding")
    return (vector / norm).astype(float).tolist()


def _jitter_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    clips = []
    for start, end in intervals:
        count = max(1, math.ceil((end - start) / MAX_VOICE_CLIP_S))
        clips.extend((start + i * (end - start) / count, start + (i + 1) * (end - start) / count)
                     for i in range(count) if (end - start) / count >= 1.0)
    return [clips[index] for index in np.linspace(0, len(clips) - 1, min(12, len(clips)), dtype=int)] if clips else []


def _embedding_available() -> bool:
    if os.getenv("HF_TOKEN"):
        return True
    # SpeechBrain's public model can already be cached without a diarization
    # token. Check the complete cache without triggering a network download.
    try:
        from huggingface_hub import try_to_load_from_cache

        return all(isinstance(try_to_load_from_cache("speechbrain/spkrec-ecapa-voxceleb", name), str)
                   for name in ("hyperparams.yaml", "embedding_model.ckpt", "classifier.ckpt",
                                "mean_var_norm_emb.ckpt", "label_encoder.txt"))
    except (ImportError, OSError):
        return False


def build_profiles(samples: np.ndarray, sample_rate_hz: int, segments: list[dict],
                   boxes: list[dict], transcript: list[dict], *, embedder=None) -> list[dict]:
    if sample_rate_hz != 16000:
        raise ValueError("voice profiles require 16 kHz PCM")
    profiles = []
    embedding_enabled = embedder is not None or _embedding_available()
    cluster_slots: dict[str, set[int]] = {}
    for segment in segments:
        if segment.get("status") == "assigned" and segment.get("cluster_label") and segment.get("slot_number") is not None:
            cluster_slots.setdefault(str(segment["cluster_label"]), set()).add(int(segment["slot_number"]))
    for box in boxes:
        slot = int(box["slot_number"])
        assigned = sorted((row for row in segments if row["slot_number"] == slot and row["status"] == "assigned"),
                          key=lambda row: row["start_s"])
        recording_end = len(samples) / sample_rate_hz
        intervals = [(max(0.0, float(row["start_s"])), min(recording_end, float(row["end_s"])))
                     for row in assigned if float(row["end_s"]) > 0 and float(row["start_s"]) < recording_end]
        intervals = _merge_intervals([(start, end) for start, end in intervals if end > start])
        clean_intervals = []
        for start, end in intervals:
            region = samples[round(start * sample_rate_hz):round(end * sample_rate_hz)]
            if _usable_interval(region):
                clean_intervals.append((start, end))
        intervals = clean_intervals
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
                embedding = _profile_embedding(embedder, audio, sample_rate_hz)
                embedding_engine = embedder.engine_name
        except Exception:
            embedding_enabled = False
        matched_transcript = [row for row in transcript
                              if any(float(row["start_s"]) >= start and float(row["end_s"]) <= end
                                     for start, end in intervals)
                              and float(row["end_s"]) > float(row["start_s"])]
        words = sum(len(str(row.get("text") or "").split()) for row in matched_transcript)
        transcript_seconds = sum(end - start for start, end in _merge_intervals([
            (float(row["start_s"]), float(row["end_s"])) for row in matched_transcript
            if str(row.get("text") or "").strip()
        ]))
        # Long gaps contain other participants' turns; they are not a pause
        # made by this face's speaker.
        pauses = sum(gap for left, right in zip(intervals, intervals[1:])
                     if 0 < (gap := right[0] - left[1]) <= 2.0)
        assigned_clusters = {cluster for cluster, slots in cluster_slots.items() if slots == {slot}}
        refused = sum(float(row.get("overlap_refused_s") or 0.0) for row in segments
                      if row.get("cluster_label") in assigned_clusters)
        # With no unique visual match for a cluster, overlap cannot be attributed
        # to a face. Preserve that uncertainty instead of manufacturing zero.
        if any(row.get("overlap_refused_s", 0) > 0 for row in segments) and not assigned_clusters:
            refused = None
        try:
            jitter = analyze_vocal_jitter_regions(samples, sample_rate_hz, _jitter_intervals(intervals))
        except Exception as exc:
            jitter = unavailable_vocal_jitter(type(exc).__name__, context="conversational_research_estimate")
        turn_count = len({row["source_turn_index"] if row.get("source_turn_index") is not None
                          else (row["start_s"], row["end_s"])
                          for row in assigned
                          if any(start < row["end_s"] and row["start_s"] < end for start, end in intervals)})
        base.update(engine=voice_engine, vector=vector, embedding=embedding,
                    embedding_engine=embedding_engine, status="ready", metrics={
            "speaking_duration_s": usable, "turn_count": turn_count, "overlap_refused_s": refused,
            "pause_total_s": pauses, "word_rate_wpm": words / transcript_seconds * 60 if transcript_seconds else None,
            "transcript_coverage_s": transcript_seconds,
            "pitch_jitter_relative": jitter.get("pitch_jitter_relative") if jitter.get("status") == "complete" else None,
            "jitter": jitter,
        })
        profiles.append(base)
    return profiles


def training_feature(face: list[float], profile: dict) -> list[float] | None:
    if profile.get("status") != "ready" or len(profile.get("vector") or []) != VECTOR_SIZE:
        return None
    metrics = profile.get("metrics") or {}
    try:
        feature = [*map(float, face), *map(float, profile["vector"])]
        for name in SCALAR_NAMES:
            value = metrics.get(name)
            if value is None:
                if name not in OPTIONAL_SCALARS:
                    return None
                feature.extend([-1.0, 1.0])  # value abstained, explicit missing flag
            else:
                scalar = float(value)
                if scalar < 0 or not math.isfinite(scalar):
                    return None
                feature.extend([scalar, 0.0])
    except (TypeError, ValueError, OverflowError):
        return None
    return feature if len(face) == 80 and all(math.isfinite(value) for value in feature) else None


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
