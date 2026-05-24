from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from .config import COMMON_HZ
from .wesad import resample_labels

WRIST_SAMPLE_RATES = {
    "ACC": 32,
    "BVP": 64,
    "EDA": 4,
    "TEMP": 4,
}


def subject_to_frame(subject_id: str, data: dict, common_hz: int = COMMON_HZ) -> pd.DataFrame:
    wrist = data["signal"]["wrist"]
    durations = [len(wrist[name]) / rate for name, rate in WRIST_SAMPLE_RATES.items() if name in wrist]
    duration_seconds = min(durations)
    n_samples = int(duration_seconds * common_hz)
    time_s = np.arange(n_samples, dtype=float) / common_hz

    frame = pd.DataFrame({"subject": subject_id, "time_s": time_s})
    acc = _resample_array(wrist["ACC"], WRIST_SAMPLE_RATES["ACC"], time_s)
    frame["acc_x"] = acc[:, 0]
    frame["acc_y"] = acc[:, 1]
    frame["acc_z"] = acc[:, 2]
    frame["bvp"] = _smooth(_resample_array(wrist["BVP"], WRIST_SAMPLE_RATES["BVP"], time_s)[:, 0])
    frame["eda"] = _smooth(_resample_array(wrist["EDA"], WRIST_SAMPLE_RATES["EDA"], time_s)[:, 0])
    frame["temp"] = _smooth(_resample_array(wrist["TEMP"], WRIST_SAMPLE_RATES["TEMP"], time_s)[:, 0])

    labels = resample_labels(data["label"], n_samples, common_hz)
    frame["wesad_label"] = labels.astype(int)
    return frame


def _resample_array(values: np.ndarray, source_hz: int, target_time_s: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    source_time_s = np.arange(len(array), dtype=float) / source_hz
    output = np.empty((len(target_time_s), array.shape[1]), dtype=float)
    for col in range(array.shape[1]):
        output[:, col] = np.interp(target_time_s, source_time_s, array[:, col])
    return output


def _smooth(values: np.ndarray) -> np.ndarray:
    values = pd.Series(values).interpolate(limit_direction="both").to_numpy(dtype=float)
    if len(values) < 9:
        return values
    window = min(9, len(values) if len(values) % 2 == 1 else len(values) - 1)
    return savgol_filter(values, window_length=window, polyorder=2, mode="nearest")

