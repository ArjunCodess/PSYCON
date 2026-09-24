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
MATCHING_VERSION = "face-voice-strict-1"
REVIEW_CLIP_SECONDS = 8.0
MAX_WINDOW_S = 0.8
BOUNDARY_GUARD_S = 0.15
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
        with WindowFrameSampler(source) as sampler:
            return _assign_windows(turns, boxes, source, sampler, checker)


class WindowFrameSampler:
    """Decode chronologically once, keeping only the current short window."""

    def __init__(self, path: Path):
        import cv2

        self.video = cv2.VideoCapture(str(path))
        if not self.video.isOpened():
            self.video.release()
            raise RuntimeError("voice_frame_decode_failed")
        self.pending = None
        self.previous_start = -1.0
        self.previous_timestamp = -1.0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.video.release()

    def __call__(self, _source, start: float, end: float) -> list[np.ndarray]:
        import cv2

        if start < self.previous_start:
            raise ValueError("voice windows must be chronological")
        self.previous_start = start
        frames = []
        next_sample = start
        while True:
            if self.pending is None:
                okay, frame = self.video.read()
                if not okay:
                    break
                timestamp = self.video.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if not math.isfinite(timestamp) or timestamp <= self.previous_timestamp:
                    raise RuntimeError("voice_frame_timestamps_invalid")
                self.previous_timestamp = timestamp
            else:
                timestamp, frame = self.pending
                self.pending = None
            if timestamp >= end:
                self.pending = (timestamp, frame)
                break
            if timestamp + 1e-6 < next_sample:
                continue
            height, width = frame.shape[:2]
            if width > 960:
                frame = cv2.resize(frame, (960, round(height * 960 / width)))
            frames.append(frame)
            next_sample = timestamp + 1 / 12
        return frames


def _trusted_turn(turn: dict) -> bool:
    return str(turn.get("engine") or "").startswith(("pyannote/", "sherpa_onnx/"))


def _track_face_frames(frames: list[np.ndarray], box: dict) -> list[np.ndarray] | None:
    """Track upper-face features and stabilize the mouth within a short window.

    Reacquisition is restricted to the marked seat. Lost or crossing tracks are
    withheld rather than attaching a nearby person's mouth to this slot.
    """
    import cv2

    if not frames or not face_visible(frames[0], box):
        return None
    height, width = frames[0].shape[:2]
    x, y, w, h = (float(box[key]) for key in ("x", "y", "width", "height"))
    x, y, w, h = x * width, y * height, w * width, h * height
    gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(gray)
    mask[max(0, round(y)):min(height, round(y + h * .5)),
         max(0, round(x)):min(width, round(x + w))] = 255
    points = cv2.goodFeaturesToTrack(gray, maxCorners=40, qualityLevel=.03, minDistance=3, mask=mask)
    if points is None or len(points) < 6:
        return None
    anchors = points.copy()
    scale = np.array([[96 / w, 0, -x * 96 / w], [0, 96 / h, -y * 96 / h], [0, 0, 1]])
    output = [cv2.warpAffine(frames[0], scale[:2], (96, 96))]
    for frame in frames[1:]:
        current = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tracked, status, _ = cv2.calcOpticalFlowPyrLK(gray, current, points, None)
        if tracked is None:
            return None
        reverse, reverse_status, _ = cv2.calcOpticalFlowPyrLK(current, gray, tracked, None)
        if reverse is None:
            return None
        good = (status.ravel() == 1) & (reverse_status.ravel() == 1) & (np.linalg.norm(reverse - points, axis=2).ravel() < 1.0)
        if np.count_nonzero(good) < 6:
            return None
        anchors, tracked = anchors[good], tracked[good]
        transform, inliers = cv2.estimateAffinePartial2D(tracked, anchors, method=cv2.RANSAC, ransacReprojThreshold=2)
        if transform is None or inliers is None or float(np.mean(inliers)) < .7:
            return None
        size = float(np.hypot(transform[0, 0], transform[0, 1]))
        if not .85 <= size <= 1.18 or np.linalg.norm(np.mean(tracked - anchors, axis=0)) > min(w, h) * .35:
            return None
        warp = scale @ np.vstack([transform, [0, 0, 1]])
        output.append(cv2.warpAffine(frame, warp[:2], (96, 96)))
        points, gray = tracked, current
    return output


