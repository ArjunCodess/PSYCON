"""Pinned Nemotron 3 streaming diarization. Speaker channels are anonymous."""

from __future__ import annotations

from uuid import uuid4

import numpy as np

MODEL_ID = "nvidia/Nemotron-3-Diarization"
MODEL_REVISION = "f667ed73aee57d40cc39428eb768b4fd87a0a29e"
TRANSFORMERS_REVISION = "6da3313a6f89fb3fe0d51c02fe06e3664cd436b0"
ENGINE = "nemotron-3-diarization/transformers-streaming-v1"
MATCHING_VERSION = "nemotron-face-voice-2"
MAX_SPEAKERS = 8
BOUNDARY_GUARD_S = 0.15
MIN_CLEAN_S = 0.3


def streaming_logits(samples: np.ndarray, sample_rate: int, *, processor=None, model=None):
    """Process one recording with one cache; never batch independent chunks."""
    if sample_rate != 16000 or samples.ndim != 1:
        raise ValueError("nemotron_requires_16khz_mono_pcm")
    if not len(samples):
        raise ValueError("nemotron_empty_pcm")
    if processor is None or model is None:
        try:
            import torch
            from transformers import AutoModelForAudioFrameClassification, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("nemotron_runtime_missing") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("nemotron_cuda_unavailable")
        processor = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
        model = AutoModelForAudioFrameClassification.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION).to("cuda").eval()
    else:
        import torch
    processor.set_streaming_mode("low_latency")
    audio = np.asarray(samples, dtype=np.float32) / 32768.0
    cache = None
    chunks = []
    def inputs_generator():
        yield processor(audio[:processor.num_samples_first_audio_chunk], sampling_rate=16000,
                        is_streaming=True, is_first_audio_chunk=True)
        mel_frame_idx = processor.num_mel_frames_per_step
        start_idx = processor.audio_chunk_start(mel_frame_idx)
        while start_idx + processor.num_samples_per_audio_chunk <= len(audio):
            end_idx = start_idx + processor.num_samples_per_audio_chunk
            yield processor(audio[start_idx:end_idx], sampling_rate=16000,
                            is_streaming=True, is_first_audio_chunk=False)
            mel_frame_idx += processor.num_mel_frames_per_step
            start_idx = processor.audio_chunk_start(mel_frame_idx)
        yield processor(audio[start_idx:], sampling_rate=16000, is_streaming=True,
                        is_first_audio_chunk=False, is_last_audio_chunk=True)
    with torch.inference_mode():
        for inputs in inputs_generator():
            inputs = inputs.to(model.device, dtype=model.dtype)
            output = model(**inputs, speaker_cache=cache)
            cache = output.speaker_cache
            chunks.append(output.logits.detach().cpu())
        probabilities = torch.sigmoid(torch.cat(chunks, dim=1))
    if probabilities.ndim != 3 or probabilities.shape[0] != 1 or probabilities.shape[2] != MAX_SPEAKERS:
        raise RuntimeError("nemotron_unexpected_output_shape")
    return probabilities[0].numpy()


def activity_segments(probabilities: np.ndarray, *, threshold: float = 0.5) -> list[dict]:
    """Keep independent channels so simultaneous speech survives postprocessing."""
    matrix = np.asarray(probabilities)
    if matrix.ndim != 2 or matrix.shape[1] != MAX_SPEAKERS:
        raise ValueError("nemotron_requires_eight_speaker_channels")
    if not np.isfinite(matrix).all():
        raise ValueError("nemotron_nonfinite_activity")
    active = matrix >= threshold
    rows = []
    for speaker in range(MAX_SPEAKERS):
        edges = np.flatnonzero(np.diff(np.r_[False, active[:, speaker], False].astype(np.int8)))
        for left, right in zip(edges[::2], edges[1::2]):
            rows.append({"id": str(uuid4()), "cluster_label": f"nemotron-speaker-{speaker}",
                         "start_s": left * .01, "end_s": right * .01,
                         "engine": ENGINE, "speaker_channel": speaker})
    return sorted(rows, key=lambda row: (row["start_s"], row["cluster_label"]))


