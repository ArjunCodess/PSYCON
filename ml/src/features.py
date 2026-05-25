from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .config import COMMON_HZ, HOP_SECONDS, WINDOW_SECONDS
from .wesad import map_wesad_label


def extract_windows(
    frame: pd.DataFrame,
    common_hz: int = COMMON_HZ,
    window_seconds: int = WINDOW_SECONDS,
    hop_seconds: int = HOP_SECONDS,
) -> pd.DataFrame:
    window_size = window_seconds * common_hz
    hop_size = hop_seconds * common_hz
    rows: list[dict[str, float | int | str]] = []
    for start in range(0, len(frame) - window_size + 1, hop_size):
        end = start + window_size
        window = frame.iloc[start:end]
        label = _majority_label(window["wesad_label"].to_numpy(dtype=int))
        if label is None:
            continue
        row: dict[str, float | int | str] = {
            "subject": str(window["subject"].iloc[0]),
            "window_start_s": float(window["time_s"].iloc[0]),
            "window_end_s": float(window["time_s"].iloc[-1]),
            "label": label,
            "label_binary": 1 if label == "high_stress" else 0,
        }
        row.update(_series_features("eda", window["eda"].to_numpy(dtype=float), common_hz))
        row.update(_series_features("bvp", window["bvp"].to_numpy(dtype=float), common_hz))
        row.update(_acc_features(window[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float), common_hz))
        row.update(_series_features("temp", window["temp"].to_numpy(dtype=float), common_hz))
        rows.append(row)
    return pd.DataFrame(rows)


def add_subject_baseline_features(features: pd.DataFrame) -> pd.DataFrame:
    """Add per-subject calm-baseline deltas used for personalization experiments."""
    output = features.copy()
    baseline_columns = [
        "bvp_mean",
        "bvp_std",
        "eda_mean",
        "eda_slope",
        "eda_peak_count",
        "temp_mean",
        "acc_mag_mean",
        "jerk_mean",
    ]
    available_columns = [col for col in baseline_columns if col in output.columns]
    calm = output[output["label"] == "calm"]
    baselines = calm.groupby("subject")[available_columns].mean()
    global_baseline = calm[available_columns].mean()

    for col in available_columns:
        values: list[float] = []
        for _, row in output[["subject", col]].iterrows():
            subject = row["subject"]
            baseline = baselines.loc[subject, col] if subject in baselines.index else global_baseline[col]
            values.append(float(row[col] - baseline))
        output[f"{col}_baseline_diff"] = values
    return output


def feature_columns(columns: list[str] | pd.Index) -> list[str]:
    excluded = {"subject", "window_start_s", "window_end_s", "label", "label_binary"}
    return [str(c) for c in columns if str(c) not in excluded]


def modality_columns(columns: list[str] | pd.Index) -> dict[str, list[str]]:
    cols = feature_columns(columns)
    return {
        "eda": [c for c in cols if c.startswith("eda_")],
        "bvp": [c for c in cols if c.startswith("bvp_")],
        "motion": [c for c in cols if c.startswith("acc_") or c.startswith("jerk_")],
        "temp": [c for c in cols if c.startswith("temp_")],
        "multimodal": cols,
    }


def _majority_label(raw_labels: np.ndarray) -> str | None:
    labels = [map_wesad_label(int(label)) for label in raw_labels]
    labels = [label for label in labels if label is not None]
    if len(labels) < len(raw_labels) * 0.8:
        return None
    values, counts = np.unique(labels, return_counts=True)
    return str(values[int(np.argmax(counts))])


def _series_features(prefix: str, values: np.ndarray, sample_hz: int) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    t = np.arange(len(x), dtype=float) / sample_hz
    slope = float(np.polyfit(t, x, 1)[0]) if len(x) > 1 else 0.0
    features = {
        f"{prefix}_mean": float(np.mean(x)),
        f"{prefix}_std": float(np.std(x)),
        f"{prefix}_min": float(np.min(x)),
        f"{prefix}_max": float(np.max(x)),
        f"{prefix}_slope": slope,
        f"{prefix}_change": float(x[-1] - x[0]) if len(x) else 0.0,
        f"{prefix}_range": float(np.max(x) - np.min(x)),
    }
    if prefix == "eda":
        prominence = max(float(np.std(x)) * 0.5, 1e-9)
        peaks, _ = find_peaks(x, prominence=prominence)
        features["eda_peak_count"] = float(len(peaks))
    if prefix == "bvp":
        prominence = max(float(np.std(x)) * 0.5, 1e-9)
        peaks, _ = find_peaks(x, prominence=prominence)
        features["bvp_peak_count"] = float(len(peaks))
    return features


def _acc_features(acc: np.ndarray, sample_hz: int) -> dict[str, float]:
    magnitude = np.linalg.norm(acc, axis=1)
    jerk = np.diff(magnitude, prepend=magnitude[0]) * sample_hz
    return {
        "acc_mag_mean": float(np.mean(magnitude)),
        "acc_mag_std": float(np.std(magnitude)),
        "acc_mag_max": float(np.max(magnitude)),
        "jerk_mean": float(np.mean(np.abs(jerk))),
        "jerk_max": float(np.max(np.abs(jerk))),
    }
