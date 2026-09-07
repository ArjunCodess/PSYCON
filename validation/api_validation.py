from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import urlopen

from backend.simulator import Client, run_detailed


SCENARIOS = ("normal", "duplicate", "corrupt", "missing-audio", "overrun", "sensor-failure", "communication-loss", "watchdog", "shutdown")


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    passed: bool
    checks: dict[str, bool]
    session_id: str


def assess_scenario(scenario: str, details: dict, snapshot: dict) -> ScenarioResult:
    responses = details["chunk_responses"]
    streams = snapshot["streams"]
    events = {item["event_type"] for item in snapshot["status"]}
    checks = {
        "processing_completed": bool(snapshot["jobs"] and snapshot["jobs"][0]["state"] == "complete"),
        "synchronization_recorded": bool(streams and all(item["max_sync_uncertainty_us"] is not None for item in streams)),
        "features_created": bool(snapshot["features"]),
        "inference_recorded": bool(snapshot["inferences"]),
    }
    if scenario == "normal":
        checks["all_chunks_accepted"] = len(responses) == 6 and all(item["status"] == 201 for item in responses)
    elif scenario == "duplicate":
        checks["duplicate_is_idempotent"] = any(item["response"].get("status") == "already_present" for item in responses)
    elif scenario == "corrupt":
        checks["corrupt_chunk_rejected"] = any(item["status"] == 400 and item["response"].get("error", {}).get("code") == "invalid_crc" for item in responses)
    elif scenario == "missing-audio":
        checks["missing_stream_visible"] = {item["stream_type"] for item in streams} == {"wrist_batch"}
    elif scenario == "overrun":
        checks["overrun_reported"] = "overrun" in events
    elif scenario == "sensor-failure":
        checks["sensor_failure_isolated"] = "sensor_error" in events and {item["stream_type"] for item in streams} == {"audio_pcm", "wrist_batch"}
    elif scenario == "communication-loss":
        checks["sequence_gap_visible"] = any(int(item["missing_sequence_count"]) > 0 for item in streams)
        checks["reconnect_reported"] = "reconnect" in events
    elif scenario == "watchdog":
        checks["watchdog_recovery_reported"] = "watchdog_reset" in events
    elif scenario == "shutdown":
        checks["session_closed"] = snapshot["session"]["state"] == "complete"
        checks["post_close_write_rejected"] = details["post_close"]["status"] == 409
        checks["shutdown_reported"] = "shutdown" in events
    return ScenarioResult(scenario, all(checks.values()), checks, str(details["session_id"]))


def run_api_validation(base_url: str, operator_token: str, output: Path) -> dict:
    operator = Client(base_url, operator_token)
    health = operator.json("GET", "/api/v1/health")
    ready = operator.json("GET", "/api/v1/ready")
    with urlopen(base_url.rstrip("/") + "/", timeout=15) as response:
        dashboard_status = response.status
    results: list[ScenarioResult] = []
    for scenario in SCENARIOS:
        details = run_detailed(base_url, operator_token, scenario)
        snapshot = _wait_for_processing(operator, str(details["session_id"]))
        results.append(assess_scenario(scenario, details, snapshot))
    report = {
        "schema_version": "1.0.0",
        "source": "simulated_stack",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "health": health,
        "ready": ready,
        "dashboard_http_status": dashboard_status,
        "scenarios": [asdict(item) for item in results],
        "passed": health.get("status") == "ok" and ready.get("status") == "ready" and dashboard_status == 200 and all(item.passed for item in results),
        "claim_limit": "This validates the simulated API path and does not pass a physical integration, runtime, electrical, or safety gate.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _wait_for_processing(operator: Client, session_id: str) -> dict:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        snapshot = operator.json("GET", f"/api/v1/sessions/{session_id}")
        if snapshot["jobs"] and snapshot["jobs"][0]["state"] in {"complete", "failed"}:
            return snapshot
        time.sleep(0.25)
    raise TimeoutError(f"processing did not finish for session {session_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Week 6 software failure scenarios against a live PSYCON stack.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--operator-token", default="psycon-local-operator")
    parser.add_argument("--output", type=Path, default=Path("validation-output/software-api.json"))
    arguments = parser.parse_args()
    report = run_api_validation(arguments.url, arguments.operator_token, arguments.output)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

