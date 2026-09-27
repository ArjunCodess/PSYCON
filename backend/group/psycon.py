"""Conservative Community-1 group attribution and wearable feature reuse."""

from __future__ import annotations

import os
from collections import defaultdict
from uuid import uuid4

import numpy as np

from ml.src.speaker_analysis import PyannoteDiarizer, SpeechBrainEmbedder, SpeakerTurn
from ml.src.transcription import FasterWhisperTranscriber, TranscriptionStatus
from ml.src.language_features import extract_language_features
from ml.src.voice_quality import not_supplied_sustained_vowel
from ml.src.audio import analyze_pcm16

from .voice import build_profiles, training_feature


MATCHING_VERSION = "psycon-community1-face-4"
FEATURE_SCHEMA = "psycon-face-voice-2"
MODEL_REVISION = os.getenv("PSYCON_COMMUNITY1_REVISION", "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee")
BOUNDARY_GUARD_S = 0.12
MIN_WINDOW_S = 0.3


def audio_quality_windows(samples, *, window_s=2.0):
    width = round(window_s*16000)
    result = []
    for start in range(0, len(samples), width):
        clip = np.asarray(samples[start:start+width], dtype=np.int16)
        analysis = analyze_pcm16(clip, 16000)
        result.append({"start_s": start/16000, "end_s": (start+len(clip))/16000,
                       "status": analysis.status.value, "reasons": list(analysis.reasons)})
    return result


def clean_windows(regular_turns, duration_s: float, quality_windows=()):
    """Preserve overlapping spans for review while excluding them from features."""
    events = defaultdict(list)
    for index, turn in enumerate(regular_turns):
        start, end = max(0., float(turn.start_s)), min(duration_s, float(turn.end_s))
        if end > start:
            events[start].append((str(turn.speaker_id), index, 1))
            events[end].append((str(turn.speaker_id), index, -1))
    active = set()
    rows = []
    edges = sorted(events)
    for left, right in zip(edges, edges[1:]):
        for speaker, index, change in events[left]:
            if change > 0:
                active.add((speaker, index))
            else:
                active.discard((speaker, index))
        if not active or right <= left:
            continue
        speakers = {speaker for speaker, _ in active}
        overlap = len(active) > 1
        if overlap:
            rows.append(_row(left, right, None, "overlapping_speakers", right-left,
                             sorted(speakers), None))
            continue
        speaker, index = next(iter(active))
        start, end = left + BOUNDARY_GUARD_S, right - BOUNDARY_GUARD_S
        if end-start < MIN_WINDOW_S:
            continue
        accepted = [(start, end)]
        for window in quality_windows:
            if window.get("status") in ("accepted", "usable", "complete"):
                continue
            bad_start, bad_end = float(window["start_s"]), float(window["end_s"])
            accepted = [(a, b) for x, y in accepted for a, b in
                        ((x, min(y, bad_start)), (max(x, bad_end), y)) if b-a >= MIN_WINDOW_S]
        rows.extend(_row(a, b, speaker, "speaker_unmapped", 0., [speaker], index)
                    for a, b in accepted)
    return rows


def _row(start, end, speaker, reason, overlap, clusters, source_index):
    return {"id": str(uuid4()), "start_s": start, "end_s": end,
            "cluster_label": speaker, "slot_number": None, "confidence": 0.,
            "status": "unknown", "overlap_refused_s": overlap,
            "source_turn_index": source_index,
            "evidence": {"version": MATCHING_VERSION, "reason": reason, "clusters": clusters}}


def _similar(left, right, threshold):
    if left is None or right is None:
        return False
    a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if a.shape != b.shape or not a.size:
        return False
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return bool(np.isfinite(denominator) and denominator > 0 and
                float(np.dot(a, b) / denominator) >= threshold)


