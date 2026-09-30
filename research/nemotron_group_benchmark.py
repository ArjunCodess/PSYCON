"""Checkpointed Nemotron offline benchmark on every inventoried recording.

Run in the existing GPU worker. Set NEMOTRON_BENCHMARK_MODE=streaming-control
to replay the saved low-latency turns through the same guarded attribution.
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
import sys
import time
import traceback
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.group import nvidia, psycon, nemotron_benchmark
from ml.src.speaker_analysis import SpeechBrainEmbedder, SpeakerTurn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "instance/group_batch"
MODE = os.getenv("NEMOTRON_BENCHMARK_MODE", "offline")
if MODE not in {"offline", "streaming-control"}:
    raise ValueError("unknown_nemotron_benchmark_mode")
METHOD = "nemotron-offline" if MODE == "offline" else "nemotron-streaming-guarded"


def save(path, value):
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, default=lambda item:
                       item.tolist() if isinstance(item, np.ndarray) else str(item)))
    pending.replace(path)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""):
            result.update(chunk)
    return result.hexdigest()


def run(info):
    import torch
    folder = OUT / Path(info["file"]).stem
    summary_path = folder / f"{METHOD}-summary.json"
    if summary_path.exists():
        saved = json.loads(summary_path.read_text())
        if saved.get("status") == "complete" and saved.get("matching_version") == nemotron_benchmark.MATCHING_VERSION:
            print(info["file"], METHOD, "already complete", flush=True)
            return
    started = time.time()
    pcm = folder / "shared-16khz.wav"
    with wave.open(str(pcm), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("invalid_shared_pcm")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").copy()
    duration = len(samples)/16000
    print(info["file"], METHOD, "start", round(duration, 2), "seconds", flush=True)
    raw_path = folder / f"{METHOD}-turns.json"
    probabilities_path = folder / f"{METHOD}-probabilities.npz"
    if not raw_path.exists():
        if MODE == "offline":
            print(info["file"], "offline inference", flush=True)
            probabilities = nvidia.offline_logits(samples, 16000)
            np.savez_compressed(probabilities_path, probabilities=probabilities)
            turns = nvidia.activity_segments(probabilities)
            del probabilities
            torch.cuda.empty_cache()
        else:
            turns = json.loads((folder / "nvidia-detail.json").read_text())["turns"]
        # The last model frame may include PCM padding; preserve its 10 ms clock.
        turns = [{**turn, "end_s": min(duration, turn["end_s"])} for turn in turns
                 if turn["start_s"] < duration and turn["end_s"] > turn["start_s"]]
        save(raw_path, turns)
    turns = json.loads(raw_path.read_text())
    inputs_path = folder / f"{METHOD}-inputs.json"
    if inputs_path.exists():
        inputs = json.loads(inputs_path.read_text())
        rows, observations = inputs["rows"], inputs["observations"]
    else:
        quality = json.loads((folder / "psycon-quality.json").read_text())
        rows = psycon.clean_windows([SpeakerTurn(turn["start_s"], turn["end_s"], turn["cluster_label"])
                                    for turn in turns], duration, quality)
        boxes = [{**box, "rotation_degrees": info["rotation_degrees"],
                  "frame_time_s": info["marked_frame_s"]} for box in info["faces"]]
        proxy = folder / "analysis-1920w-25fps.mp4"
        video = proxy if proxy.exists() else ROOT / "group_discussions" / info["file"]
        import cv2
        capture = cv2.VideoCapture(str(video))
        video_duration = capture.get(cv2.CAP_PROP_FRAME_COUNT)/capture.get(cv2.CAP_PROP_FPS)
        capture.release()
        if abs(video_duration-duration) > .2:
            raise RuntimeError("visual_audio_timing_mismatch")
        print(info["file"], "TalkNet", len(rows), "rows", flush=True)
        observations = psycon.active_observations(rows, boxes, video, samples)
        save(inputs_path, {"rows": rows, "observations": observations})
    boxes = info["faces"]
    embeddings_path = folder / f"{METHOD}-turn-embeddings.npz"
    embedder = SpeechBrainEmbedder(device="cuda")
    if embeddings_path.exists():
        with np.load(embeddings_path) as saved:
            embeddings = dict(zip(saved["ids"].tolist(), saved["vectors"]))
    else:
        print(info["file"], "SpeechBrain", flush=True)
        embeddings = {}
        for row in rows:
            if row["cluster_label"] is None or row["end_s"]-row["start_s"] < 1.:
                continue
            clip = samples[round(row["start_s"]*16000):round(row["end_s"]*16000)]
            embeddings[row["id"]] = embedder.embed(clip, 16000)
        np.savez_compressed(embeddings_path, ids=np.array(list(embeddings)),
                            vectors=np.array(list(embeddings.values())))
    print(info["file"], "profiles and transcripts", len(observations), "observations", flush=True)
    profiles, attribution = nemotron_benchmark.attribute(
        samples, rows, observations, embeddings, boxes, embedder=embedder,
        mode="offline" if MODE == "offline" else "streaming")
    summary = {"status": "complete", "file": info["file"], "method": METHOD,
               "matching_version": nemotron_benchmark.MATCHING_VERSION,
               "model_id": nvidia.MODEL_ID, "model_revision": nvidia.MODEL_REVISION,
               "transformers_revision": nvidia.TRANSFORMERS_REVISION,
               "inference_config": nvidia.OFFLINE_CONFIG if MODE == "offline" else "saved low_latency turns",
               "pcm_sha256": digest(pcm), "duration_s": duration, "activity_threshold": .5,
               "frame_resolution_s": .01, "marked_faces": len(boxes),
               "active_channels": len({turn["cluster_label"] for turn in turns}),
               "channels_over_one_second": sum(sum(turn["end_s"]-turn["start_s"] for turn in turns
                  if turn["cluster_label"] == label) >= 1. for label in {turn["cluster_label"] for turn in turns}),
               "ready_profiles": sum(p["status"] == "ready" for p in profiles),
               "assigned_s": round(sum(row["end_s"]-row["start_s"] for row in rows if row["status"] == "assigned"), 2),
               "unknown_s": round(sum(row["end_s"]-row["start_s"] for row in rows if row["status"] == "unknown" and not row["overlap_refused_s"]), 2),
               "overlap_s": round(sum(row["overlap_refused_s"] for row in rows), 2),
               "usable_s": round(sum(p["usable_seconds"] for p in profiles), 2),
               "profiles": [{"slot": p["slot_number"], "status": p["status"], "usable_s": round(p["usable_seconds"], 2)} for p in profiles],
               "elapsed_s": round(time.time()-started, 2), **attribution}
    save(folder / f"{METHOD}-detail.json", {"summary": summary, "turns": turns, "rows": rows,
                                            "observations": observations, "profiles": profiles})
    save(summary_path, summary)
    print(info["file"], METHOD, "complete", summary["ready_profiles"], "ready",
          summary["channels_over_one_second"], "channels", summary["elapsed_s"], "seconds", flush=True)
    del embedder, profiles, embeddings
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    failures = []
    for info in json.loads((OUT / "inventory.json").read_text()):
        if os.getenv("GROUP_BATCH_FILE") and info["file"] != os.environ["GROUP_BATCH_FILE"]:
            continue
        try:
            run(info)
        except Exception as error:
            folder = OUT / Path(info["file"]).stem
            save(folder / f"{METHOD}-summary.json", {"status": "failed", "method": METHOD,
                 "file": info["file"], "reason": f"{type(error).__name__}:{error}", "traceback": traceback.format_exc()})
            failures.append(info["file"])
            print(info["file"], "FAILED", traceback.format_exc(), flush=True)
    raise SystemExit(1 if failures else 0)
