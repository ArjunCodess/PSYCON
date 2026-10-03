"""Prior-only, session-weighted baselines and repeated deviations."""
from __future__ import annotations

import statistics
import os
import hashlib
import json
from datetime import datetime, timezone

from .rubrics import ADJUSTMENTS, ROLE_ADJUSTMENTS, ROLES, VERSION

METRICS = tuple(ADJUSTMENTS)
MIN_CONVERSATIONS = max(1, int(os.getenv("PSYCON_BASELINE_MIN_CONVERSATIONS", "5")))
MIN_DAYS = max(1, int(os.getenv("PSYCON_BASELINE_MIN_DAYS", "3")))
MIN_SPEECH_S = max(1, int(os.getenv("PSYCON_BASELINE_MIN_SPEECH_S", "1800")))
MIN_PATTERN_CONVERSATIONS = max(3, int(os.getenv("PSYCON_PATTERN_MIN_CONVERSATIONS", "3")))


def cohort(row):
    context = row["context"]
    return tuple(context.get(key, "unknown") for key in ("language", "conversation_type", "microphone", "setting"))


def eligible(row):
    return (row.get("state") == "complete" and row.get("analysis", {}).get("identity") == "verified"
            and row["analysis"].get("quality") == "usable" and row["context"].get("language") == "en"
            and datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc))


def baseline(rows):
    days = len({row["occurred_at"][:10] for row in rows})
    speech = sum(row["analysis"].get("usable_speech_s", 0) for row in rows)
    ready = len(rows) >= MIN_CONVERSATIONS and days >= MIN_DAYS and speech >= MIN_SPEECH_S
    result = {"state": "ready" if ready else "building", "conversations": len(rows), "days": days,
              "usable_speech_s": speech, "requirements": {"conversations": MIN_CONVERSATIONS, "days": MIN_DAYS, "usable_speech_s": MIN_SPEECH_S},
              "source_ids": [row["id"] for row in rows], "metrics": {}}
    for metric in METRICS:
        values = [row["analysis"]["metrics"][metric] for row in rows if metric in row["analysis"].get("metrics", {})]
        if values:
            median = statistics.median(values)
            result["metrics"][metric] = {"median": median, "mad": statistics.median(abs(v-median) for v in values), "n": len(values)}
    lineage = {"version": "communication-baseline-1", "rules": result["requirements"],
               "sources": [{"id": row["id"], "revision": row.get("revision", 0), "source_sha256": row.get("source_sha256"),
                            "context": row["context"], "occurred_at": row["occurred_at"],
                            "metrics": row["analysis"].get("metrics", {}), "analysis_version": row["analysis"].get("version"),
                            "engines": row["analysis"].get("engines", {}), "semantic_model": row["analysis"].get("semantic_model", {})} for row in rows]}
    result.update(version=lineage["version"], snapshot_id=hashlib.sha256(json.dumps(lineage, sort_keys=True).encode()).hexdigest())
    return result


def summarize(rows, role="general"):
    rows = sorted((row for row in rows if eligible(row)), key=lambda row: (row["occurred_at"], row["id"]))
    cohorts = {}
    for row in rows:
        cohorts.setdefault(cohort(row), []).append(row)
    baselines, patterns, comparisons = [], [], []
    for key, group in cohorts.items():
        reference = []
        for row in group:
            reference.append(row)
            if baseline(reference)["state"] == "ready":
                break
        frozen = baseline(reference)
        baselines.append({"cohort": list(key), "reference": frozen, "current": baseline(group)})
        if frozen["state"] != "ready":
            continue
        later = group[len(reference):]
        for row in later:
            comparisons.append({"conversation_id": row["id"], "cohort": list(key), "reference_source_ids": frozen["source_ids"],
                                "metrics": {metric: {"value": value, "baseline_median": frozen["metrics"][metric]["median"],
                                                     "delta": value-frozen["metrics"][metric]["median"]}
                                            for metric, value in row["analysis"].get("metrics", {}).items()
                                            if metric in frozen["metrics"] and frozen["metrics"][metric]["n"] >= MIN_CONVERSATIONS},
                                "uncertainty": "Comparison with earlier comparable conversations; a change alone does not establish a recurring pattern."})
        for metric, stat in frozen["metrics"].items():
            if stat["n"] < MIN_CONVERSATIONS:
                continue
            # Floors prevent a zero-MAD baseline from treating numerical noise as change.
            floors = {"acknowledgement_per_turn": .1, "clarification_per_turn": .1, "speaking_share": .1, "candidate_interruptions_per_min": .5,
                      "articulation_rate_wpm": 20, "mean_turn_duration_s": 3, "response_gap_s": .3, "pause_mean_s": .3}
            threshold = max(2 * 1.4826 * stat["mad"], floors[metric])
            for direction in ("increased", "decreased"):
                support = [row for row in later if metric in row["analysis"].get("metrics", {}) and
                           (row["analysis"]["metrics"][metric] - stat["median"]) * (1 if direction == "increased" else -1) > threshold]
                if len(support) < MIN_PATTERN_CONVERSATIONS:
                    continue
                effect, adjustment = ADJUSTMENTS[metric]
                if direction == "decreased" and metric in {"speaking_share", "mean_turn_duration_s", "candidate_interruptions_per_min"}:
                    effect = "This may leave more room for others, but the retained exchange does not establish their experience."
                    adjustment = "Review whether your main point was still clear, then keep the amount of space that fits the conversation."
                patterns.append({"metric": metric, "direction": direction, "observation": f"{metric.replace('_', ' ')} {direction} across {len(support)} comparable conversations.",
                                 "context": dict(zip(("language", "conversation_type", "microphone", "setting"), key)),
                                 "baseline": stat, "evidence_count": len(support), "source_ids": [r["id"] for r in support],
                                 "evidence": [{"conversation_id": r["id"], "occurred_at": r["occurred_at"], "value": r["analysis"]["metrics"][metric],
                                               "intervals": r["analysis"].get("evidence", [])[:3]} for r in support],
                                 "possible_effect": effect, "suggested_adjustment": adjustment+" "+ROLE_ADJUSTMENTS.get(role, ""),
                                 "uncertainty": "Pilot heuristic; neither a diagnosis nor a calibrated probability."})
    return {"version": "communication-history-1", "rubric_version": VERSION, "role": role,
            "focus": ROLES[role], "general_focus": ROLES["general"], "baselines": baselines, "patterns": patterns, "comparisons": comparisons}
