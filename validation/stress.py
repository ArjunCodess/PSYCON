from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from backend.simulator import Client, VERSIONS, audio_packet, wrist_packet


@dataclass
class StressMetrics:
    target_duration_seconds: float
    packets_attempted: int = 0
    packets_accepted: int = 0
    packets_idempotent: int = 0
    packets_rejected: int = 0
    planned_drops: int = 0
    request_latency_ms: list[float] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def record(self, *, status: int, latency_ms: float, device: str, sequence: int, response: dict) -> None:
        self.packets_attempted += 1
        self.request_latency_ms.append(latency_ms)
        state = response.get("status")
        if status == 201 and state == "accepted":
            self.packets_accepted += 1
        elif status == 200 and state == "already_present":
            self.packets_idempotent += 1
        else:
            self.packets_rejected += 1
            self.errors.append({"device": device, "sequence": sequence, "status": status, "response": response})

    def summary(self) -> dict:
        latency = self.request_latency_ms
        return {
            "target_duration_seconds": self.target_duration_seconds,
            "packets_attempted": self.packets_attempted,
            "packets_accepted": self.packets_accepted,
            "packets_idempotent": self.packets_idempotent,
            "packets_rejected": self.packets_rejected,
            "planned_drops": self.planned_drops,
            "unexpected_failure_count": self.packets_rejected,
            "latency_ms": {
                "minimum": min(latency) if latency else None,
                "median": statistics.median(latency) if latency else None,
                "maximum": max(latency) if latency else None,
            },
            "errors": self.errors,
        }


def run_stress(
    base_url: str,
    operator_token: str,
    *,
    duration_seconds: float,
    interval_seconds: float,
    output: Path,
    drop_every: int = 0,
) -> dict:
    if duration_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("duration and interval must be positive")
    operator = Client(base_url, operator_token)
    versions = {**VERSIONS, "dataset": "none", "configuration": "week6-stress-1", "documentation": "week6-1"}
    session = operator.json(
        "POST",
        "/api/v1/sessions",
        {
            "anonymous_code": f"STRESS-{int(time.time())}",
            "versions": versions,
            "metadata": {"source": "simulated_stack", "purpose": "week6_backend_stress", "physical_evidence": False},
        },
    )["session"]
    session_id = str(session["id"])
    simulation_id = int(session_id.replace("-", "")[-7:], 16)
    device_ids = {"wrist": 0xB0000000 | simulation_id, "audio": 0xE0000000 | simulation_id}
    clients: dict[str, Client] = {}
    for name, device_id in device_ids.items():
        issued = operator.json("POST", "/api/v1/devices", {"device_id": device_id, "label": f"stress {name}", "session_id": session_id})
        clients[name] = Client(base_url, issued["token"])

    metrics = StressMetrics(duration_seconds)
    started_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    deadline = started + duration_seconds
    next_send = started
    sequence = 0
    tracemalloc.start()
    try:
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_send:
                time.sleep(min(next_send - now, 0.1))
                continue
            if sequence % 60 == 0:
                _clock_sync(clients, device_ids, session_id, sequence)
            if drop_every > 0 and sequence > 0 and sequence % drop_every == 0:
                metrics.planned_drops += 2
            else:
                timestamp_us = 5_000_000 + round(sequence * interval_seconds * 1_000_000)
                _send(metrics, clients["wrist"], session_id, wrist_packet(device_ids["wrist"], sequence, timestamp_us), "wrist", sequence)
                _send(metrics, clients["audio"], session_id, audio_packet(device_ids["audio"], sequence, timestamp_us), "audio", sequence)
            if sequence % 10 == 0:
                for name, device_id in device_ids.items():
                    clients[name].json(
                        "POST",
                        f"/api/v1/sessions/{session_id}/status",
                        {
                            "device_id": device_id,
                            "event_type": "heartbeat",
                            "device_timestamp_us": 5_000_000 + round(sequence * interval_seconds * 1_000_000),
                            "payload": {
                                "simulated": True,
                                "queue_depth": 0,
                                "overruns": 0,
                                "reset_count": 0,
                                "battery_mv": None,
                                "device_temperature_c": None,
                                "free_heap_bytes": None,
                            },
                        },
                    )
            sequence += 1
            next_send += interval_seconds
    finally:
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    actual_duration = time.monotonic() - started
    operator.json("POST", f"/api/v1/sessions/{session_id}/process", {})
    for name, device_id in device_ids.items():
        clients[name].json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": device_id, "event_type": "shutdown", "device_timestamp_us": None, "payload": {"simulated": True, "buffers_flushed": True}})
    operator.json("POST", f"/api/v1/sessions/{session_id}/close", {})
    snapshot = operator.json("GET", f"/api/v1/sessions/{session_id}")
    report = {
        "schema_version": "1.0.0",
        "source": "simulated_stack",
        "physical_evidence": False,
        "session_id": session_id,
        "started_at_utc": started_utc,
        "actual_duration_seconds": actual_duration,
        "client_peak_memory_bytes": peak_bytes,
        "metrics": metrics.summary(),
        "streams": snapshot["streams"],
        "passed": actual_duration >= duration_seconds and metrics.packets_rejected == 0,
        "claim_limit": "This load test covers the simulated backend path. It does not prove firmware memory, radio behavior, temperature, battery voltage, charging, physical packet loss, or the six-hour runtime gate.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report


def _send(metrics: StressMetrics, client: Client, session_id: str, packet: bytes, device: str, sequence: int) -> None:
    started = time.perf_counter()
    status, response = client.chunk(session_id, packet)
    metrics.record(status=status, latency_ms=(time.perf_counter() - started) * 1000, device=device, sequence=sequence, response=response)


def _clock_sync(clients: dict[str, Client], device_ids: dict[str, int], session_id: str, sequence: int) -> None:
    epoch_us = time.time_ns() // 1_000
    device_time = 5_000_000 + sequence * 1_000_000
    for name, client in clients.items():
        client.json("POST", f"/api/v1/sessions/{session_id}/clock-sync", {"device_id": device_ids[name], "t0_backend_us": epoch_us, "t1_device_us": device_time + 2_000, "t2_device_us": device_time + 2_500, "t3_backend_us": epoch_us + 5_000})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a timed simulated load test against the PSYCON backend.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--operator-token", default="psycon-local-operator")
    parser.add_argument("--duration-seconds", type=float, default=3600)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--drop-every", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("validation-output/stress.json"))
    arguments = parser.parse_args()
    report = run_stress(
        arguments.url,
        arguments.operator_token,
        duration_seconds=arguments.duration_seconds,
        interval_seconds=arguments.interval_seconds,
        output=arguments.output,
        drop_every=arguments.drop_every,
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

