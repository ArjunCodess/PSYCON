from __future__ import annotations

import pytest

from validation.api_validation import SCENARIOS, assess_scenario


def snapshot(event: str = "heartbeat", *, missing: int = 0, state: str = "open", streams: tuple[str, ...] = ("wrist_batch", "audio_pcm")) -> dict:
    return {
        "session": {"state": state},
        "streams": [{"stream_type": name, "max_sync_uncertainty_us": 1000, "missing_sequence_count": missing} for name in streams],
        "status": [{"event_type": event}],
        "features": [{"modality": "wrist"}],
        "inferences": [{"state": "abstained"}],
        "jobs": [{"state": "complete"}],
    }


def details(responses=None, post_close=None) -> dict:
    return {"session_id": "session-1", "chunk_responses": responses or [], "post_close": post_close}


@pytest.mark.parametrize(
    ("scenario", "run_details", "state"),
    [
        ("normal", details([{"status": 201, "response": {}}] * 6), snapshot()),
        ("duplicate", details([{"status": 200, "response": {"status": "already_present"}}]), snapshot()),
        ("corrupt", details([{"status": 400, "response": {"error": {"code": "invalid_crc"}}}]), snapshot()),
        ("missing-audio", details(), snapshot(streams=("wrist_batch",))),
        ("overrun", details(), snapshot("overrun")),
        ("sensor-failure", details(), snapshot("sensor_error")),
        ("communication-loss", details(), snapshot("reconnect", missing=1)),
        ("watchdog", details(), snapshot("watchdog_reset")),
        ("shutdown", details(post_close={"status": 409}), snapshot("shutdown", state="complete")),
    ],
)
def test_scenario_acceptance(scenario: str, run_details: dict, state: dict) -> None:
    result = assess_scenario(scenario, run_details, state)
    assert result.passed
    assert all(result.checks.values())


def test_all_declared_scenarios_have_acceptance_logic() -> None:
    assert set(SCENARIOS) == {"normal", "duplicate", "corrupt", "missing-audio", "overrun", "sensor-failure", "communication-loss", "watchdog", "shutdown"}

