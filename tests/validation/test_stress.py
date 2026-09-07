from __future__ import annotations

from validation.stress import StressMetrics


def test_stress_metrics_separate_accepted_idempotent_and_rejected_packets() -> None:
    metrics = StressMetrics(3600)
    metrics.record(status=201, latency_ms=2.0, device="wrist", sequence=0, response={"status": "accepted"})
    metrics.record(status=200, latency_ms=1.0, device="wrist", sequence=0, response={"status": "already_present"})
    metrics.record(status=400, latency_ms=3.0, device="audio", sequence=1, response={"status": "error", "error": {"code": "invalid_crc"}})
    summary = metrics.summary()
    assert summary["packets_attempted"] == 3
    assert summary["packets_accepted"] == 1
    assert summary["packets_idempotent"] == 1
    assert summary["packets_rejected"] == 1
    assert summary["latency_ms"] == {"minimum": 1.0, "median": 2.0, "maximum": 3.0}
    assert summary["errors"][0]["response"]["error"]["code"] == "invalid_crc"


def test_empty_stress_metrics_do_not_invent_latency() -> None:
    assert StressMetrics(60).summary()["latency_ms"] == {"minimum": None, "median": None, "maximum": None}

