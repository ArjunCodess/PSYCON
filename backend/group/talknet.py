"""Pinned pretrained TalkNet active-speaker scoring for marked face tracks."""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .nvidia import _visual_windows
from .faces import YUNET_SHA256, rotate_frame, sface_model


UPSTREAM_REVISION = "6d6821479af485e251c4991487e40573b42181b4"
WEIGHTS_REVISION = "a67cf01a10acdf5c3b56dcee865cab922d8e6b77"
WEIGHTS_SHA256 = "d985ddd07dca08864a28337726f5b7d91b6426bebc7327f0e9b21cf9ff1cc937"
SFACE_COSINE_THRESHOLD = .363


def weights_path() -> Path:
    configured = os.getenv("PSYCON_TALKNET_WEIGHTS")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "instance" / "talknet-model" / "pretrain_TalkSet.model"


def load_model(*, device=None, path=None):
    import torch

    from .talknet_vendor.loss import lossAV
    from .talknet_vendor.model.talkNetModel import talkNetModel

    path = Path(path or weights_path())
    if not path.is_file():
        raise RuntimeError("pretrained_talknet_weights_missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != WEIGHTS_SHA256:
        raise RuntimeError("pretrained_talknet_weights_hash_mismatch")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model, classifier = talkNetModel(), lossAV()
    state = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict({key.removeprefix("model."): value for key, value in state.items()
                           if key.startswith("model.")}, strict=True)
    classifier.load_state_dict({key.removeprefix("lossAV."): value for key, value in state.items()
                                if key.startswith("lossAV.")}, strict=True)
    return model.to(device).eval(), classifier.to(device).eval(), device


def _frames_for_window(capture, start_s, end_s):
    import cv2

    capture.set(cv2.CAP_PROP_POS_MSEC, start_s*1000)
    frames = []
    next_sample = start_s
    while True:
        okay, frame = capture.read()
        if not okay:
            break
        timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)/1000
        if timestamp >= end_s:
            break
        if timestamp + .02 < next_sample:
            continue
        frames.append(frame)
        next_sample += 1/25
    count = min(len(frames), round((end_s-start_s)*25))
    return frames[:count]


def _nearest_detection(detections, box, width, height):
    anchor_x = (float(box["x"]) + float(box["width"])/2)*width
    anchor_y = (float(box["y"]) + float(box["height"])/2)*height
    radius_x = max(1, float(box["width"])*width)
    radius_y = max(1, float(box["height"])*height)
    matches = sorted(((math.hypot((float(d[0])+float(d[2])/2-anchor_x)/radius_x,
                                 (float(d[1])+float(d[3])/2-anchor_y)/radius_y), d)
                      for d in detections), key=lambda item: item[0])
    return matches[0][1] if matches and matches[0][0] < 1.5 else None


def _identity_vector(recognizer, frame, detection):
    vector = recognizer.feature(recognizer.alignCrop(frame, detection)).reshape(-1).astype(np.float64)
    norm = float(np.linalg.norm(vector))
    return vector/norm if norm > 0 and math.isfinite(norm) else None


def _identity_decision(samples):
    if not samples:
        return None, None, False
    own = float(np.median([score for score, _ in samples]))
    margin = float(np.median([gap for _, gap in samples]))
    return own, margin, len(samples) >= 2 and own >= SFACE_COSINE_THRESHOLD and margin > 0