def _consistent_support(items, embeddings, threshold):
    """Find the dominant mutually agreeing set of distinct visual turns."""
    usable = []
    seen = set()
    for item in items:
        source_id = item["source_segment_id"]
        vector = embeddings.get(source_id)
        if source_id not in seen and vector is not None:
            usable.append((item, np.asarray(vector, dtype=float)))
            seen.add(source_id)
    if len(usable) < 2:
        return None
    neighbors = {index: {other for other in range(len(usable)) if other != index and
                         _similar(usable[index][1], usable[other][1], threshold)}
                 for index in range(len(usable))}
    maximal = []

    def visit(clique, candidates, excluded):
        if not candidates and not excluded:
            maximal.append(clique)
            return
        pivot = max(candidates | excluded, key=lambda index: len(neighbors[index] & candidates))
        for index in tuple(candidates - neighbors[pivot]):
            visit(clique | {index}, candidates & neighbors[index], excluded & neighbors[index])
            candidates.remove(index)
            excluded.add(index)

    visit(set(), set(neighbors), set())
    ranked = sorted(maximal, key=lambda clique: (len(clique),
                    sum(usable[index][0]["end_s"]-usable[index][0]["start_s"] for index in clique)), reverse=True)
    strongest = ranked[0]
    if len(strongest) < 2 or any(len(other) == len(strongest) and not (other & strongest)
                                 for other in ranked[1:]):
        return None
    chosen = [usable[index] for index in sorted(strongest)]
    center = np.mean([vector / np.linalg.norm(vector) for _, vector in chosen], axis=0)
    center /= np.linalg.norm(center)
    cohesion = min(float(np.dot(left, right) / (np.linalg.norm(left)*np.linalg.norm(right)))
                   for index, (_, left) in enumerate(chosen)
                   for _, right in chosen[index+1:])
    return [item for item, _ in chosen], center, cohesion