def clean_windows(turns: list[dict], *, duration_s: float) -> list[dict]:
    """Split on all activity edges; guard uncertain onsets and offsets."""
    events: dict[float, list[tuple[str, int]]] = {}
    for turn in turns:
        label = str(turn["cluster_label"])
        events.setdefault(float(turn["start_s"]), []).append((label, 1))
        events.setdefault(float(turn["end_s"]), []).append((label, -1))
    boundaries = sorted(events)
    counts: dict[str, int] = {}
    spans = []
    for left, right in zip(boundaries, boundaries[1:]):
        for label, change in events[left]:
            counts[label] = counts.get(label, 0) + change
        active = sorted(label for label, count in counts.items() if count > 0)
        if not active:
            continue
        if spans and spans[-1][2] == active and abs(spans[-1][1] - left) < 1e-6:
            spans[-1] = (spans[-1][0], right, active)
        else:
            spans.append((left, right, active))
    rows = []
    for left, right, active in spans:
        overlap = len(active) > 1
        start = left if overlap else left + BOUNDARY_GUARD_S
        end = right if overlap else right - BOUNDARY_GUARD_S
        if end <= start or start >= duration_s or (not overlap and end - start < MIN_CLEAN_S):
            continue
        rows.append({"id": str(uuid4()), "start_s": start, "end_s": min(end, duration_s),
                     "cluster_label": active[0] if len(active) == 1 else None,
                     "slot_number": None, "confidence": 0.0, "status": "unknown",
                     "overlap_refused_s": right - left if overlap else 0.0,
                     "evidence": {"reason": "overlapping_speakers" if overlap else "speaker_unmapped",
                                  "clusters": active, "version": MATCHING_VERSION}})
    return rows


