"""Swappable local model adapters and conservative timestamp attribution."""
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version, PackageNotFoundError
import math
import os
from pathlib import Path
from typing import Protocol
import wave

import numpy as np

from .features import merge_turns
from .store import uid


@dataclass
class Audio:
    samples: np.ndarray
    diagnostics: dict


class Diarizer(Protocol):
    @property
    def engine_name(self) -> str: ...
    def diarize(self, samples: np.ndarray, rate: int) -> list[dict]: ...


class Transcriber(Protocol):
    @property
    def engine_name(self) -> str: ...
    def transcribe(self, samples: np.ndarray, rate: int) -> dict: ...


def preprocess(path, output, max_duration=14400):
    import av
    chunks = []
    count = 0
    try:
        with av.open(str(path)) as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise ValueError("No audio stream found")
            rate = int(stream.codec_context.sample_rate or 0)
            channels = stream.codec_context.layout.nb_channels
            if not 1000 <= rate <= 192000 or not 1 <= channels <= 8:
                raise ValueError("Supported source audio is 1–192 kHz with 1–8 channels")
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    values = converted.to_ndarray().reshape(-1)
                    count += len(values)
                    if count > max_duration*16000:
                        raise ValueError(f"Maximum supported duration is {max_duration/3600:g} hours")
                    chunks.append(values)
            for converted in resampler.resample(None):
                values = converted.to_ndarray().reshape(-1)
                count += len(values)
                if count > max_duration*16000:
                    raise ValueError("Recording exceeds maximum duration")
                chunks.append(values)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Corrupted or unreadable audio; no analysis was generated") from exc
    if not chunks or count < 16000:
        raise ValueError("At least one second of decodable audio is required")
    values = np.concatenate(chunks)
    if not np.isfinite(values).all():
        raise ValueError("Audio contains nonfinite signal values")
    clipping = float(np.mean(np.abs(values) >= .999))
    rms = []
    for start in range(0, len(values), 320):
        rms.append(float(np.sqrt(np.mean(values[start:start+320]**2))))
    silence = float(np.mean(np.asarray(rms) < .003162))
    # Signal-to-background proxy from frame-energy quantiles, not a calibrated SNR.
    low, high = np.quantile(rms, [.1, .9])
    snr = float(20*math.log10(high/low)) if low > 0 and high > 0 else None
    samples = np.rint(np.clip(values, -1, 1)*32767).astype(np.int16)
    with wave.open(str(output), "wb") as wav:
        wav.setparams((1, 2, 16000, len(samples), "NONE", "not compressed"))
        wav.writeframes(samples.tobytes())
    diagnostics = dict(duration=len(samples)/16000, original_sample_rate=rate, original_channels=channels,
                       sample_rate=16000, channels=1, format="PCM16 WAV", clipping_fraction=clipping,
                       silence_fraction=silence, silence_method="20ms frame RMS below -50 dBFS",
                       snr_proxy_db=snr, snr_status="estimated energy contrast; not calibrated SNR",
                       clipping_method="After resampling/downmix; source-channel clipping may differ",
                       denoising="disabled", removed_sections=[], timeline="original audio time; no silence removed",
                       quality="poor" if clipping > .05 else "usable",
                       warnings=["Clipping exceeds 5%; confidence reduced"] if clipping > .05 else [])
    if high < .003162:
        raise ValueError("No usable signal detected; recording is silent or below the signal threshold")
    return Audio(samples, diagnostics)


class PyannoteAdapter:
    def __init__(self, config):
        self.config = config
        self.model = config["diarization_model"]

    @property
    def engine_name(self):
        return self.model

    def diarize(self, samples, rate):
        import torch
        from ml.src.speaker_analysis import _ensure_torchaudio_backend_probe
        _ensure_torchaudio_backend_probe()
        from pyannote.audio import Pipeline
        token = os.getenv("HF_TOKEN")
        options = {"token": token}
        if self.config.get("diarization_revision"):
            options["revision"] = self.config["diarization_revision"]
        pipeline = Pipeline.from_pretrained(self.model, **options)
        if self.config["device"] == "cuda":
            pipeline.to(torch.device("cuda"))
        output = pipeline({"waveform": torch.from_numpy(samples.astype(np.float32)[None, :]/32768), "sample_rate": rate},
                          min_speakers=1, max_speakers=self.config["max_speakers"])
        annotation = getattr(output, "speaker_diarization", output)
        return [{"speaker": str(speaker), "start": float(turn.start), "end": float(turn.end), "confidence": None}
                for turn, _, speaker in annotation.itertracks(yield_label=True)]