def link_faces(rows, observations, embeddings, slots, *, threshold=.55):
    """Require independent active-speaker turns and consistent voice identity."""
    by_cluster = defaultdict(list)
    by_row = defaultdict(list)
    for item in observations:
        if item.get("source_segment_id"):
            by_row[item["source_segment_id"]].append(item)
        if item.get("reliable") and item.get("slot_number") in slots:
            by_cluster[item["cluster_label"]].append(item)
    for row in rows:
        if by_row[row["id"]]:
            row["evidence"]["visual_observations"] = by_row[row["id"]]
    candidates = {}
    for cluster, items in by_cluster.items():
        per_slot = defaultdict(list)
        per_row = defaultdict(set)
        for item in items:
            per_slot[item["slot_number"]].append(item)
            per_row[item["source_segment_id"]].add(item["slot_number"])
        if any(len(slots) > 1 for slots in per_row.values()):
            continue
        for slot, support in per_slot.items():
            agreed = _consistent_support(support, embeddings, max(threshold, .65))
            if agreed is None:
                continue
            support, center, cohesion = agreed
            if sum(x["end_s"]-x["start_s"] for x in support) < 1.2:
                continue
            candidates[(cluster, slot)] = (slot, [x["source_segment_id"] for x in support],
                                           center, cohesion)
    # A cluster may contain two voices, but the same voice cannot establish two faces.
    for cluster in {key[0] for key in candidates}:
        groups = [(key, value) for key, value in candidates.items() if key[0] == cluster]
        if any(_similar(left[2], right[2], threshold)
               for index, (_, left) in enumerate(groups) for _, right in groups[index+1:]):
            for key, _ in groups:
                candidates.pop(key, None)
    # Two acoustic clusters may name one face only if their voice samples agree.
    by_slot = defaultdict(list)
    for key, (slot, ids, center, cohesion) in candidates.items():
        by_slot[slot].append((key, ids, center, cohesion))
    for slot, groups in by_slot.items():
        if len(groups) > 1 and not all(
            _similar(left[2], right[2], threshold)
            for index, left in enumerate(groups) for right in groups[index+1:]
        ):
            for key, _, _, _ in groups:
                candidates.pop(key, None)
    conflicting = set()
    pairs = list(candidates.items())
    for index, (key, (slot, ids, center, cohesion)) in enumerate(pairs):
        for other, (other_slot, other_ids, other_center, other_cohesion) in pairs[index+1:]:
            if (slot != other_slot and _similar(center, other_center, threshold) and
                    float(np.dot(center, other_center)) >= min(cohesion, other_cohesion)):
                conflicting.update((key, other))
    for key in conflicting:
        candidates.pop(key, None)
    for row in rows:
        cluster = row["cluster_label"]
        if cluster is None or row["overlap_refused_s"]:
            continue
        current = embeddings.get(row["id"])
        matches = []
        for key, (slot, source_ids, reference, _cohesion) in candidates.items():
            if key[0] != cluster:
                continue
            contrary = any(x.get("reliable") and x.get("slot_number") != slot
                           for x in by_row[row["id"]])
            direct = any(x.get("reliable") and x.get("slot_number") == slot
                         for x in by_row[row["id"]])
            own = (float(np.dot(current, reference) / (np.linalg.norm(current)*np.linalg.norm(reference)))
                   if current is not None else None)
            if not contrary and ((own is not None and own >= threshold) or
                                 (current is None and direct)):
                matches.append((own if own is not None else 1., slot, source_ids, direct))
        matches.sort(reverse=True)
        if matches:
            own, slot, source_ids, direct = matches[0]
            competitors = [float(np.dot(current, other_center) /
                                 (np.linalg.norm(current)*np.linalg.norm(other_center)))
                           for key, (other_slot, _, other_center, _) in candidates.items()
                           if current is not None and other_slot != slot]
            voice_margin = None if not competitors else own-max(competitors)
            if voice_margin is None or voice_margin > 0:
                row.update(slot_number=slot, status="assigned", confidence=1.)
                row["evidence"].update(reason="active_speaker_and_voice_consistent",
                                       source_segments=source_ids, matching_threshold=threshold,
                                       voice_margin=voice_margin, voice_similarity=own,
                                       visual_observations=by_row[row["id"]])
                continue
        # A diarization cluster can contain an isolated second voice. Retain a
        # strong directly visible turn for playback, without propagating it.
        direct = [x for x in by_row[row["id"]] if x.get("reliable") and
                  (x.get("visual_repetition") or
                   (float(x.get("score", 0)) >= .9 and
                    float(x.get("score", 0))-float(x.get("competing_score", 1)) >= .35))]
        if current is not None and len({x["slot_number"] for x in direct}) == 1:
            visual = max(direct, key=lambda x: x["score"])
            slot = visual["slot_number"]
            rival = [float(np.dot(current, center) /
                           (np.linalg.norm(current)*np.linalg.norm(center)))
                     for key, (other_slot, _, center, _) in candidates.items()
                     if key[0] == cluster and other_slot != slot]
            no_cohort = not rival and not any(key[0] == cluster for key in candidates)
            independently_clear = (no_cohort and float(visual["score"]) >= .97 and
                                   float(visual.get("competing_score", 1)) <= .15 and
                                   not any(_similar(current, center, threshold)
                                           for _, (other_slot, _, center, _) in candidates.items()
                                           if other_slot != slot))
            if (rival and max(rival) < threshold) or independently_clear:
                row.update(slot_number=slot, status="assigned", confidence=float(visual["score"]))
                row["evidence"].update(reason="isolated_active_speaker_playback_only",
                                       source_segments=[row["id"]], training_eligible=False,
                                       visual_observations=by_row[row["id"]])
                continue
        row["evidence"]["reason"] = "voice_inconsistent"
    isolated = defaultdict(list)
    for row in rows:
        if (row.get("status") == "assigned" and row.get("slot_number") is not None and
                row.get("evidence", {}).get("reason") == "isolated_active_speaker_playback_only"):
            isolated[row["slot_number"]].append(row)
    for slot, members in isolated.items():
        pairs = []
        for index, left in enumerate(members):
            for right in members[index+1:]:
                if ((left.get("source_turn_index") is not None and
                     left.get("source_turn_index") == right.get("source_turn_index")) or
                        abs(left["start_s"]-right["start_s"]) < 2. or
                        sum(row["end_s"]-row["start_s"] for row in (left, right)) < 3.):
                    continue
                visual = [item for row in (left, right)
                          for item in by_row[row["id"]] if item.get("reliable") and
                          item.get("slot_number") == slot]
                strong = any(float(item.get("score", 0)) >= .9 and
                             float(item.get("score", 0))-float(item.get("competing_score", 1)) >= .35
                             for item in visual)
                repeated = any(item.get("visual_repetition") for item in visual)
                first, second = embeddings.get(left["id"]), embeddings.get(right["id"])
                if not (strong and repeated and _similar(first, second, threshold)):
                    continue
                similarity = float(np.dot(first, second) /
                                   (np.linalg.norm(first)*np.linalg.norm(second)))
                if any(float(np.dot(vector, center) /
                             (np.linalg.norm(vector)*np.linalg.norm(center))) >= similarity
                       for vector in (first, second)
                       for _, (other_slot, _, center, _) in candidates.items()
                       if other_slot != slot):
                    continue
                pairs.append((similarity, left, right))
        if pairs:
            similarity, left, right = max(pairs, key=lambda pair: pair[0])
            for row in (left, right):
                row["evidence"].update(reason="repeated_visual_voice_consistent",
                                       training_eligible=True,
                                       source_segments=[left["id"], right["id"]],
                                       voice_similarity=similarity,
                                       matching_threshold=threshold)
    unique = defaultdict(set)
    for cluster, slot in candidates:
        unique[cluster].add(slot)
    return {cluster: next(iter(slots)) for cluster, slots in unique.items() if len(slots) == 1}


