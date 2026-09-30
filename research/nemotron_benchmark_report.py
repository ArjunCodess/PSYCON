"""Always include Nemotron offline and its attribution control in comparisons."""
from __future__ import annotations

import json
import csv
import sys
import wave
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group.nemotron_benchmark import activity_diagnostics

ROOT = Path("instance/group_batch")
ASSETS = Path("docs/report_assets")
METHODS = ("existing", "nvidia", "psycon", "psycon-recovered",
           "nemotron-streaming-guarded", "nemotron-offline")
LABELS = ("Original", "Earlier NVIDIA", "First PSYCON", "Guarded PSYCON",
          "Nemotron streaming + guarded", "Nemotron offline + guarded")
COLORS = ("#9c9c9c", "#708997", "#c5894b", "#3a6c50", "#8865a3", "#295c94")
inventory = json.loads((ROOT / "inventory.json").read_text())
records = []
for item in inventory:
    folder = ROOT / Path(item["file"]).stem
    summaries = {}
    for method in METHODS:
        path = folder / f"{method}-summary.json"
        value = json.loads(path.read_text()) if path.exists() else {"status": "not_run"}
        summaries[method] = {key: value.get(key) for key in (
            "status", "reason", "ready_profiles", "active_channels", "channels_over_one_second",
            "assigned_s", "usable_s", "unknown_s", "overlap_s", "elapsed_s", "profiles")}
        if value.get("status") == "complete" and value.get("usable_s") is None:
            summaries[method]["usable_s"] = round(sum(profile["usable_s"]
                for profile in value["profiles"]), 2)
    diagnostic_path = folder / "nemotron-offline-probabilities.npz"
    diagnostics = []
    if diagnostic_path.exists():
        with np.load(diagnostic_path) as data:
            probabilities = data["probabilities"]
        with wave.open(str(folder / "shared-16khz.wav"), "rb") as source:
            duration = source.getnframes()/source.getframerate()
        diagnostics = [activity_diagnostics(probabilities, duration, threshold=threshold)
                       for threshold in (.3, .5, .7)]
        (folder / "nemotron-offline-activity-diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    # Same detector on separately selected times is a disagreement check, not DER.
    reference_path = folder / "psycon-recovered-detail.json"
    reference = (json.loads(reference_path.read_text()) if reference_path.exists()
                 else {"profiles": [], "observations": []})
    reference_slots = {profile["slot_number"] for profile in reference["profiles"] if profile["status"] == "ready"}
    reference_observations = [observation for observation in reference["observations"]
                              if observation.get("reliable") and observation.get("face_identity_verified")]
    for method in METHODS[-2:]:
        path = folder / f"{method}-detail.json"
        compared, conflicts = set(), set()
        conflict_intervals = {}
        if path.exists():
            detail = json.loads(path.read_text())
            benchmark_slots = {profile["slot_number"] for profile in detail["profiles"] if profile["status"] == "ready"}
            if reference_path.exists():
                summaries[method]["new_ready_slots_vs_psycon"] = sorted(benchmark_slots-reference_slots)
                summaries[method]["lost_ready_slots_vs_psycon"] = sorted(reference_slots-benchmark_slots)
            for row in detail["rows"]:
                if row["status"] != "assigned" or row.get("evidence", {}).get("training_eligible", True) is False:
                    continue
                for observation in reference_observations:
                    overlap = min(row["end_s"], observation["end_s"])-max(row["start_s"], observation["start_s"])
                    if overlap < .3:
                        continue
                    compared.add(row["id"])
                    if row["slot_number"] != observation["slot_number"]:
                        conflicts.add(row["id"])
                        conflict = conflict_intervals.setdefault(row["id"], {
                            "source_segment_id": row["id"], "start_s": row["start_s"],
                            "end_s": row["end_s"], "assigned_slot": row["slot_number"],
                            "reference_observations": []})
                        conflict["reference_observations"].append({key: observation.get(key)
                            for key in ("slot_number", "start_s", "end_s", "score")})
        summaries[method]["detector_comparison_rows"] = len(compared)
        summaries[method]["detector_disagreement_rows"] = len(conflicts)
        summaries[method]["detector_disagreement_intervals"] = list(conflict_intervals.values())
    records.append({"file": item["file"], "marked_faces": item["detected_faces"],
                    "methods": summaries, "offline_activity_thresholds": diagnostics})

totals = {method: sum(row["methods"][method]["ready_profiles"] or 0 for row in records)
          for method in METHODS}
complete = {method: sum(row["methods"][method]["status"] == "complete" for row in records)
            for method in METHODS}
ASSETS.mkdir(exist_ok=True)
dataset = {"teammate_repository": "https://github.com/CodeSakshamY/PSYCON-Diarization_Model",
           "teammate_commit": "d7d018dba76ca59da144b357ed223757596dc0c0",
           "model_revision": "f667ed73aee57d40cc39428eb768b4fd87a0a29e",
           "basis": "same shared PCM and marked faces; same guarded matcher for the last three methods",
           "marked_slots": sum(row["marked_faces"] for row in records),
           "totals": totals, "complete_runs": complete, "records": records}
(ASSETS / "nemotron-benchmark-summary.json").write_text(json.dumps(dataset, indent=2))

# Keep all six methods in the shared exports, including an explicit failed run.
comparison_rows, profile_rows, segment_rows = [], [], []
for record in records:
    folder = ROOT / Path(record["file"]).stem
    for method in METHODS:
        summary = record["methods"][method]
        comparison_rows.append({"recording": record["file"], "method": method,
            "status": summary["status"], "visible_faces": record["marked_faces"],
            "ready_profiles": summary["ready_profiles"], "usable_s": summary["usable_s"],
            "assigned_s": summary["assigned_s"], "unknown_s": summary["unknown_s"],
            "overlap_s": summary["overlap_s"], "failure_reason": summary["reason"]})
        if summary["status"] != "complete":
            continue
        detail = json.loads((folder / f"{method}-detail.json").read_text())
        for profile in detail["profiles"]:
            metrics = profile.get("metrics") or {}
            profile_rows.append({"recording": record["file"], "method": method,
                "slot": profile["slot_number"], "status": profile["status"],
                "usable_s": profile["usable_seconds"],
                "transcription_status": (metrics.get("transcription") or {}).get("status"),
                "feature_schema": metrics.get("feature_schema"),
                "benchmark_only": metrics.get("benchmark_only", False)})
        segment_rows.extend({"recording": record["file"], "method": method,
            "start_s": row["start_s"], "end_s": row["end_s"],
            "status": row["status"], "slot": row.get("slot_number"),
            "anonymous_cluster": row.get("cluster_label"),
            "overlap_excluded_s": row.get("overlap_refused_s", 0),
            "evidence_reason": (row.get("evidence") or {}).get("reason")}
            for row in detail["rows"])
for filename, entries in (("comparison.csv", comparison_rows),
                          ("profiles.csv", profile_rows), ("segments.csv", segment_rows)):
    if entries:
        with (ROOT / filename).open("w", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=entries[0])
            writer.writeheader()
            writer.writerows(entries)

fig, ax = plt.subplots(figsize=(9, 3.5), layout="constrained")
for index, (method, label, color) in enumerate(zip(METHODS, LABELS, COLORS)):
    count = totals[method]
    ax.barh(index, count, color=color)
    ax.text(count+.8, index, f"{count}   ({complete[method]}/11 runs)", va="center", fontsize=10)
ax.set_yticks(range(len(METHODS)), LABELS)
ax.invert_yaxis()
ax.set_xlim(0, 90)
ax.set_xlabel("Numbered profiles passing each method's gate, out of 85")
ax.grid(axis="x", alpha=.2)
ax.set_axisbelow(True)
fig.savefig(ASSETS / "nemotron-method-totals.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 6.5), layout="constrained")
positions = np.arange(len(records))
for index, method in enumerate(METHODS[3:]):
    values = [row["methods"][method]["ready_profiles"] if row["methods"][method]["status"] == "complete" else np.nan
              for row in records]
    ax.barh(positions+(index-1)*.23, values, height=.21, color=COLORS[index+3], label=LABELS[index+3])
ax.set_yticks(positions, [Path(row["file"]).stem.replace("WhatsApp Video 2026-09-27 at ", "WA ") for row in records], fontsize=9)
ax.invert_yaxis()
ax.set_xlim(0, 8.5)
ax.set_xticks(range(9))
ax.set_xlabel("Model-supported numbered profiles")
ax.grid(axis="x", alpha=.2)
ax.set_axisbelow(True)
ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.01), ncol=1, frameon=False)
fig.savefig(ASSETS / "nemotron-recording-comparison.png", dpi=180)
plt.close(fig)

