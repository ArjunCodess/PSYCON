from __future__ import annotations

import pytest

from backend.sync import ClockObservation, estimate_clock


def observation(number: int, *, drift_us: int = 20) -> dict:
    backend = 1_700_000_000_000_000 + number * 1_000_000
    device = 5_000_000 + number * (1_000_000 + drift_us)
    value = ClockObservation(backend, device + 2_000, device + 2_500, backend + 5_000)
    return {
        "t0_backend_us": value.t0_backend_us,
        "t1_device_us": value.t1_device_us,
        "t2_device_us": value.t2_device_us,
        "t3_backend_us": value.t3_backend_us,
        "delay_us": value.delay_us,
        "offset_us": value.offset_us,
    }


def test_clock_observation_uses_ntp_style_delay_and_offset() -> None:
    value = ClockObservation(1_000_000, 10_002, 10_502, 1_005_000)
    value.validate(10_000)
    assert value.delay_us == 4_500
    assert value.offset_us == 992_248


def test_clock_estimate_requires_multiple_observations_for_reliability() -> None:
    estimate = estimate_clock([observation(0)])
    assert estimate is not None
    assert estimate.reliable is False
    assert estimate.synchronize(6_000_000) is None


def test_clock_estimate_corrects_bounded_drift_and_ignores_slow_exchange() -> None:
    rows = [observation(number) for number in range(5)]
    outlier = observation(6)
    outlier["delay_us"] = 900_000
    outlier["offset_us"] += 300_000
    estimate = estimate_clock(rows + [outlier])
    assert estimate is not None and estimate.reliable
    assert estimate.drift == pytest.approx(-20 / 1_000_020, rel=0.05)
    expected = 1_700_000_005_000_000
    assert estimate.synchronize(10_000_100) == pytest.approx(expected, abs=5_000)


@pytest.mark.parametrize(
    "value",
    [
        ClockObservation(-1, 0, 0, 1),
        ClockObservation(5, 1, 2, 4),
        ClockObservation(1, 5, 4, 2),
        ClockObservation(1, 1, 1, 3_000_001),
    ],
)
def test_clock_observation_rejects_invalid_exchanges(value: ClockObservation) -> None:
    with pytest.raises(ValueError):
        value.validate(2_000_000)
