"""Derived audio, transcript, diarization, and seat-visibility records.

Automatic clusters stay anonymous. Nothing in this module copies a cluster
index onto a participant slot.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ml.src.audio import FEATURE_EXTRACTOR, analyze_pcm16


PROCESSING_VERSION = "group-processing-1.1.0"


def build_processing_baseline(
    *,
    source_sha256: str,
    duration_s: float,
    samples: np.ndarray | None = None,
    sample_rate_hz: int | None = None,
    turns: list[dict[str, Any]] | None = None,
    transcript: list[dict[str, Any]] | None = None,
    frames: list[dict[str, Any]] | None = None,
    seat_count: int = 0,
    time_offset_s: float = 0.0,
    diarization_engine: str | None = None,
    failure_reasons: list[str] | None = None,
) -> dict[str, Any]:
    reasons = list(failure_reasons or [])
    audio_summary: dict[str, Any] | None = None
    if samples is not None and sample_rate_hz is not None:
        analysis = analyze_pcm16(np.asarray(samples, dtype=np.int16), sample_rate_hz)
        audio_summary = analysis.to_dict()
        if analysis.status.value != "usable":
            reasons.extend(analysis.reasons)
    else:
        reasons.append("audio_samples_not_extracted")

    stored_turns = []
    for turn in turns or []:
        start = float(turn["start_s"]) + time_offset_s
        end = float(turn["end_s"]) + time_offset_s
        if end <= start:
            reasons.append("invalid_turn_dropped")
            continue
        cluster = str(turn.get("cluster_label") or "").strip()
        if not cluster or cluster.lower().startswith("participant"):
            raise ValueError("diarization clusters must stay anonymous")
        stored_turns.append(
            {
                "cluster_label": cluster,
                "start_s": start,
                "end_s": end,
                "overlap": bool(turn.get("overlap")),
                "engine": diarization_engine or str(turn.get("engine") or "unassigned"),
                "tool_version": PROCESSING_VERSION,
                "proposed_participant_id": None,
            }
        )
    stored_turns.sort(key=lambda item: (item["start_s"], item["cluster_label"]))
    overlap_s = _overlap_seconds(stored_turns)
    speaking = {}
    for turn in stored_turns:
        speaking[turn["cluster_label"]] = speaking.get(turn["cluster_label"], 0.0) + (turn["end_s"] - turn["start_s"])
    pauses = _pauses(stored_turns, duration_s)
    visibility = _visibility(frames or [], seat_count)
    quality = "usable"
    if "audio_samples_not_extracted" in reasons or (audio_summary and audio_summary["status"] != "usable"):
        quality = "poor_audio"
    if frames is not None and visibility and any(not row["visible"] for row in visibility):
        quality = "partial_visibility" if quality == "usable" else quality
    return {
        "source_sha256": source_sha256,
        "time_offset_s": time_offset_s,
        "tool_version": PROCESSING_VERSION,
        "audio_extractor": FEATURE_EXTRACTOR,
        "audio": audio_summary,
        "turns": stored_turns,
        "transcript": [_transcript_row(row, time_offset_s) for row in transcript or []],
        "overlap_s": overlap_s,
        "speaking_duration_s": speaking,
        "pauses": pauses,
        "frames": visibility,
        "quality_state": quality,
        "failure_reasons": reasons,
        "diarization_engine": diarization_engine,
    }


def _transcript_row(row: dict[str, Any], offset_s: float) -> dict[str, Any]:
    return {
        "start_s": float(row["start_s"]) + offset_s,
        "end_s": float(row["end_s"]) + offset_s,
        "cluster_label": row.get("cluster_label"),
        "text": str(row.get("text") or ""),
    }


def _overlap_seconds(turns: list[dict[str, Any]]) -> float:
    total = 0.0
    for index, left in enumerate(turns):
        for right in turns[index + 1 :]:
            start = max(left["start_s"], right["start_s"])
            end = min(left["end_s"], right["end_s"])
            if end > start and left["cluster_label"] != right["cluster_label"]:
                total += end - start
    return total


def _pauses(turns: list[dict[str, Any]], duration_s: float) -> list[dict[str, float]]:
    if not turns:
        return []
    cursor = 0.0
    pauses = []
    for turn in turns:
        if turn["start_s"] - cursor >= 0.4:
            pauses.append({"start_s": cursor, "end_s": turn["start_s"]})
        cursor = max(cursor, turn["end_s"])
    if duration_s - cursor >= 0.4:
        pauses.append({"start_s": cursor, "end_s": duration_s})
    return pauses


def _visibility(frames: list[dict[str, Any]], seat_count: int) -> list[dict[str, Any]]:
    rows = []
    for frame in frames:
        visible = {int(slot) for slot in frame.get("visible_slots") or []}
        missing = [slot for slot in range(1, seat_count + 1) if slot not in visible]
        rows.append(
            {
                "time_s": float(frame["time_s"]),
                "visible_slots": sorted(visible),
                "missing_slots": missing,
                "visible": not missing,
            }
        )
    return rows