lines = ["# Nemotron comparison", "",
         "This benchmark keeps the earlier runs and adds the official Nemotron offline preset. It also replays the earlier low-latency turns through the current guarded face and voice checks. Both new paths use the same gate as guarded PSYCON. Their outputs have a separate schema and cannot enter PSYCON training.", "",
         "| Recording | Marked | Original | Earlier NVIDIA | First PSYCON | Guarded PSYCON | Guarded streaming | Guarded offline |",
         "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
for row in records:
    cells = [str(row["methods"][method]["ready_profiles"]) if row["methods"][method]["status"] == "complete"
             else row["methods"][method]["status"] for method in METHODS]
    lines.append(f"| {row['file']} | {row['marked_faces']} | " + " | ".join(cells) + " |")
lines.extend(["| Total | 85 | " + " | ".join(str(totals[m]) for m in METHODS) + " |", "",
              "![All methods](report_assets/nemotron-method-totals.png)", "",
              "![Guarded methods by recording](report_assets/nemotron-recording-comparison.png)", "",
              "The earlier NVIDIA result of 13 was the number of ready face-linked profiles. Its raw output used 80 anonymous channels across the 11 recordings. Those quantities describe different stages of the pipeline.", "",
              "The teammate's `usable profiles` counter counts channels above a user-set total-speech duration, including overlap. It does not check a face link or a SpeechBrain embedding. Our new comparisons use the same isolated-speech and identity gate as PSYCON, so those counts are not interchangeable.", "",
              "The teammate's code uses NeMo's 340-frame chunk and 40-frame lookahead preset, with a persistent speaker cache. We use that same official preset in the already-pinned Transformers implementation. The downloaded repository contained code and a notebook, but no saved outputs for these recordings. This therefore tests the proposed configuration, rather than reproducing an undocumented teammate score.", "",
              "Raw probabilities are retained locally. Activity thresholds of 0.3, 0.5, and 0.7 are reported separately; the face-profile comparison uses 0.5. Threshold changes are diagnostics, not a reason to assign an extra face. Counts do not establish diarization accuracy, and detector disagreements are not human ground truth.", "",
              "Sources: [teammate code](https://github.com/CodeSakshamY/PSYCON-Diarization_Model/blob/d7d018dba76ca59da144b357ed223757596dc0c0/neemotron_bench/core.py), [official model card](https://huggingface.co/nvidia/Nemotron-3-Diarization). The committed [summary data](report_assets/nemotron-benchmark-summary.json) records all six methods. Failures and unrun benchmarks remain visible.", ""])
lines.extend(["## Gains, losses, and detector disagreements", "",
              "| Recording | Offline new slots | Offline lost slots | Offline disagreements / compared rows | Streaming new slots | Streaming lost slots | Streaming disagreements / compared rows |",
              "| --- | --- | --- | --- | --- | --- | --- |"])
for record in records:
    values = []
    for method in ("nemotron-offline", "nemotron-streaming-guarded"):
        summary = record["methods"][method]
        values.extend([", ".join(map(str, summary.get("new_ready_slots_vs_psycon", []))) or "none",
                       ", ".join(map(str, summary.get("lost_ready_slots_vs_psycon", []))) or "none",
                       f"{summary['detector_disagreement_rows']} / {summary['detector_comparison_rows']}"])
    lines.append(f"| {record['file']} | " + " | ".join(values) + " |")
lines.extend(["", "A disagreement means an assigned benchmark interval overlaps a reliable PSYCON TalkNet observation for another face by at least 0.3 seconds. This flags a clip for inspection. It does not prove which model is correct, because both use the same detector and the recordings lack independent speaker labels.", ""])
lines.extend(["## Speech and threshold diagnostics", "",
              "| Method | Usable seconds | Unknown clean seconds | Detected overlap seconds |",
              "| --- | ---: | ---: | ---: |"])
for method in METHODS:
    totals_s = [sum(record["methods"][method][key] or 0 for record in records)
                for key in ("usable_s", "unknown_s", "overlap_s")]
    lines.append(f"| {method} | " + " | ".join(f"{value:.2f}" for value in totals_s) + " |")
lines.extend(["", "| Offline activity threshold | Anonymous channels with at least 1 second, across recordings | Speech union seconds | Overlap seconds |",
              "| ---: | ---: | ---: | ---: |"])
for threshold in (.3, .5, .7):
    selected = [diagnostic for record in records for diagnostic in record["offline_activity_thresholds"]
                if diagnostic["threshold"] == threshold]
    lines.append(f"| {threshold} | {sum(d['channels_over_one_second'] for d in selected)} | "
                 f"{sum(d['speech_union_s'] for d in selected):.2f} | "
                 f"{sum(d['overlap_s'] for d in selected):.2f} |")
lines.extend(["", "These thresholds only change the anonymous activity diagnostic. We did not rerun the face-profile gate at each threshold. Detected overlap is model-dependent and is not independently labeled overlap.", "",
              "## Source-linked data", "",
              "[All method runs](../instance/group_batch/comparison.csv), [all profiles](../instance/group_batch/profiles.csv), and [all intervals](../instance/group_batch/segments.csv) include every method. Each detail file contains the acoustic measurements, transcript, embedding, and per-turn evidence. Playback manifests point back to the original audio intervals.", ""])
for record in records:
    stem = Path(record["file"]).stem
    links = [f"[{method}](<../instance/group_batch/{stem}/{method}-detail.json>)" for method in METHODS]
    lines.append(f"**{record['file']}**: " + ", ".join(links))
    lines.append(f"[Playback manifest](<../instance/group_batch/{stem}/playback/manifest.json>)\n")
Path("docs/nemotron_benchmark_report.md").write_text("\n".join(lines))
print("ready profiles", totals, "complete runs", complete)