def map_speakers(rows: list[dict], observations: list[dict], slots: set[int]) -> dict[str, int]:
    """Require repeated, consistent visual votes and a one-to-one mapping."""
    by_source: dict[str, list[dict]] = {}
    for item in observations:
        if item.get("source_segment_id"):
            by_source.setdefault(str(item["source_segment_id"]), []).append(item)
    for row in rows:
        items = by_source.get(str(row.get("id")), [])
        if items:
            row["evidence"]["visual_observations"] = [
                {"start_s": x["start_s"], "end_s": x["end_s"],
                 "candidate_slot": x.get("slot_number"), "score": x.get("score"),
                 "reason": x.get("reason")}
                for x in items
            ]
    votes: dict[str, dict[int, list[dict]]] = {}
    for item in observations:
        speaker, slot = item.get("cluster_label"), item.get("slot_number")
        if speaker is None or slot not in slots or not item.get("reliable"):
            continue
        votes.setdefault(speaker, {}).setdefault(slot, []).append(item)
    mapping = {}
    confidence = {}
    for speaker, options in votes.items():
        ranked = sorted(options.items(), key=lambda pair: sum(float(x["end_s"])-float(x["start_s"]) for x in pair[1]), reverse=True)
        slot, support = ranked[0]
        seconds = sum(float(x["end_s"])-float(x["start_s"]) for x in support)
        total = sum(float(x["end_s"])-float(x["start_s"]) for members in options.values() for x in members)
        distinct_turns = {x.get("source_segment_id", (x["start_s"], x["end_s"])) for x in support}
        mean_margin = sum(float(x.get("score", 1.0)) for x in support) / len(support)
        if (len(support) >= 3 and len(distinct_turns) >= 2
                and seconds >= 1.2 and seconds / total >= .7 and mean_margin >= .8
                and len(support) >= 2 * max((len(members) for other, members in options.items()
                                             if other != slot), default=0)):
            mapping[speaker] = slot
            confidence[speaker] = seconds / total
    conflicts = {slot for slot in mapping.values() if list(mapping.values()).count(slot) > 1}
    mapping = {speaker: slot for speaker, slot in mapping.items() if slot not in conflicts}
    local: dict[str, tuple[int, list[dict]]] = {}
    for row in rows:
        speaker = row.get("cluster_label")
        if speaker is None or speaker in mapping or row.get("overlap_refused_s"):
            continue
        support = [x for x in by_source.get(str(row.get("id")), []) if x.get("reliable")]
        if len(support) < 2 or len({x.get("slot_number") for x in support}) != 1:
            continue
        slot = support[0]["slot_number"]
        if slot not in slots or slot in mapping.values():
            continue
        first, last = min(x["start_s"] for x in support), max(x["end_s"] for x in support)
        mean_margin = sum(float(x.get("score") or 0) for x in support) / len(support)
        if (first - row["start_s"] <= 2.1 and row["end_s"] - last <= 2.1
                and last - first >= 3.0 and mean_margin >= .7):
            local[str(row["id"])] = (slot, support)
    local_by_slot: dict[int, dict[str, float]] = {}
    for row in rows:
        if str(row.get("id")) in local:
            slot = local[str(row["id"])][0]
            speaker = row["cluster_label"]
            score = sum(x["end_s"] - x["start_s"] for x in local[str(row["id"])][1])
            by_speaker = local_by_slot.setdefault(slot, {})
            by_speaker[speaker] = by_speaker.get(speaker, 0) + score
    accepted_local: dict[int, str] = {}
    for slot, speakers in local_by_slot.items():
        ranked = sorted(speakers.items(), key=lambda pair: pair[1], reverse=True)
        if len(ranked) == 1 or ranked[0][1] >= 2 * ranked[1][1]:
            accepted_local[slot] = ranked[0][0]
    for row in rows:
        speaker = row.get("cluster_label")
        if speaker in mapping and not row.get("overlap_refused_s"):
            contrary = [x for x in observations if x.get("cluster_label") == speaker and x.get("reliable")
                        and x.get("slot_number") != mapping[speaker]
                        and x.get("start_s", 0) < row["end_s"] and x.get("end_s", 0) > row["start_s"]]
            if contrary:
                row["evidence"]["reason"] = "local_identity_conflict"
                continue
            row.update(slot_number=mapping[speaker], status="assigned", confidence=confidence[speaker])
            row["evidence"].update(reason="speaker_identity_propagated", mapping_slot=mapping[speaker],
                                   support_windows=len(votes[speaker][mapping[speaker]]),
                                   support_seconds=sum(x["end_s"]-x["start_s"] for x in votes[speaker][mapping[speaker]]),
                                   support_observations=[{"start_s": x["start_s"], "end_s": x["end_s"],
                                                          "score": x.get("score")}
                                                         for x in votes[speaker][mapping[speaker]]])
        elif (str(row.get("id")) in local and
              accepted_local.get(local[str(row["id"])][0]) == speaker):
            slot, support = local[str(row["id"])]
            row.update(slot_number=slot, status="assigned",
                       confidence=sum(float(x.get("score") or 0) for x in support) / len(support))
            row["evidence"].update(reason="local_repeated_visual_evidence", mapping_slot=slot,
                                   support_windows=len(support),
                                   support_seconds=sum(x["end_s"]-x["start_s"] for x in support))
        elif speaker is not None and row["evidence"].get("visual_observations"):
            row["evidence"]["reason"] = "speaker_face_conflict_or_insufficient_evidence"
    return mapping


def visual_observations(rows: list[dict], boxes: list[dict], video: bytes, *, sampler=None,
                        checker=None) -> list[dict]:
    """Sample isolated speech across time, retaining failures for review."""
    from .voice import WindowFrameSampler
    from pathlib import Path
    import tempfile

    observations = []
    selected = _visual_windows(rows)

    def inspect(frame_sampler, source):
        for speaker, start, end, source_id in selected:
            frames = frame_sampler(source, start, end)
            tracked_boxes = _locate_faces(frames, boxes) if checker is None else boxes
            slot, score, reason = _candidate_from_tracks(frames, tracked_boxes, checker)
            observations.append({"cluster_label": speaker, "slot_number": slot,
                                 "start_s": start, "end_s": end, "score": score,
                                 "reason": reason, "reliable": slot is not None,
                                 "source_segment_id": source_id})

    if sampler is not None:
        inspect(sampler, video)
    else:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "recording.mp4"
            source.write_bytes(video)
            with WindowFrameSampler(source) as frame_sampler:
                inspect(frame_sampler, source)
    return observations


