"""Normalized wrist batch contract used after binary packet decoding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag


class WristQuality(IntFlag):
    OK = 0
    CONTACT_LOST = 1 << 0
    PPG_SATURATED = 1 << 1
    EDA_SATURATED = 1 << 2
    SENSOR_DISCONNECTED = 1 << 3
    TIMING_GAP = 1 << 4
    BATTERY_LOW = 1 << 5


@dataclass(frozen=True)
class WristSample:
    sample_index: int
    ppg_red: int
    ppg_ir: int
    eda_adc: int
    temperature_centi_c: int
    accel_x_mg: int
    accel_y_mg: int
    accel_z_mg: int
    gyro_x_deci_dps: int
    gyro_y_deci_dps: int
    gyro_z_deci_dps: int
    quality_flags: int = 0


@dataclass(frozen=True)
class WristBatch:
    session_id: str
    device_id: int
    sequence: int
    device_timestamp_us: int
    sample_period_us: int
    battery_mv: int
    samples: tuple[WristSample, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CalibrationRecord:
    calibration_id: str
    device_id: int
    firmware_version: str
    hardware_revision: str
    calibrated_at: str
    operator: str
    method: str
    environment: str
    result: str


def validate_wrist_batch(batch: WristBatch) -> None:
    if not batch.session_id.strip():
        raise ValueError("session_id is required")
    if batch.device_id < 0 or batch.sequence < 0 or batch.device_timestamp_us < 0:
        raise ValueError("device identifiers, sequence, and timestamp must be nonnegative")
    if batch.sample_period_us <= 0 or not 2000 <= batch.battery_mv <= 5000:
        raise ValueError("invalid sample period or battery voltage")
    if not batch.samples:
        raise ValueError("wrist batch must contain samples")

    previous = None
    allowed_flags = int(
        WristQuality.CONTACT_LOST
        | WristQuality.PPG_SATURATED
        | WristQuality.EDA_SATURATED
        | WristQuality.SENSOR_DISCONNECTED
        | WristQuality.TIMING_GAP
        | WristQuality.BATTERY_LOW
    )
    for sample in batch.samples:
        if previous is not None and sample.sample_index <= previous:
            raise ValueError("sample indices must increase")
        if sample.quality_flags & ~allowed_flags:
            raise ValueError("unknown wrist quality flag")
        if not 0 <= sample.eda_adc <= 65535:
            raise ValueError("eda_adc must fit an unsigned 16-bit value")
        previous = sample.sample_index