class WhisperAdapter:
    def __init__(self, config):
        self.config = config

    @property
    def engine_name(self):
        return "faster-whisper/"+self.config["transcription_model"]

    def transcribe(self, samples, rate):
        from faster_whisper import WhisperModel
        model_path = self.config["transcription_model"]
        if self.config.get("transcription_revision"):
            from faster_whisper.utils import download_model
            model_path = download_model(model_path, revision=self.config["transcription_revision"], use_auth_token=os.getenv("HF_TOKEN"))
        model = WhisperModel(model_path, device=self.config["device"],
                             compute_type=self.config.get("transcription_compute_type", "int8_float16" if self.config["device"] == "cuda" else "int8"))
        try:
            generated, info = model.transcribe(samples.astype(np.float32)/32768, language="en", beam_size=5,
                                               vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
            segments = []
            for segment in generated:
                segments.append(dict(start=float(segment.start), end=float(segment.end), text=segment.text,
                                     confidence=min(1., math.exp(segment.avg_logprob)),
                                     words=[dict(start=float(w.start), end=float(w.end), text=w.word, confidence=float(w.probability))
                                            for w in segment.words or []]))
        finally:
            model.model.unload_model()

        return dict(segments=segments, language=info.language, language_confidence=info.language_probability,
                    engine=self.engine_name)


def attribute(session_id, raw_turns, transcript, duration, max_speakers):
    rows = []
    for row in raw_turns:
        if not all(math.isfinite(row[k]) for k in ("start", "end")) or row["start"] < 0 or row["end"] > duration+.1 or row["end"] <= row["start"]:
            raise ValueError("Diarization returned invalid timestamps")
        rows.append({**row, "end": min(row["end"], duration)})
    if not rows:
        raise ValueError("Speaker attribution could not be reliably completed: no diarized speech")
    labels = sorted({r["speaker"] for r in rows})
    if len(labels) > max_speakers:
        raise ValueError("Diarization exceeded the supported speaker limit")
    speakers = [dict(id=uid(), session_id=session_id, label=label, display_name=f"Speaker {i+1}", profile_id=None)
                for i, label in enumerate(labels)]
    mapping = {s["label"]: s["id"] for s in speakers}
    turns = [dict(id=uid(), session_id=session_id, speaker_id=mapping[r["speaker"]], start=r["start"], end=r["end"],
                  confidence=r.get("confidence")) for r in merge_turns(rows)]
    utterances, words = [], []
    for segment in transcript["segments"]:
        parts = segment.get("words") or [segment]
        group = []
        previous = object()
        def emit():
            if not group:
                return
            sid = group[0][1]
            key = uid()
            utterances.append(dict(id=key, session_id=session_id, speaker_id=sid,
                                   turn_id=next((t["id"] for t in turns if t["speaker_id"] == sid and t["start"] <= group[0][0]["start"] and t["end"] >= group[-1][0]["end"]), None),
                                   start=group[0][0]["start"], end=group[-1][0]["end"], text="".join(p[0]["text"] for p in group).strip(),
                                   confidence=sum(p[0].get("confidence", 0) for p in group)/len(group),
                                   attribution="attributed" if sid else "ambiguous_or_missing"))
            if segment.get("words"):
                words.extend(dict(id=uid(), utterance_id=key, **{k: p[0].get(k) for k in ("start", "end", "text", "confidence")}) for p in group)
        for word in parts:
            left, right = word["start"], word["end"]
            if not math.isfinite(left+right) or not 0 <= left <= right <= duration+.2:
                raise ValueError("Transcript contains invalid timestamps")
            width = max(right-left, .001)
            coverage = {}
            for turn in turns:
                covered = max(0., min(right, turn["end"])-max(left, turn["start"]))
                coverage[turn["speaker_id"]] = coverage.get(turn["speaker_id"], 0.)+covered/width
            ranked = sorted(coverage.items(), key=lambda item: item[1], reverse=True)
            sid = ranked[0][0] if ranked and ranked[0][1] >= .8 and (len(ranked) == 1 or ranked[1][1] < .1) else None
            if group and (sid != previous or word["start"]-group[-1][0]["end"] > 1 or group[-1][0]["text"].rstrip().endswith((".", "?", "!"))):
                emit()
                group = []
            group.append((word, sid))
            previous = sid
        emit()
    if not utterances:
        raise ValueError("Transcription returned no speech; analysis unavailable")
    return speakers, turns, utterances, words


def model_versions(config):
    versions = {"analysis_version": "0.2.0", "feature_schema_version": "1.0.0",
                "diarization_model": config["diarization_model"], "diarization_revision": config.get("diarization_revision"),
                "transcription_model": "faster-whisper/"+config["transcription_model"]}
    versions["transcription_revision"] = config.get("transcription_revision")
    versions["device"] = config["device"]
    versions["transcription_compute_type"] = config.get("transcription_compute_type", "int8_float16" if config["device"] == "cuda" else "int8")
    for package in ("pyannote.audio", "faster-whisper", "av", "numpy", "torch"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not installed"
    return versions
