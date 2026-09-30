"""Nemotron output through the same guarded face/voice checks as PSYCON.

These profiles are benchmark outputs. A separate schema prevents accidental
admission to the PSYCON training source before a model-selection decision.
"""
import numpy as np

from . import nvidia, psycon

MATCHING_VERSION = "nemotron-guarded-benchmark-1"
FEATURE_SCHEMA = "nemotron-benchmark-face-voice-1"


def activity_diagnostics(probabilities, duration_s, *, threshold=.5):
    """Describe anonymous channels without equating them to numbered faces."""
    matrix = np.asarray(probabilities)
    if (matrix.ndim != 2 or matrix.shape[1] != 8 or not np.isfinite(matrix).all() or
            np.any((matrix < 0) | (matrix > 1))):
        raise ValueError("invalid_nemotron_probabilities")
    if not 0 < threshold < 1 or duration_s <= 0:
        raise ValueError("invalid_nemotron_activity_parameters")
    if abs(len(matrix)*.01-duration_s) > .021:
        raise ValueError("nemotron_activity_timing_mismatch")
    active = matrix >= threshold
    weights = np.minimum(.01, np.maximum(0., duration_s-np.arange(len(matrix))*.01))
    count = active.sum(axis=1)
    channel_seconds = (active*weights[:, None]).sum(axis=0)
    return {"threshold": threshold, "frame_resolution_s": .01,
            "channels_over_one_second": int(np.sum(channel_seconds >= 1.)),
            "speech_union_s": round(float(weights[count > 0].sum()), 3),
            "overlap_s": round(float(weights[count > 1].sum()), 3),
            "channels": [{"channel": channel, "speech_s": round(float(seconds), 3),
                           "isolated_s": round(float(weights[active[:, channel] & (count == 1)].sum()), 3)}
                          for channel, seconds in enumerate(channel_seconds)]}


def attribute(samples, rows, observations, embeddings, boxes, *, embedder=None,
              transcriber=None, mode="offline"):
    slots = {int(box["slot_number"]) for box in boxes}
    mapping = psycon.link_faces(rows, observations, embeddings, slots)
    recovered = psycon.recover_supported_faces(rows, observations, embeddings, slots)
    review = psycon.mark_review_candidates(rows, observations, slots)
    orphaned = psycon.mark_speech_disposition(rows, observations)
    psycon.mark_playback_overlap(rows)
    isolated_turns = [psycon.SpeakerTurn(row["start_s"], row["end_s"], row["cluster_label"])
                      for row in rows if row["cluster_label"] is not None and
                      not row.get("overlap_refused_s")]
    profiles = psycon.make_profiles(samples, rows, boxes, isolated_turns,
                                   embedder=embedder, transcriber=transcriber)
    audits = {audit["slot_number"]: audit for audit in psycon.audit_incomplete_profiles(rows, profiles)}
    for row in rows:
        row["evidence"]["diarization_engine"] = nvidia.OFFLINE_ENGINE if mode == "offline" else nvidia.ENGINE
        row["evidence"]["matching_version"] = MATCHING_VERSION
    for profile in profiles:
        profile["metrics"].update(feature_schema=FEATURE_SCHEMA,
                                  matching_version=MATCHING_VERSION,
                                  diarization_model=nvidia.MODEL_ID,
                                  diarization_revision=nvidia.MODEL_REVISION,
                                  diarization_mode=mode,
                                  benchmark_only=True)
        if profile["slot_number"] in audits:
            profile["metrics"]["candidate_audit"] = audits[profile["slot_number"]]
    return profiles, {"mapping": mapping, "recovered_turns": recovered,
                      "review_candidates": review, "orphaned_seconds": orphaned}
