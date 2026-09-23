"""Seat order is right to left across the displayed frame.

Participant numbers are session labels chosen by that order. They are not
identities inferred from appearance, and they are not speaker-cluster indexes.
"""

from __future__ import annotations

from typing import Any


MIN_PARTICIPANTS = 2
MAX_PARTICIPANTS = 10
_CENTER_EPSILON = 0.02
_OVERLAP_IOU = 0.2


class SeatError(ValueError):
    pass


def overhead_row_regions(count: int) -> list[dict[str, float]]:
    """Place one row of seats for the overhead table recording.

    Heads sit along the near edge. Participant 1 is the person on the right
    of the displayed frame, then numbers continue toward the left.
    """
    if not MIN_PARTICIPANTS <= count <= MAX_PARTICIPANTS:
        raise SeatError("a group recording needs between 2 and 10 participants")
    gap = 0.012
    usable = 0.90
    width = (usable - gap * (count - 1)) / count
    right_edge = 0.95
    regions = []
    for index in range(count):
        x = right_edge - ((index + 1) * width) - (index * gap)
        regions.append({"x": x, "y": 0.40, "width": width, "height": 0.30})
    return regions


def order_seats(regions: list[dict[str, Any]], *, duration_s: float) -> list[dict[str, Any]]:
    if not isinstance(regions, list):
        raise SeatError("seat regions must be a list")
    if not MIN_PARTICIPANTS <= len(regions) <= MAX_PARTICIPANTS:
        raise SeatError("a group recording needs between 2 and 10 seat regions")
    cleaned = [_region(region, duration_s) for region in regions]
    _reject_ambiguous(cleaned)
    ordered = sorted(cleaned, key=lambda region: -region["center_x"])
    for index, region in enumerate(ordered, start=1):
        supplied = region.pop("supplied_slot", None)
        if supplied is not None and int(supplied) != index:
            raise SeatError(
                "seat numbers follow the displayed frame from right to left; "
                f"the region near x={region['center_x']:.2f} is Participant {index}"
            )
        region["slot_number"] = index
        region["label"] = f"Participant {index}"
    return ordered


def _region(region: dict[str, Any], duration_s: float) -> dict[str, Any]:
    try:
        x = float(region["x"])
        y = float(region["y"])
        width = float(region["width"])
        height = float(region["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SeatError("each seat needs x, y, width, and height") from exc
    if min(x, y, width, height) < 0 or x + width > 1.001 or y + height > 1.001:
        raise SeatError("seat regions must lie inside the displayed frame")
    if width < 0.02 or height < 0.02:
        raise SeatError("seat regions must be large enough to see the participant")
    start = float(region.get("valid_from_s", 0))
    end = float(region.get("valid_to_s", duration_s))
    if not (end > start >= 0) or end > duration_s + 0.001:
        raise SeatError("seat time interval must fall inside the recording")
    supplied = region.get("slot_number")
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "center_x": x + (width / 2),
        "valid_from_s": start,
        "valid_to_s": end,
        "supplied_slot": supplied,
        "research_code": region.get("research_code"),
    }


def _reject_ambiguous(regions: list[dict[str, Any]]) -> None:
    for index, left in enumerate(regions):
        for right in regions[index + 1 :]:
            centers_close = abs(left["center_x"] - right["center_x"]) < _CENTER_EPSILON
            spatial = _iou(left, right) >= _OVERLAP_IOU
            temporal = _overlaps_time(left, right)
            if centers_close and temporal:
                raise SeatError("two seats are too close to order from right to left")
            if spatial and temporal:
                raise SeatError("overlapping seats need non-overlapping time intervals")


def _overlaps_time(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["valid_from_s"] < right["valid_to_s"] and right["valid_from_s"] < left["valid_to_s"]


def _iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    x1 = max(left["x"], right["x"])
    y1 = max(left["y"], right["y"])
    x2 = min(left["x"] + left["width"], right["x"] + right["width"])
    y2 = min(left["y"] + left["height"], right["y"] + right["height"])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if intersection <= 0:
        return 0.0
    union = (left["width"] * left["height"]) + (right["width"] * right["height"]) - intersection
    if union <= 0:
        return 0.0
    return intersection / union
