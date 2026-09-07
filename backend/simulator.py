from __future__ import annotations

import argparse
import json
import math
import struct
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from protocol.chunk import encode_chunk_v2


VERSIONS = {
    "firmware": "simulator-1",
    "hardware": "simulated",
    "pcb": "simulated",
    "protocol": "2",
    "dataset": "week4-demo-1",
    "model": "0.1.0",
    "configuration": "local-demo-1",
    "calibration": "simulated-1",
    "documentation": "week4-1",
}


class Client:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def json(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.base_url + path, data=data, method=method, headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def chunk(self, session_id: str, packet: bytes) -> tuple[int, dict]:
        request = Request(self.base_url + f"/api/v1/sessions/{session_id}/chunks", data=packet, method="POST", headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/vnd.psycon.chunk-v2"})
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)


def audio_packet(device_id: int, sequence: int, timestamp_us: int, *, corrupt: bool = False) -> bytes:
    rate = 8_000
    samples = [round(7_500 * math.sin(2 * math.pi * 220 * index / rate)) for index in range(rate)]
    packet = encode_chunk_v2(stream_type="audio_pcm", device_id=device_id, sequence=sequence, device_timestamp_us=timestamp_us, sample_count=len(samples), sample_period_us=125, payload=struct.pack(f"<{len(samples)}h", *samples))
    if corrupt:
        damaged = bytearray(packet)
        damaged[-1] ^= 1
        return bytes(damaged)
    return packet


def wrist_packet(device_id: int, sequence: int, timestamp_us: int) -> bytes:
    records = []
    for index in range(25):
        records.append(struct.pack("<IIIHh", sequence * 25 + index, 50_000 + index * 2, 60_000 + index * 3, 1_200 + index, 3_150 + index // 5))
    payload = b"".join(records)
    return encode_chunk_v2(stream_type="wrist_batch", device_id=device_id, sequence=sequence, device_timestamp_us=timestamp_us, sample_count=25, sample_period_us=40_000, payload=payload)


def run(base_url: str, operator_token: str, scenario: str) -> str:
    return str(run_detailed(base_url, operator_token, scenario)["session_id"])


def run_detailed(base_url: str, operator_token: str, scenario: str) -> dict:
    operator = Client(base_url, operator_token)
    session = operator.json("POST", "/api/v1/sessions", {"anonymous_code": f"DEMO-{int(time.time())}", "versions": VERSIONS, "metadata": {"source": "deterministic simulator", "scenario": scenario}})["session"]
    session_id = session["id"]
    # Protocol v2 chunk identity is global, so repeated demo sessions need distinct
    # simulated provisioned IDs even though their per-stream sequences restart at zero.
    simulation_id = int(session_id.replace("-", "")[-7:], 16)
    devices = [
        (0xB0000000 | simulation_id, "simulated wrist"),
        (0xE0000000 | simulation_id, "simulated audio"),
    ]
    clients = {}
    for device_id, label in devices:
        issued = operator.json("POST", "/api/v1/devices", {"device_id": device_id, "label": label, "session_id": session_id})
        clients[device_id] = Client(base_url, issued["token"])
    epoch_us = time.time_ns() // 1_000
    for device_id, _ in devices:
        client = clients[device_id]
        for number in range(3):
            t0 = epoch_us + number * 1_000_000
            device = 5_000_000 + number * 1_000_020
            client.json("POST", f"/api/v1/sessions/{session_id}/clock-sync", {"device_id": device_id, "t0_backend_us": t0, "t1_device_us": device + 2_000, "t2_device_us": device + 2_500, "t3_backend_us": t0 + 5_000})
        client.json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": device_id, "event_type": "startup", "device_timestamp_us": 5_000_000, "payload": {"battery_mv": 3920, "queue_depth": 0, "overruns": 0, "sensor_ok": True}})
    clients[devices[0][0]].json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": devices[0][0], "event_type": "heartbeat", "device_timestamp_us": 5_500_000, "payload": {"battery_mv": 3914, "queue_depth": 1, "sensor_ok": True}})
    clients[devices[1][0]].json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": devices[1][0], "event_type": "light", "device_timestamp_us": 5_500_000, "payload": {"ambient_light_raw": 1837, "battery_mv": 3908, "microphone_ok": True}})
    wrist = clients[devices[0][0]]
    audio = clients[devices[1][0]]
    chunk_responses = []
    sequences = (0, 2, 3) if scenario == "communication-loss" else range(3)
    for sequence in sequences:
        timestamp = 6_000_000 + sequence * 1_000_000
        status, response = wrist.chunk(session_id, wrist_packet(devices[0][0], sequence, timestamp))
        chunk_responses.append({"device": "wrist", "sequence": sequence, "status": status, "response": response})
        if scenario != "missing-audio":
            status, response = audio.chunk(session_id, audio_packet(devices[1][0], sequence, timestamp, corrupt=scenario == "corrupt" and sequence == 1))
            chunk_responses.append({"device": "audio", "sequence": sequence, "status": status, "response": response})
    if scenario == "duplicate":
        status, response = wrist.chunk(session_id, wrist_packet(devices[0][0], 2, 8_000_000))
        chunk_responses.append({"device": "wrist", "sequence": 2, "status": status, "response": response})
    if scenario == "overrun":
        wrist.json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": devices[0][0], "event_type": "overrun", "device_timestamp_us": 9_000_000, "payload": {"queue_depth": 16, "overruns": 1, "dropped_chunks": 1}})
    if scenario == "sensor-failure":
        wrist.json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": devices[0][0], "event_type": "sensor_error", "device_timestamp_us": 9_000_000, "payload": {"sensor": "ads1115", "isolated": True, "other_sensors_running": True}})
    if scenario == "communication-loss":
        for device_id, _ in devices:
            clients[device_id].json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": device_id, "event_type": "reconnect", "device_timestamp_us": 10_000_000, "payload": {"gap_visible": True, "buffer_replayed": True}})
    if scenario == "watchdog":
        wrist.json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": devices[0][0], "event_type": "watchdog_reset", "device_timestamp_us": 9_000_000, "payload": {"reset_count": 1, "recovered": True}})
    operator.json("POST", f"/api/v1/sessions/{session_id}/process", {})
    post_close = None
    if scenario == "shutdown":
        for device_id, _ in devices:
            clients[device_id].json("POST", f"/api/v1/sessions/{session_id}/status", {"device_id": device_id, "event_type": "shutdown", "device_timestamp_us": 10_000_000, "payload": {"reason": "operator", "buffers_flushed": True}})
        operator.json("POST", f"/api/v1/sessions/{session_id}/close", {})
        status, response = wrist.chunk(session_id, wrist_packet(devices[0][0], 9, 15_000_000))
        post_close = {"status": status, "response": response}
    return {"session_id": session_id, "device_ids": {"wrist": devices[0][0], "audio": devices[1][0]}, "chunk_responses": chunk_responses, "post_close": post_close}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a deterministic dual-device session through the PSYCON HTTP API")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--operator-token", default="psycon-local-operator")
    parser.add_argument("--scenario", choices=["normal", "duplicate", "corrupt", "missing-audio", "overrun", "sensor-failure", "communication-loss", "watchdog", "shutdown"], default="normal")
    args = parser.parse_args()
    print(run(args.url, args.operator_token, args.scenario))


if __name__ == "__main__":
    main()
