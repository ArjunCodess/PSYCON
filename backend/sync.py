from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class ClockObservation:
    t0_backend_us: int
    t1_device_us: int
    t2_device_us: int
    t3_backend_us: int

    @property
    def delay_us(self) -> int:
        return (self.t3_backend_us - self.t0_backend_us) - (self.t2_device_us - self.t1_device_us)

    @property
    def offset_us(self) -> int:
        # backend epoch minus device monotonic time
        return round(((self.t0_backend_us - self.t1_device_us) + (self.t3_backend_us - self.t2_device_us)) / 2)

    def validate(self, max_delay_us: int) -> None:
        if min(self.t0_backend_us, self.t1_device_us, self.t2_device_us, self.t3_backend_us) < 0:
            raise ValueError("clock timestamps must be nonnegative")
        if self.t3_backend_us < self.t0_backend_us or self.t2_device_us < self.t1_device_us:
            raise ValueError("clock timestamps are not monotonic")
        if self.delay_us < 0 or self.delay_us > max_delay_us:
            raise ValueError("clock exchange delay is outside the accepted range")


@dataclass(frozen=True)
class ClockEstimate:
    offset_us: float
    drift: float
    uncertainty_us: int
    reliable: bool

    def synchronize(self, device_timestamp_us: int) -> int | None:
        if not self.reliable:
            return None
        return round(self.offset_us + device_timestamp_us * (1.0 + self.drift))


def estimate_clock(rows: list[dict], *, max_uncertainty_us: int = 250_000) -> ClockEstimate | None:
    if not rows:
        return None
    by_delay = sorted(rows, key=lambda row: int(row["delay_us"]))[:16]
    # The lowest-delay half is least distorted by asymmetric network queuing.
    keep = min(8, max(2, (len(by_delay) + 1) // 2))
    ordered = by_delay[:keep]
    uncertainty = max(1, round(median(int(row["delay_us"]) for row in ordered) / 2))
    offsets = [float(row["offset_us"]) for row in ordered]
    device_midpoints = [
        (int(row["t1_device_us"]) + int(row["t2_device_us"])) / 2 for row in ordered
    ]
    drift = 0.0
    intercept = median(offsets)
    if len(ordered) >= 3 and max(device_midpoints) > min(device_midpoints):
        slopes = []
        for left in range(len(ordered)):
            for right in range(left + 1, len(ordered)):
                delta_device = device_midpoints[right] - device_midpoints[left]
                if delta_device:
                    slopes.append((offsets[right] - offsets[left]) / delta_device)
        drift = median(slopes) if slopes else 0.0
        drift = max(-0.001, min(0.001, drift))
        intercept = median(
            offset - drift * midpoint for offset, midpoint in zip(offsets, device_midpoints, strict=True)
        )
    spread = max(abs(offset - (intercept + drift * midpoint)) for offset, midpoint in zip(offsets, device_midpoints, strict=True))
    uncertainty += round(spread)
    return ClockEstimate(intercept, drift, uncertainty, len(rows) >= 2 and uncertainty <= max_uncertainty_us)
