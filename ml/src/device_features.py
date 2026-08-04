"""Hardware-compatible wrist feature conversion independent of WESAD frames."""

from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.wrist import WristBatch, WristQuality, validate_wrist_batch


def wrist_batch_to_frame(batch: WristBatch) -> pd.DataFrame:
    validate_wrist_batch(batch)
    rows = []
    first_index = batch.samples[0].sample_index
    for sample in batch.samples:
        rows.append(
            {
                "session_id": batch.session_id,
                "device_id": batch.device_id,
                "sample_index": sample.sample_index,
                "time_s": (batch.device_timestamp_us + (sample.sample_index - first_index) * batch.sample_period_us) / 1_000_000,
                "ppg_red": sample.ppg_red,
                "ppg_ir": sample.ppg_ir,
                "eda_adc": sample.eda_adc,
                "temperature_c": sample.temperature_centi_c / 100,
                "accel_x_g": sample.accel_x_mg / 1000,
                "accel_y_g": sample.accel_y_mg / 1000,
                "accel_z_g": sample.accel_z_mg / 1000,
                "gyro_x_dps": sample.gyro_x_deci_dps / 10,
                "gyro_y_dps": sample.gyro_y_deci_dps / 10,
                "gyro_z_dps": sample.gyro_z_deci_dps / 10,
                "quality_flags": sample.quality_flags,
                "battery_mv": batch.battery_mv,
            }
        )
    return pd.DataFrame(rows)


def extract_wrist_batch_features(batch: WristBatch) -> dict[str, float]:
    frame = wrist_batch_to_frame(batch)
    features: dict[str, float] = {}
    for name in ("ppg_red", "ppg_ir", "eda_adc", "temperature_c"):
        values = frame[name].to_numpy(dtype=float)
        features.update(_summary(name, values))

    accel = frame[["accel_x_g", "accel_y_g", "accel_z_g"]].to_numpy(dtype=float)
    gyro = frame[["gyro_x_dps", "gyro_y_dps", "gyro_z_dps"]].to_numpy(dtype=float)
    features.update(_summary("accel_mag", np.linalg.norm(accel, axis=1)))
    features.update(_summary("gyro_mag", np.linalg.norm(gyro, axis=1)))

    expected = frame["sample_index"].iloc[-1] - frame["sample_index"].iloc[0] + 1
    flags = frame["quality_flags"].to_numpy(dtype=int)
    features["sample_completeness"] = float(len(frame) / expected)
    features["contact_lost_fraction"] = _flag_fraction(flags, WristQuality.CONTACT_LOST)
    features["ppg_saturated_fraction"] = _flag_fraction(flags, WristQuality.PPG_SATURATED)
    features["eda_saturated_fraction"] = _flag_fraction(flags, WristQuality.EDA_SATURATED)
    features["sensor_disconnected_fraction"] = _flag_fraction(flags, WristQuality.SENSOR_DISCONNECTED)
    features["battery_mv"] = float(batch.battery_mv)
    return features


def _summary(prefix: str, values: np.ndarray) -> dict[str, float]:
    return {
        f"{prefix}_mean": float(np.mean(values)),
        f"{prefix}_std": float(np.std(values)),
        f"{prefix}_min": float(np.min(values)),
        f"{prefix}_max": float(np.max(values)),
        f"{prefix}_range": float(np.ptp(values)),
    }


def _flag_fraction(flags: np.ndarray, flag: WristQuality) -> float:
    return float(np.mean((flags & int(flag)) != 0))
