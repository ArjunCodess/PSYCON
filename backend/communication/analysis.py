"""Adapters use source time, not concatenated playback time."""
from __future__ import annotations

import gc
import os
import re
import statistics

import numpy as np

from ml.src.audio import analyze_pcm16
from ml.src.audio_recording import analyze_decoded_recording, decode_audio
from ml.src.speaker_analysis import PyannoteDiarizer, SpeechBrainEmbedder, analyze_speakers
from ml.src.transcription import FasterWhisperTranscriber, transcribe_usable_regions

VERSION = "communication-observations-1"


def redact(text):
    text = re.sub(r"[\w.+-]+@[\w.-]+|https?://\S+|\b\d[\d ()+-]{5,}\d\b", "[redacted]", text)
    # Conservative proper-name suppression, not a claim of perfect de-identification.
    return re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", "[redacted]", text)[:300]


def observations(samples, rate, turns, regular, words, wearer, quality_windows, identity):
    turns = sorted(turns, key=lambda t: (t["start_s"], t["end_s"]))
    anonymous = {speaker: f"other_{index+1}" for index, speaker in enumerate(dict.fromkeys(t["speaker_id"] for t in turns if t["speaker_id"] != wearer))}
    def label(speaker):
        return "wearer" if speaker == wearer else anonymous.get(speaker, "unattributed")
    duration = len(samples) / rate
    clean = []
    for turn in turns:
        if turn["speaker_id"] != wearer:
            continue
        intervals = [(turn["start_s"], turn["end_s"])]
        for other in regular:
            if other["speaker_id"] == wearer:
                continue
            remaining = []
            for left, right in intervals:
                if other["end_s"] <= left or other["start_s"] >= right:
                    remaining.append((left, right))
                else:
                    if left < other["start_s"]:
                        remaining.append((left, other["start_s"]))
                    if other["end_s"] < right:
                        remaining.append((other["end_s"], right))
            intervals = remaining
        for left, right in intervals:
            for window in quality_windows:
                start, end = max(left, window["start_s"]), min(right, window["end_s"])
                if end > start and window["status"] == "usable":
                    clean.append((start, end))
    clean.sort()
    merged = []
    for left, right in clean:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    clean = merged
    speech = sum(right-left for left, right in clean)
    own_turns = [t for t in turns if t["speaker_id"] == wearer and any(min(t["end_s"], r)>max(t["start_s"], l) for l,r in clean)]
    own_words = [w for w in words if w.get("speaker_id") == wearer and any(w["start_s"] >= l and w["end_s"] <= r for l,r in clean)]
    metrics = {"speaking_share": speech/duration if duration else 0}
    if own_turns:
        metrics["mean_turn_duration_s"] = statistics.mean(t["end_s"]-t["start_s"] for t in own_turns)
    if own_words and speech:
        metrics["articulation_rate_wpm"] = len(own_words)/speech*60
        vocabulary = [w["text"].strip().lower() for w in own_words]
        metrics["vocabulary_diversity"] = len(set(vocabulary))/len(vocabulary)
    pauses, gaps = [], []
    for previous, current in zip(turns, turns[1:]):
        if current["speaker_id"] != wearer:
            continue
        gap = current["start_s"]-previous["end_s"]
        if previous["speaker_id"] == wearer and gap >= .2:
            pauses.append(gap)
        elif previous["speaker_id"] != wearer and gap >= 0:
            gaps.append(gap)
    if pauses:
        metrics["pause_mean_s"] = statistics.mean(pauses)
    if gaps:
        metrics["response_gap_s"] = statistics.mean(gaps)
    interruptions = {round(t["start_s"], 3) for t in regular if t["speaker_id"] == wearer and t["end_s"]-t["start_s"] >= .5
                     and any(o["speaker_id"] != wearer and o["start_s"] < t["start_s"] and o["end_s"]-t["start_s"] >= .2 for o in regular)}
    if identity == "verified" and speech:
        metrics["candidate_interruptions_per_min"] = len(interruptions)/(duration/60)
    acoustic = []
    for left, right in clean:
        if right-left >= 1:
            result = analyze_pcm16(samples[int(left*rate):int(right*rate)], rate).to_dict()
            if result["status"] == "usable":
                acoustic.append(result["features"])
    for name, output in (("f0_hz", "pitch_mean_hz"), ("f0_std_hz", "pitch_std_hz"), ("rms_dbfs", "rms_dbfs")):
        values = [a[name] for a in acoustic if isinstance(a.get(name), (int,float))]
        if values:
            metrics[output] = statistics.median(values)
    evidence = []
    # Bound retained text independently of recording length. Other speakers' text is ephemeral.
    for index, turn in enumerate(own_turns[:6]):
        text = " ".join(w["text"] for w in own_words if w["start_s"] >= turn["start_s"] and w["end_s"] <= turn["end_s"])
        evidence.append({"id": f"e{index}", "start_s": turn["start_s"], "end_s": turn["end_s"], "excerpt": redact(text), "speaker": "wearer"})
    transient = []
    for index, turn in enumerate(turns):
        text = " ".join(w["text"] for w in words if w["start_s"] >= turn["start_s"] and w["end_s"] <= turn["end_s"] and w.get("speaker_id") == turn["speaker_id"])
        transient.append({"id": f"t{index}", "start_s": turn["start_s"], "end_s": turn["end_s"], "speaker": label(turn["speaker_id"]), "text": redact(text), "word_count": len(text.split())})
    return {"version": VERSION, "identity": identity, "quality": "usable" if speech >= 3 else "insufficient_speech",
            "usable_speech_s": speech, "duration_s": duration, "metrics": metrics, "evidence": evidence,
            "turns": [{"start_s": t["start_s"], "end_s": t["end_s"], "speaker": label(t["speaker_id"])} for t in turns],
            "overlap_events": [{"start_s": max(t["start_s"], o["start_s"]), "end_s": min(t["end_s"], o["end_s"])}
                               for t in regular if t["speaker_id"] == wearer for o in regular
                               if o["speaker_id"] != wearer and min(t["end_s"], o["end_s"]) > max(t["start_s"], o["start_s"])],
            "quality_windows": [{"start_s": w["start_s"], "end_s": w["end_s"], "status": w["status"]} for w in quality_windows],
            "attributed_words": [{"start_s": w["start_s"], "end_s": w["end_s"], "speaker": label(w.get("speaker_id"))} for w in words],
            "_transient": transient}