def playback_intervals(rows, slot_number):
    """Return source PCM spans, including mixed overlap for a securely linked cluster.

    Overlap remains excluded from profile and training measurements. A single
    manual correction does not establish the cluster identity for overlap.
    """
    mark_playback_overlap(rows)
    intervals = []
    mixed_seconds = 0.
    for row in rows:
        if row.get("status") == "assigned" and row.get("slot_number") == slot_number:
            intervals.append((float(row["start_s"]), float(row["end_s"])))
        elif row.get("overlap_refused_s") and any(
            item["slot_number"] == slot_number
            for item in row.get("evidence", {}).get("playback_overlap_sources", [])
        ):
            start, end = float(row["start_s"]), float(row["end_s"])
            intervals.append((start, end))
            mixed_seconds += end-start
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged, mixed_seconds


def mark_playback_overlap(rows):
    """Record why a mixed overlap span belongs in a participant's playback."""
    assigned = defaultdict(list)
    for row in rows:
        if row.get("status") == "assigned" and row.get("cluster_label"):
            assigned[row["cluster_label"]].append(row)
    for row in rows:
        if not row.get("overlap_refused_s"):
            continue
        sources = []
        for cluster in row.get("evidence", {}).get("clusters", []):
            members = assigned[cluster]
            if not members:
                continue
            ranked = sorted(members, key=lambda item: max(0.,
                            float(item["start_s"])-float(row["end_s"]),
                            float(row["start_s"])-float(item["end_s"])))
            nearest = ranked[0]
            distance = max(0., float(nearest["start_s"])-float(row["end_s"]),
                           float(row["start_s"])-float(nearest["end_s"]))
            slots = {item["slot_number"] for item in members}
            repeated = any(len(item.get("evidence", {}).get("source_segments", [])) >= 2
                           for item in members)
            reviewed = sum(item.get("evidence", {}).get("reason") ==
                           "reviewer_confirmed_from_original_video" for item in members) >= 2
            unique = len(slots) == 1 and (repeated or reviewed)
            other_nearby = any(item["slot_number"] != nearest["slot_number"] and
                               max(0., float(item["start_s"])-float(row["end_s"]),
                                   float(row["start_s"])-float(item["end_s"])) <= 5.
                               for item in members)
            if unique or (distance <= 5. and not other_nearby):
                sources.append({"slot_number": nearest["slot_number"], "cluster_label": cluster,
                                "source_segment_id": nearest["id"],
                                "reason": "repeated_cluster_voice" if unique else "nearby_clean_turn",
                                "distance_s": round(distance, 3)})
        row["evidence"]["playback_overlap_sources"] = sources


def playback_audio_for_slot(samples, rows, slot_number):
    intervals, mixed_seconds = playback_intervals(rows, slot_number)
    pieces = [samples[round(start*16000):round(end*16000)] for start, end in intervals]
    return (np.concatenate(pieces) if pieces else np.empty(0, dtype=np.int16),
            intervals, mixed_seconds)


