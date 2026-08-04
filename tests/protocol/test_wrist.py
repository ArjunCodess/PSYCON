from __future__ import annotations

from dataclasses import replace

import pytest

from protocol.wrist import WristBatch, WristQuality, WristSample, validate_wrist_batch


def batch() -> WristBatch:
    return WristBatch(
        session_id="session-1",
        device_id=1,
        sequence=2,
        device_timestamp_us=1000,
        sample_period_us=40000,
        battery_mv=3800,
        samples=(
            WristSample(10, 100, 200, 300, 3150, 0, 0, 1000, 0, 0, 0),
            WristSample(11, 101, 201, 301, 3151, 1, 0, 1000, 0, 0, 0, int(WristQuality.CONTACT_LOST)),
        ),
    )


def test_validates_wrist_batch() -> None:
    validate_wrist_batch(batch())


@pytest.mark.parametrize(
    "changed",
    [
        lambda value: replace(value, session_id=""),
        lambda value: replace(value, battery_mv=9000),
        lambda value: replace(value, samples=()),
        lambda value: replace(value, samples=(value.samples[1], value.samples[0])),
        lambda value: replace(value, samples=(replace(value.samples[0], quality_flags=128),)),
    ],
)
def test_rejects_invalid_wrist_batch(changed) -> None:
    with pytest.raises(ValueError):
        validate_wrist_batch(changed(batch()))