def _visual_candidate(frames, boxes, face_checker) -> tuple[int | None, float, str]:
    if len(frames) < 5:
        return None, 0.0, "too_few_frames"
    full = {"x": 0., "y": 0., "width": 1., "height": 1.}
    observations = {int(box["slot_number"]):
                    (_track_face_frames(frames, box), full) if face_checker is face_visible else (frames, box)
                    for box in boxes}
    series = {slot: _mouth_motion_series(crops, box) for slot, (crops, box) in observations.items() if crops}
    series = {slot: values for slot, values in series.items() if values is not None}
    if not series:
        return None, 0.0, "mouth_not_observable"
    ranked = sorted(series, key=lambda slot: float(np.median(series[slot])), reverse=True)
    winner = ranked[0]
    best = float(np.median(series[winner]))
    others = [series[slot] for slot in ranked[1:]]
    # Independent mouth movement also means ambiguity. Correlation between two
    # faces is not a reliable overlap detector: people rarely move in sync.
    if any(np.mean(values >= MIN_MOTION) >= 0.2 for values in others):
        return None, 0.0, "multiple_moving_mouths"
    second = max((float(np.median(values)) for values in others), default=0.0)
    if best < MIN_MOTION or best < second * 2.5 or best - second < 0.5:
        return None, 0.0, "weak_visual_evidence"
    if np.mean(series[winner] >= MIN_MOTION) < 0.6:
        return None, 0.0, "intermittent_mouth_motion"
    winning_frames, winning_box = observations[winner]
    if not all(face_checker(frame, winning_box) for frame in (winning_frames[0], winning_frames[len(winning_frames) // 2], winning_frames[-1])):
        return None, 0.0, "face_not_visible"
    if _head_motion_ratio(winning_frames, winning_box) > 0.5:
        return None, 0.0, "head_motion"
    return winner, min(1.0, (best - second) / max(best, 1e-9)), "visual_candidate"


def _resolve_cluster_faces(rows: list[dict]) -> None:
    votes: dict[str, dict[int, float]] = {}
    counts: dict[tuple[str, int], int] = {}
    for row in rows:
        candidate = row["evidence"].get("candidate_slot")
        if candidate is None:
            continue
        cluster = row["cluster_label"]
        by_slot = votes.setdefault(cluster, {})
        by_slot[candidate] = by_slot.get(candidate, 0.0) + row["end_s"] - row["start_s"]
        counts[cluster, candidate] = counts.get((cluster, candidate), 0) + 1
    mappings = {}
    for cluster, scores in votes.items():
        slot = max(scores, key=scores.get)
        if scores[slot] >= 1.2 and counts[cluster, slot] >= 3 and scores[slot] / sum(scores.values()) >= 0.9:
            mappings[cluster] = slot
    # A face with strong evidence for different acoustic identities is unsafe.
    # Abstain rather than silently concatenate different speakers into its profile.
    ambiguous_slots = {slot for slot in mappings.values() if list(mappings.values()).count(slot) > 1}
    for row in rows:
        candidate = row["evidence"].get("candidate_slot")
        if candidate is None:
            continue
        if mappings.get(row["cluster_label"]) == candidate and candidate not in ambiguous_slots:
            row.update(slot_number=candidate, status="assigned")
            row["evidence"]["reason"] = "audio_visual_consensus"
        else:
            row["evidence"]["reason"] = "speaker_face_conflict_or_insufficient_evidence"
            row["confidence"] = 0.0


def _select_review_windows(rows: list[dict], boxes: list[dict]) -> None:
    """Choose short, distinct speech excerpts for review, never for training."""
    used: set[str] = set()
    totals = {int(box["slot_number"]): 0.0 for box in boxes}
    candidates = [row for row in rows if row["status"] == "unknown"
                  and row.get("cluster_label") is not None and row.get("_review_scores")]
    for _ in range(16):
        progress = False
        for slot in totals:
            if totals[slot] >= REVIEW_CLIP_SECONDS - 0.2:
                continue
            options = [row for row in candidates if row["id"] not in used
                       and row["end_s"] - row["start_s"] <= REVIEW_CLIP_SECONDS - totals[slot] + 1e-6
                       and slot in row["_review_scores"]]
            if not options:
                continue
            row = max(options, key=lambda item: (item["_review_scores"][slot],
                                                  -item["start_s"]))
            score = row["_review_scores"][slot]
            row["evidence"].update(review_slot=slot, review_motion=score,
                                   review_status="tentative" if score > 0 else "unattributed")
            totals[slot] += row["end_s"] - row["start_s"]
            used.add(row["id"])
            progress = True
        if not progress:
            break
    for row in rows:
        row.pop("_review_scores", None)


def _assign_windows(turns: list[dict], boxes: list[dict], source: bytes | Path, frame_sampler, face_checker) -> list[dict]:
    valid = [(index, turn) for index, turn in enumerate(turns)
             if math.isfinite(float(turn["start_s"])) and math.isfinite(float(turn["end_s"]))
             and 0 <= float(turn["start_s"]) < float(turn["end_s"])]
    boundaries = sorted({float(turn[key]) for _, turn in valid for key in ("start_s", "end_s")})
    rows = []

    def append(left, right, active, reason, candidate=None, confidence=0.0):
        if right <= left:
            return
        clusters = {str(turn["cluster_label"]) for _, turn in active}
        rows.append({"id": str(uuid4()), "start_s": left, "end_s": right,
                     "source_turn_index": active[0][0] if len(active) == 1 else None,
                     "cluster_label": next(iter(clusters)) if len(clusters) == 1 else None,
                     "overlap_refused_s": right - left if reason == "overlapping_speakers" else 0.0,
                     "slot_number": None, "confidence": confidence, "status": "unknown",
                     "evidence": {"version": MATCHING_VERSION, "reason": reason,
                                  "candidate_slot": candidate, "clusters": sorted(clusters)}})

    for left, right in zip(boundaries, boundaries[1:]):
        active = [(index, turn) for index, turn in valid
                  if float(turn["start_s"]) < right and float(turn["end_s"]) > left]
        if not active:
            continue
        clusters = {turn["cluster_label"] for _, turn in active}
        if len(clusters) > 1:
            append(left, right, active, "overlapping_speakers")
            continue
        if not all(_trusted_turn(turn) for _, turn in active):
            append(left, right, active, "diarization_required")
            continue
        # A standalone overlap flag without an interval must also fail closed.
        unexplained_overlap = any(turn.get("overlap") and not any(
            other["cluster_label"] != turn["cluster_label"] and
            float(other["start_s"]) < float(turn["end_s"]) and
            float(other["end_s"]) > float(turn["start_s"]) for _, other in valid) for _, turn in active)
        if unexplained_overlap:
            append(left, right, active, "overlapping_speakers")
            continue
        core_start, core_end = left + BOUNDARY_GUARD_S, right - BOUNDARY_GUARD_S
        if core_end - core_start < 0.4:
            append(left, right, active, "short_or_boundary_speech")
            continue
        append(left, core_start, active, "speaker_boundary")
        count = max(1, math.ceil((core_end - core_start) / MAX_WINDOW_S))
        for window in range(count):
            start = core_start + (core_end - core_start) * window / count
            end = core_start + (core_end - core_start) * (window + 1) / count
            frames = frame_sampler(source, start, end)
            candidate, confidence, reason = _visual_candidate(frames, boxes, face_checker)
            append(start, end, active, reason, candidate, confidence)
            if frames:
                rows[-1]["_review_scores"] = {int(box["slot_number"]):
                                              float(mouth_motion(frames, box) or 0.0)
                                              for box in boxes}
        append(core_end, right, active, "speaker_boundary")
    _resolve_cluster_faces(rows)
    _select_review_windows(rows, boxes)
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


def assigned_audio_for_slot(samples: np.ndarray, sample_rate_hz: int, segments: list[dict],
                            slot: int) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Rebuild the exact clean PCM and source intervals used for a slot's profile."""
    if sample_rate_hz != 16000:
        raise ValueError("voice profiles require 16 kHz PCM")
    recording_end = len(samples) / sample_rate_hz
    intervals = [(max(0.0, float(row["start_s"])), min(recording_end, float(row["end_s"])))
                 for row in segments if row.get("status") == "assigned" and row.get("slot_number") == slot
                 and float(row["end_s"]) > 0 and float(row["start_s"]) < recording_end]
    merged = _merge_intervals([(start, end) for start, end in intervals if end > start])
    forbidden = _merge_intervals([(float(row["start_s"]), float(row["end_s"])) for row in segments
                                 if row.get("status") != "assigned" or row.get("slot_number") != slot])
    for left, right in forbidden:
        merged = [(a, b) for start, end in merged for a, b in
                  ([(start, end)] if right <= start or left >= end else
                   [(start, min(end, left)), (max(start, right), end)]) if b > a]
    clean = [(start, end) for start, end in merged
             if _usable_interval(samples[round(start * sample_rate_hz):round(end * sample_rate_hz)])]
    chunks = [samples[round(start * sample_rate_hz):round(end * sample_rate_hz)] for start, end in clean]
    return (np.concatenate(chunks).astype(np.int16) if chunks else np.array([], dtype=np.int16)), clean


def review_audio_for_slot(samples: np.ndarray, sample_rate_hz: int, segments: list[dict],
                          slot: int) -> np.ndarray:
    """Stitch saved tentative windows without promoting them to assigned speech."""
    if sample_rate_hz != 16000:
        raise ValueError("voice review requires 16 kHz PCM")
    intervals = sorted((max(0, round(float(row["start_s"]) * sample_rate_hz)),
                        min(len(samples), round(float(row["end_s"]) * sample_rate_hz)))
                       for row in segments if row["status"] == "unknown"
                       and (row.get("evidence") or {}).get("review_slot") == slot)
    chunks = [samples[start:end] for start, end in intervals if end > start]
    return np.concatenate(chunks).astype(np.int16) if chunks else np.array([], dtype=np.int16)


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
        audio, intervals = assigned_audio_for_slot(samples, sample_rate_hz, segments, slot)
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
                      if row.get("cluster_label") in assigned_clusters or
                      assigned_clusters.intersection((row.get("evidence") or {}).get("clusters", [])))
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
            "matching_version": MATCHING_VERSION,
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
    if metrics.get("matching_version") != MATCHING_VERSION:
        return None
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