def _visual_windows(rows: list[dict], *, limit_per_speaker: int = 24) -> list[tuple[str, float, float, str]]:
    """Visit distinct turns first, then revisit long turns at separated times."""
    by_speaker: dict[str, list[dict]] = {}
    for row in rows:
        speaker = row.get("cluster_label")
        if speaker is not None and not row.get("overlap_refused_s") and row["end_s"] - row["start_s"] >= .42:
            by_speaker.setdefault(speaker, []).append(row)
    selected = []
    for speaker, turns in by_speaker.items():
        passes: list[list[tuple[str, float, float, str]]] = [[], [], []]
        for row in sorted(turns, key=lambda item: item["start_s"]):
            start, end = float(row["start_s"]), float(row["end_s"])
            length = end - start
            source_id = str(row.get("id") or f"{speaker}:{start}")
            passes[0].append((speaker, start, min(end, start + 2.0), source_id))
            if length >= 4.0:
                passes[1].append((speaker, end - 2.0, end, source_id))
            if length >= 6.0:
                middle = (start + end) / 2
                passes[2].append((speaker, middle - 1.0, middle + 1.0, source_id))
        selected.extend((passes[0] + passes[1] + passes[2])[:limit_per_speaker])
    return sorted(selected, key=lambda item: item[1])


def _candidate_from_tracks(frames: list[np.ndarray], boxes: list[dict], checker=None):
    from .voice import _mouth_motion_series, _track_face_frames

    if len(frames) < 5 or not boxes:
        return None, 0.0, "face_tracking_lost"
    scores = {}
    full = {"x": 0., "y": 0., "width": 1., "height": 1.}
    for box in boxes:
        if checker is not None and not checker(frames[0], box):
            continue
        tracked = _track_face_frames(frames, box)
        if tracked is None:
            continue
        motion = _mouth_motion_series(tracked, full)
        if motion is not None:
            scores[int(box["slot_number"])] = float(np.median(motion))
    if not scores:
        return None, 0.0, "face_tracking_lost"
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    slot, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if best < .55 or best < second * 1.8 or best - second < .35:
        return None, 0.0, "weak_stabilized_mouth_evidence"
    return slot, min(1.0, (best - second) / max(best, 1e-9)), "stabilized_mouth_motion"


def _locate_faces(frames: list[np.ndarray], anchors: list[dict]) -> list[dict]:
    """Relocate marked faces by horizontal seat order in the sampled video."""
    if len(frames) < 5:
        return []
    import cv2
    from .voice import _frontal_face_detector, _profile_face_detector

    height, width = frames[0].shape[:2]
    locations: dict[int, list[tuple[int, int, int, int]]] = {}
    for frame in (frames[0], frames[len(frames) // 2], frames[-1]):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        found = list(_frontal_face_detector().detectMultiScale(gray, 1.1, 3, minSize=(20, 20)))
        found.extend(_profile_face_detector().detectMultiScale(gray, 1.1, 3, minSize=(20, 20)))
        flipped = cv2.flip(gray, 1)
        found.extend((width-x-w, y, w, h) for x, y, w, h in
                     _profile_face_detector().detectMultiScale(flipped, 1.1, 3, minSize=(20, 20)))
        for anchor in anchors:
            slot = int(anchor["slot_number"])
            expected_x = float(anchor["x"]) + float(anchor["width"]) / 2
            choices = [b for b in found if abs((b[0]+b[2]/2)/width - expected_x) < .065
                       and .15 < (b[1]+b[3]/2)/height < .7]
            if choices:
                selected = min(choices, key=lambda b: abs((b[0]+b[2]/2)/width - expected_x))
                locations.setdefault(slot, []).append(tuple(map(int, selected)))
    boxes = []
    for slot, found in locations.items():
        if len(found) < 2:
            continue
        x, y, w, h = np.median(np.asarray(found), axis=0)
        boxes.append({"slot_number": slot, "x": float(x/width), "y": float(y/height),
                      "width": float(w/width), "height": float(h/height)})
    return boxes