def make_profiles(samples, rows, boxes, exclusive_turns, *, embedder=None, transcriber=None):
    transcriber = transcriber or FasterWhisperTranscriber(device="cuda")
    profiles = build_profiles(samples, 16000, rows, boxes, [], embedder=embedder,
                              matching_version=MATCHING_VERSION)
    from .voice import assigned_audio_for_slot
    for profile in profiles:
        profile["metrics"]["matching_version"] = MATCHING_VERSION
        profile["metrics"]["feature_schema"] = FEATURE_SCHEMA
        profile["metrics"]["sustained_vowel"] = not_supplied_sustained_vowel()
        slot = profile["slot_number"]
        audio, intervals = assigned_audio_for_slot(samples, 16000, rows, slot)
        if not len(audio):
            profile["metrics"].update(transcription={"status": "unavailable", "reason": "no_assigned_speech"},
                                      language_features={"status": "unavailable"})
            continue
        result = transcriber.transcribe(audio, 16000)
        # Whisper timestamps refer to concatenated clean audio. Map them back to source PCM.
        words = []
        offsets = []
        cursor = 0.
        for start, end in intervals:
            offsets.append((cursor, cursor+end-start, start))
            cursor += end-start
        if result.status is TranscriptionStatus.COMPLETE:
            for word in result.words:
                for left, right, source_start in offsets:
                    if left <= word.start_s < right and word.end_s <= right:
                        source_word_start = source_start + word.start_s-left
                        source_word_end = source_start + word.end_s-left
                        speaker = next((turn.speaker_id for turn in exclusive_turns
                                        if turn.start_s <= source_word_start and turn.end_s >= source_word_end), None)
                        words.append({"start_s": source_word_start, "end_s": source_word_end,
                                      "text": word.text, "cluster_label": speaker})
                        break
        profile["metrics"]["transcription"] = {"status": result.status.value,
                                                "engine": result.engine, "language": result.language,
                                                "words": words, "reasons": list(result.reasons)}
        profile["metrics"]["language_features"] = extract_language_features(result)
        covered = sum(word["end_s"]-word["start_s"] for word in words)
        profile["metrics"]["word_rate_wpm"] = len(words)/covered*60 if covered else None
    return profiles


def diarize(samples, *, diarizer=None):
    if diarizer is None and not MODEL_REVISION:
        raise RuntimeError("PSYCON_COMMUNITY1_REVISION is required for pinned Community-1")
    diarizer = diarizer or PyannoteDiarizer(device="cuda", revision=MODEL_REVISION)
    return diarizer.diarize(samples, 16000)


def active_observations(rows, boxes, video, samples, *, detector=None):
    """Score tracked marked faces with the pinned local TalkNet checkpoint."""
    if detector is not None:
        return detector(rows, boxes, video, samples)
    from .talknet import observations as detect

    observations = detect(rows, boxes, video, samples)
    eligible = {row["id"]: row for row in rows if row["cluster_label"] is not None}
    slots = {int(box["slot_number"]) for box in boxes}
    checked = []
    for item in observations:
        row = eligible.get(item.get("source_segment_id"))
        if row is None or item.get("cluster_label") != row["cluster_label"]:
            raise ValueError("active_speaker_returned_unknown_window")
        if item.get("slot_number") not in slots or not 0 <= float(item.get("score", -1)) <= 1:
            raise ValueError("active_speaker_returned_invalid_face")
        if not row["start_s"] <= float(item["start_s"]) < float(item["end_s"]) <= row["end_s"]:
            raise ValueError("active_speaker_returned_invalid_timing")
        score = float(item["score"])
        competing = float(item.get("competing_score", 1))
        strong_absolute = score >= .8 and competing <= .3
        strong_separation = score >= .7 and score-competing >= .35 and competing <= .6
        item["reliable"] = bool((strong_absolute or strong_separation) and
                                float(item.get("track_continuity", 0)) >= .8 and
                                item.get("face_identity_verified", item.get("reliable", False)))
        checked.append(item)
    by_source = defaultdict(list)
    for item in checked:
        by_source[item["source_segment_id"]].append(item)
    for items in by_source.values():
        for index, left in enumerate(items):
            for right in items[index+1:]:
                separated = (float(left["end_s"]) <= float(right["start_s"])+.02 or
                             float(right["end_s"]) <= float(left["start_s"])+.02)
                repeated = (separated and left["slot_number"] == right["slot_number"] and
                            all(float(item["score"]) >= .6 and
                                float(item["score"])-float(item.get("competing_score", 1)) >= .25 and
                                float(item.get("competing_score", 1)) <= .4 and
                                item.get("face_identity_verified") and
                                float(item.get("track_continuity", 0)) >= .8
                                for item in (left, right)))
                if repeated:
                    for item in (left, right):
                        item["reliable"] = True
                        item["visual_repetition"] = True
    return checked


def training_vector(face, profile):
    if (profile.get("metrics") or {}).get("feature_schema") != FEATURE_SCHEMA:
        return None
    return training_feature(face, profile)