def _face_crops(frames, boxes, recognizer, references):
    import cv2

    model_path = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != YUNET_SHA256:
        raise RuntimeError("pinned_face_detector_missing_or_changed")
    height, width = frames[0].shape[:2]
    detector = cv2.FaceDetectorYN.create(str(model_path), "", (width, height),
                                          score_threshold=.85, nms_threshold=.3)
    crops = {int(box["slot_number"]): [] for box in boxes}
    identity = {int(box["slot_number"]): [] for box in boxes}
    tracks = {int(box["slot_number"]): dict(box) for box in boxes}
    _unused, first_found = detector.detect(frames[0])
    first_detections = [] if first_found is None else first_found
    for detection in first_detections:
        vector = _identity_vector(recognizer, frames[0], detection)
        if vector is None or not references:
            continue
        ranked = sorted(((float(vector @ reference), slot) for slot, reference in references.items()),
                        reverse=True)
        score, slot = ranked[0]
        if score < SFACE_COSINE_THRESHOLD or (len(ranked) > 1 and score <= ranked[1][0]):
            continue
        previous = tracks[slot].get("_initial_identity_score", -1.)
        if score > previous:
            tracks[slot] = {**tracks[slot], "x": float(detection[0])/width,
                            "y": float(detection[1])/height,
                            "width": float(detection[2])/width,
                            "height": float(detection[3])/height,
                            "_initial_identity_score": score}
    sample_indices = {0, len(frames)//2, len(frames)-1}
    for frame_index, frame in enumerate(frames):
        if frame_index == 0:
            found = first_found
        else:
            _unused, found = detector.detect(frame)
        detections = [] if found is None else found
        for box in boxes:
            slot = int(box["slot_number"])
            detection = _nearest_detection(detections, tracks[slot], width, height)
            if detection is None:
                continue
            tracks[slot].update(x=float(detection[0])/width, y=float(detection[1])/height,
                                width=float(detection[2])/width, height=float(detection[3])/height)
            if frame_index in sample_indices and slot in references:
                vector = _identity_vector(recognizer, frame, detection)
                if vector is not None:
                    own = float(vector @ references[slot])
                    other = max((float(vector @ reference) for other_slot, reference in references.items()
                                 if other_slot != slot), default=-1.)
                    identity[slot].append((own, own-other))
            cx = float(detection[0]+detection[2]/2)
            cy = float(detection[1]+detection[3]/2)
            half = max(float(detection[2]), float(detection[3]))*.65
            x0, x1 = max(0, round(cx-half)), min(width, round(cx+half))
            y0, y1 = max(0, round(cy-half)), min(height, round(cy+half))
            crop = frame[y0:y1, x0:x1]
            if crop.size:
                crops[slot].append(cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (112, 112)))
    result = {}
    for slot, series in crops.items():
        if len(series) != len(frames):
            continue
        own, margin, verified = _identity_decision(identity[slot])
        result[slot] = (np.stack(series), own, margin, verified)
    return result


