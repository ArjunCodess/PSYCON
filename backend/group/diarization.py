"""Local, overlapping anonymous speaker turns. Cluster IDs are never face numbers."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np


ENGINE = "sherpa_onnx/pyannote-3.0-titanet-small/v1"


def model_directory() -> Path:
    return Path(os.getenv("PSYCON_DIARIZATION_MODELS", "instance/diarization-models"))


def diarize(samples: np.ndarray, sample_rate: int) -> list[dict]:
    import sherpa_onnx

    if sample_rate != 16000:
        raise ValueError("diarization requires 16 kHz PCM")
    directory = model_directory()
    if not all((directory / name).is_file() for name in ("segmentation.onnx", "embedding.onnx")):
        raise RuntimeError("local_diarization_models_missing")
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(directory / "segmentation.onnx")), num_threads=2),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(directory / "embedding.onnx"), num_threads=2),
        # Do not force the number of visible faces: moderators and off-camera
        # voices exist, and some visible participants may never speak.
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=0.5),
        min_duration_on=0.2, min_duration_off=0.0,
    )
    if not config.validate():
        raise RuntimeError("invalid_local_diarization_config")
    model = sherpa_onnx.OfflineSpeakerDiarization(config)
    result = model.process(np.asarray(samples, dtype=np.float32) / 32768.0).sort_by_start_time()
    return [{"cluster_label": f"voice-{row.speaker}", "start_s": float(row.start),
             "end_s": float(row.end), "overlap": False, "engine": ENGINE} for row in result]