def analyze_upload(raw, filename, digest, profile):
    decoded = decode_audio(raw)
    quality = analyze_decoded_recording(decoded, filename, digest)
    revision = os.getenv("PSYCON_COMMUNITY1_REVISION", "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee")
    transcriber, diarizer, embedder = FasterWhisperTranscriber(), PyannoteDiarizer(revision=revision), SpeechBrainEmbedder()
    try:
        transcript = transcribe_usable_regions(decoded.samples, decoded.sample_rate_hz, quality["windows"], transcriber)
        speakers = analyze_speakers(decoded.samples, decoded.sample_rate_hz, transcript, diarizer, embedder, profile)
        result = observations(decoded.samples, decoded.sample_rate_hz, speakers.get("turns", []), speakers.get("regular_turns", []),
                              speakers.get("attributed_words", []), "participant", quality["windows"],
                              "verified" if speakers.get("participant_status") == "identified" else "uncertain")
        result.update(language=transcript.language, transcription_status=transcript.status.value,
                      attribution_status=speakers.get("participant_status"), reasons=speakers.get("reasons", []),
                      engines={"transcriber": transcript.engine, "speaker": speakers.get("engine"), "extractor": quality["extractor"],
                               "diarizer_revision": revision})
        result["vocal_jitter"] = speakers.get("speakers", {}).get("participant", {}).get("jitter", {"status": "unavailable"})
        return result
    finally:
        del transcriber, diarizer, embedder
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