def _reference_vectors(capture, boxes, recognizer):
    import cv2

    result = {}
    for box in boxes:
        raw = box.get("identity_vector")
        if raw is None:
            continue
        vector = np.asarray(raw, dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if norm > 0 and math.isfinite(norm):
            result[int(box["slot_number"])] = vector/norm
    if len(result) == len(boxes):
        return result
    time_s = float(boxes[0].get("frame_time_s", 0)) if boxes else 0.
    frames = _frames_for_window(capture, time_s, time_s+.2)
    if not frames:
        return result
    frame = rotate_frame(frames[0], int(boxes[0].get("rotation_degrees", 0)))
    height, width = frame.shape[:2]
    model_path = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
    detector = cv2.FaceDetectorYN.create(str(model_path), "", (width, height),
                                          score_threshold=.85, nms_threshold=.3)
    _unused, found = detector.detect(frame)
    detections = [] if found is None else found
    for box in boxes:
        slot = int(box["slot_number"])
        if slot in result:
            continue
        detection = _nearest_detection(detections, box, width, height)
        if detection is not None:
            vector = _identity_vector(recognizer, frame, detection)
            if vector is not None:
                result[slot] = vector
    return result


def _score(model, classifier, device, audio, faces):
    import python_speech_features
    import torch

    count = len(faces)
    if count < 13:
        return None
    mfcc = python_speech_features.mfcc(audio, 16000, numcep=13, winlen=.025, winstep=.01)
    count = min(count, len(mfcc)//4)
    if count < 13:
        return None
    audio_tensor = torch.from_numpy(np.asarray(mfcc[:count*4], dtype=np.float32)).unsqueeze(0).to(device)
    visual_tensor = torch.from_numpy(np.asarray(faces[:count], dtype=np.float32)).unsqueeze(0).to(device)
    with torch.no_grad():
        audio_embedding = model.forward_audio_frontend(audio_tensor)
        visual_embedding = model.forward_visual_frontend(visual_tensor)
        audio_embedding, visual_embedding = model.forward_cross_attention(audio_embedding, visual_embedding)
        combined = model.forward_audio_visual_backend(audio_embedding, visual_embedding)
        probabilities = torch.softmax(classifier.FC(combined), dim=-1)[:, 1]
    return float(probabilities.mean().detach().cpu())


def _diverse_windows(rows, limit_per_speaker):
    first = _visual_windows(rows, limit_per_speaker=min(8, limit_per_speaker))
    if limit_per_speaker <= 8:
        return first
    all_windows = _visual_windows(rows, limit_per_speaker=10000)
    grouped = {}
    for item in all_windows:
        grouped.setdefault(item[0], []).append(item)
    selected = list(first)
    seen = {(item[0], item[3]) for item in selected}
    for speaker, windows in grouped.items():
        remaining = limit_per_speaker - sum(item[0] == speaker for item in selected)
        unique = {}
        for item in windows:
            if (item[0], item[3]) not in seen:
                unique.setdefault(item[3], item)
        candidates = list(unique.values())
        if remaining <= 0 or not candidates:
            continue
        indices = np.linspace(0, len(candidates)-1, min(remaining, len(candidates)), dtype=int)
        for index in indices:
            item = candidates[int(index)]
            if (item[0], item[3]) not in seen:
                selected.append(item)
                seen.add((item[0], item[3]))
    return sorted(selected, key=lambda item: item[1])


def observations(rows, boxes, video, samples, *, model_bundle=None, max_windows_per_speaker=32):
    import cv2

    model, classifier, device = model_bundle or load_model()
    recognizer = sface_model()
    selected = _diverse_windows(rows, max_windows_per_speaker)
    by_id = {row["id"]: row for row in rows if row.get("id")}
    scheduled = {(segment_id, round(start, 3)) for _, start, _, segment_id in selected}
    secondary = set()
    results = []
    with ExitStack() as stack:
        if isinstance(video, (str, Path)):
            path = Path(video)
        else:
            path = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "video.mp4"
            path.write_bytes(video)
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError("active_speaker_video_decode_failed")
        try:
            references = _reference_vectors(capture, boxes, recognizer)
            for cluster, start, end, segment_id in selected:
                frames = _frames_for_window(capture, start, end)
                if boxes:
                    frames = [rotate_frame(frame, int(boxes[0].get("rotation_degrees", 0)))
                              for frame in frames]
                if len(frames) < 13:
                    continue
                audio = samples[round(start*16000):round(end*16000)]
                scores = []
                crops = _face_crops(frames, boxes, recognizer, references)
                for box in boxes:
                    slot = int(box["slot_number"])
                    if slot not in crops:
                        continue
                    faces, identity_score, identity_margin, identity_verified = crops[slot]
                    value = _score(model, classifier, device, audio, faces)
                    if value is not None and math.isfinite(value):
                        scores.append((slot, value, identity_score, identity_margin, identity_verified))
                if not scores:
                    continue
                scores.sort(key=lambda item: item[1], reverse=True)
                slot, score, identity_score, identity_margin, identity_verified = scores[0]
                competitor = scores[1][1] if len(scores) > 1 else 0.
                results.append({"source_segment_id": segment_id, "cluster_label": cluster,
                                "slot_number": slot, "start_s": start, "end_s": end,
                                "score": score, "competing_score": competitor,
                                "track_continuity": 1.,
                                "face_identity_score": identity_score,
                                "face_identity_margin": identity_margin,
                                "face_identity_verified": identity_verified,
                                "reliable": score >= .8 and competitor <= .3 and identity_verified,
                                "model": "TalkNet-ASD", "model_revision": WEIGHTS_REVISION})
                row = by_id.get(segment_id)
                if (row is not None and segment_id not in secondary and
                        float(row["end_s"])-float(row["start_s"]) >= 4. and
                        abs(start-float(row["start_s"])) < .02 and
                        .55 <= score < .8 and score-competitor >= .25 and
                        competitor <= .45 and identity_verified):
                    later_start = float(row["end_s"])-2.
                    if later_start >= end-.02 and (segment_id, round(later_start, 3)) not in scheduled:
                        selected.append((cluster, later_start, float(row["end_s"]), segment_id))
                        scheduled.add((segment_id, round(later_start, 3)))
                        secondary.add(segment_id)
        finally:
            capture.release()
    return results
