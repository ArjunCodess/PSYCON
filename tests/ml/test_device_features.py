from __future__ import annotations

import pytest

from ml.src.device_features import extract_wrist_batch_features, wrist_batch_to_frame
from protocol.wrist import WristBatch, WristQuality, WristSample


def fixture_batch() -> WristBatch:
    return WristBatch(
        session_id="session-1",
        device_id=7,
        sequence=3,
        device_timestamp_us=1_000_000,
        sample_period_us=40_000,
        battery_mv=3850,
        samples=(
            WristSample(100, 50000, 60000, 1200, 3150, 0, 0, 1000, 0, 0, 0),
            WristSample(101, 50010, 60020, 1210, 3160, 100, 0, 1000, 10, 0, 0, int(WristQuality.CONTACT_LOST)),
            WristSample(103, 50020, 60040, 1220, 3170, 200, 0, 1000, 20, 0, 0),
        ),
    )


def test_converts_device_units_and_time() -> None:
    frame = wrist_batch_to_frame(fixture_batch())
    assert frame["time_s"].tolist() == pytest.approx([1.0, 1.04, 1.12])
    assert frame["temperature_c"].tolist() == pytest.approx([31.5, 31.6, 31.7])
    assert frame["accel_z_g"].tolist() == [1.0, 1.0, 1.0]


def test_extracts_hardware_compatible_features_and_quality() -> None:
    features = extract_wrist_batch_features(fixture_batch())
    assert features["ppg_ir_mean"] == pytest.approx(60020)
    assert features["eda_adc_range"] == pytest.approx(20)
    assert features["sample_completeness"] == pytest.approx(0.75)
    assert features["contact_lost_fraction"] == pytest.approx(1 / 3)
    assert features["battery_mv"] == 3850
