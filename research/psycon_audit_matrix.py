"""Build a review-only rejection audit from saved PSYCON model outputs."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import psycon


def build(root: Path = Path("instance/group_batch")) -> list[dict]:
    inventory = json.loads((root / "inventory.json").read_text())
    matrix = []
    recording_rows = []
    for recording in inventory:
        folder = root / Path(recording["file"]).stem
        detail_path = folder / "psycon-recovered-detail.json"
        detail = json.loads(detail_path.read_text())
        audits = psycon.audit_incomplete_profiles(detail["rows"], detail["profiles"])
        by_slot = {audit["slot_number"]: audit for audit in audits}
        for profile in detail["profiles"]:
            profile["metrics"].pop("candidate_audit", None)
            if profile["slot_number"] in by_slot:
                profile["metrics"]["candidate_audit"] = by_slot[profile["slot_number"]]
        detail["summary"]["audit_version"] = psycon.AUDIT_VERSION
        detail["summary"]["incomplete_profiles"] = len(audits)
        quality_path = folder / "psycon-quality.json"
        quality = json.loads(quality_path.read_text()) if quality_path.exists() else []
        rejected_quality = sum(float(window["end_s"])-float(window["start_s"])
                               for window in quality if window["status"] not in {"accepted", "usable", "complete"})
        recording_rows.append({
            "file": recording["file"], "marked": recording["detected_faces"],
            "ready": detail["summary"]["ready_profiles"], "incomplete": len(audits),
            "unknown_s": float(detail["summary"]["unknown_s"]),
            "overlap_s": float(detail["summary"]["overlap_s"]),
            "rejected_quality_s": round(rejected_quality, 2),
        })
        detail_path.write_text(json.dumps(detail, indent=2))
        (folder / "psycon-recovered-summary.json").write_text(
            json.dumps(detail["summary"], indent=2))
        for audit in audits:
            matrix.append({"recording": recording["file"], **audit})
    matrix.sort(key=lambda item: (-item["review_priority"]["candidate_count"],
                                  -item["review_priority"]["review_seconds"],
                                  -(item["review_priority"]["best_score_margin"] or 0),
                                  item["recording"], item["slot_number"]))
    for rank, item in enumerate(matrix, 1):
        item["batch_review_rank"] = rank
    (root / "psycon-audit-matrix.json").write_text(json.dumps({
        "version": psycon.AUDIT_VERSION,
        "basis": "saved pinned Community-1, TalkNet, and SpeechBrain outputs",
        "ranking_purpose": "human inspection only; no automatic identity or training promotion",
        "failure_modes": dict(Counter(item["failure_mode"] for item in matrix)),
        "incomplete_slots": len(matrix), "recordings": recording_rows, "slots": matrix,
    }, indent=2))
    unknown = sum(row["unknown_s"] for row in recording_rows)
    overlap = sum(row["overlap_s"] for row in recording_rows)
    rejected = sum(row["rejected_quality_s"] for row in recording_rows)
    marked = sum(row["marked"] for row in recording_rows)
    ready = sum(row["ready"] for row in recording_rows)
    visual_candidates = sum(a["failure_mode"] == "no_anchored_speech_with_visual_candidate"
                            for a in matrix)
    no_candidates = sum(a["failure_mode"] == "no_anchored_speech_without_visual_candidate"
                        for a in matrix)
    zero_clean = sum(a["anchored_clean_seconds"] == 0 for a in matrix)
    lines = [
        "# PSYCON rejection audit", "",
        f"The current quality gate retains {ready} model-supported profiles and {len(matrix)} incomplete profiles across {marked} marked slots in {len(recording_rows)} recordings. The incomplete vectors remain null. This audit ranks evidence for inspection only; it does not change identity assignments or training eligibility.", "",
        f"Of the {len(matrix)} incomplete slots, {zero_clean} have zero assigned clean seconds, {visual_candidates} have tentative TalkNet review candidates, and {no_candidates} have none. Anonymous speech cannot establish whether any particular participant spoke for fewer than three isolated seconds or was occluded. The physical cause is therefore `undetermined` without independent review.", "",
        "The taxonomy also records `insufficient_anchored_speech` when a slot has some assigned clean speech below three seconds, and `embedding_rejected` when assigned clean speech passes that duration but its embedding fails validation. Neither mode occurred in this batch. These labels describe evidence at the gate, not a diagnosis of the microphone or camera.", "",
        "| Recording | Marked | Ready | Incomplete | Unknown speech s | Overlap s | Nonusable audio window s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in recording_rows:
        lines.append(f"| {row['file']} | {row['marked']} | {row['ready']} | {row['incomplete']} | {row['unknown_s']:.2f} | {row['overlap_s']:.2f} | {row['rejected_quality_s']:.2f} |")
    lines.extend(["", f"Recording-level totals: {unknown:.2f} s unknown, {overlap:.2f} s detected overlap, and {rejected:.2f} s nonusable audio windows. Nonusable windows include insufficient audio and may include silence. These measures can overlap in time and must not be added as disjoint losses.", "",
        "Tentative TalkNet scores and their competing scores appear with source intervals in [`psycon-audit-matrix.json`](../instance/group_batch/psycon-audit-matrix.json). A candidate is a place to inspect the original video, not a confirmed speaker. TS-VAD, separation, and cross-session similarity were not run and are recorded as such. The ranked queue is sorted by candidate count, review seconds, and strongest score margin; those values do not certify identity.", "",
        f"The capture implications are recording-level inferences: detected overlap suggests that closer or separate microphones could provide more isolated speech, while missing visual candidates suggest improved camera coverage may help anchor it. The current recordings do not prove which change would resolve any individual null slot. {sum(row['marked'] == 7 for row in recording_rows)} recordings have only seven marked faces, so an eighth speaker cannot acquire a numbered face profile from those markings alone.", ""])
    Path("docs/psycon_rejection_audit.md").write_text("\n".join(lines))
    return matrix


if __name__ == "__main__":
    audits = build()
    print(len(audits), "incomplete slots", dict(Counter(a["failure_mode"] for a in audits)))
