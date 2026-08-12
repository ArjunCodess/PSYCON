from __future__ import annotations

import os
import hashlib
import io
import json
import time
import zipfile
from urllib.request import urlopen

import pytest

from backend.simulator import Client, run


BASE_URL = os.getenv("PSYCON_INTEGRATION_URL", "")


@pytest.mark.integration
@pytest.mark.skipif(not BASE_URL, reason="Set PSYCON_INTEGRATION_URL to a running Week 4 stack")
def test_simulated_session_reaches_processing_and_export() -> None:
    token = os.getenv("PSYCON_INTEGRATION_TOKEN", "psycon-local-operator")
    session_id = run(BASE_URL, token, "duplicate")
    operator = Client(BASE_URL, token)
    deadline = time.monotonic() + 30
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = operator.json("GET", f"/api/v1/sessions/{session_id}")
        if snapshot["jobs"] and snapshot["jobs"][0]["state"] == "complete":
            break
        time.sleep(0.5)
    assert snapshot is not None
    assert sum(int(stream["count"]) for stream in snapshot["streams"]) == 6
    assert all(stream["max_sync_uncertainty_us"] is not None for stream in snapshot["streams"])
    assert {event["event_type"] for event in snapshot["status"]} == {"heartbeat", "light"}
    assert snapshot["features"]
    assert all(item["state"] == "abstained" for item in snapshot["inferences"])
    created = operator.json("POST", f"/api/v1/sessions/{session_id}/exports", {})
    assert created["export"]["sha256"]
    latest = operator.json("GET", f"/api/v1/sessions/{session_id}/exports/latest")
    assert latest["download_url"].startswith("http://localhost:9000/")
    with urlopen(latest["download_url"], timeout=15) as response:
        archive_bytes = response.read()
    assert hashlib.sha256(archive_bytes).hexdigest() == created["export"]["sha256"]
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        status_events = json.loads(archive.read("metadata/status_events.json"))
        assert manifest["session_id"] == session_id
        assert {event["event_type"] for event in status_events} >= {"startup", "heartbeat", "light"}
        assert "metadata/session.json" in manifest["files"]
        assert len([name for name in manifest["files"] if name.startswith("raw/")]) == 6
        for name, expected in manifest["files"].items():
            payload = archive.read(name)
            assert len(payload) == expected["size"]
            assert hashlib.sha256(payload).hexdigest() == expected["sha256"]
