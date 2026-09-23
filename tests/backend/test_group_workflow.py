from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from flask import Flask

from backend.group.media import validate_video
from backend.group.memory import MemoryGroupStore
from backend.group.processing import build_processing_baseline
from backend.group.service import GroupObservationService
from backend.group_routes import group_api
from backend.routes import api, pages


ROOT = Path(__file__).resolve().parents[2]


class StoredObject:
    def __init__(self, key: str, sha256: str, size: int) -> None:
        self.key = key
        self.sha256 = sha256
        self.size = size


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[str, bytes]] = {}

    def put_immutable(self, key: str, data: bytes, content_type: str) -> StoredObject:
        del content_type
        digest = hashlib.sha256(data).hexdigest()
        existing = self.objects.get(key)
        if existing is not None and existing[0] != digest:
            raise ValueError("immutable object key already contains different bytes")
        self.objects[key] = (digest, data)
        return StoredObject(key, digest, len(data))

    def get(self, key: str) -> bytes:
        return self.objects[key][1]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def probe(_data: bytes) -> dict:
    return {
        "duration_s": 600.0,
        "width": 1280,
        "height": 720,
        "has_audio": True,
        "video_codec": "h264",
        "audio_codec": "aac",
        "timestamps_readable": True,
    }


def extractor(_data: bytes, recording: dict) -> dict:
    samples = np.zeros(16_000, dtype=np.int16)
    samples[:4000] = 1000
    return build_processing_baseline(
        source_sha256=recording["sha256"],
        duration_s=float(recording["duration_s"]),
        samples=samples,
        sample_rate_hz=16_000,
        turns=[
            {"cluster_label": "cluster-a", "start_s": 10, "end_s": 25, "overlap": True, "engine": "test_diarizer"},
            {"cluster_label": "cluster-b", "start_s": 20, "end_s": 40, "overlap": True, "engine": "test_diarizer"},
        ],
        transcript=[{"start_s": 10, "end_s": 25, "cluster_label": "cluster-a", "text": "the point was about water"}],
        frames=[{"time_s": 1, "visible_slots": [1, 2]}],
        seat_count=2,
        diarization_engine="test_diarizer",
    )


def build_app(service: GroupObservationService) -> Flask:
    app = Flask(__name__, template_folder=str(ROOT / "backend" / "templates"), static_folder=str(ROOT / "backend" / "static"))
    app.config.update(TESTING=True, SECRET_KEY="test")
    app.extensions["psycon_group"] = service
    app.register_blueprint(pages)
    app.register_blueprint(api)
    app.register_blueprint(group_api)
    return app


def box(kind: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + kind + payload


def mvhd(duration: int = 600) -> bytes:
    return b"\x00\x00\x00\x00" + b"\x00" * 8 + (1).to_bytes(4, "big") + duration.to_bytes(4, "big") + b"\x00" * 60


def track(handler: bytes, codec: bytes, width: int, height: int) -> bytes:
    tkhd = bytearray(84)
    tkhd[76:80] = int(width * 65536).to_bytes(4, "big")
    tkhd[80:84] = int(height * 65536).to_bytes(4, "big")
    hdlr = b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00" + handler + b"\x00" * 8
    entry = (16).to_bytes(4, "big") + codec + b"\x00" * 8
    stsd = b"\x00\x00\x00\x00" + (1).to_bytes(4, "big") + entry
    mdia = box(b"mdia", box(b"hdlr", hdlr) + box(b"minf", box(b"stbl", box(b"stsd", stsd))))
    return box(b"trak", box(b"tkhd", bytes(tkhd)) + mdia)


def mp4_bytes(*, audio: bool) -> bytes:
    tracks = track(b"vide", b"avc1", 1280, 720)
    if audio:
        tracks += track(b"soun", b"mp4a", 0, 0)
    ftyp = box(b"ftyp", b"isom" + b"\x00\x00\x00\x00" + b"isom")
    return ftyp + box(b"moov", box(b"mvhd", mvhd()) + tracks)


@pytest.fixture
def stack():
    service = GroupObservationService(MemoryGroupStore(), MemoryStorage(), probe=probe, extractor=extractor)
    operator, operator_token = service.provision_account(label="Operator One", role="operator", account_code="OP-1")
    psychologist, psychologist_token = service.provision_account(label="Rater One", role="psychologist", account_code="R-1")
    second, second_token = service.provision_account(label="Rater Two", role="psychologist", account_code="R-2")
    reviewer, reviewer_token = service.provision_account(label="Reviewer One", role="reviewer", account_code="RV-1")
    client = build_app(service).test_client()
    return {
        "service": service,
        "client": client,
        "operator": operator,
        "operator_token": operator_token,
        "psychologist": psychologist,
        "psychologist_token": psychologist_token,
        "second": second,
        "second_token": second_token,
        "reviewer": reviewer,
        "reviewer_token": reviewer_token,
    }


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def session_payload(**overrides) -> dict:
    payload = {
        "session_code": "CLS-2026-09-23-A",
        "session_date": "2026-09-23",
        "class_name": "10",
        "section": "A",
        "topic": "Shared water use",
        "language": "en",
        "moderator_code": "MOD-1",
        "camera_position": "front-center",
        "camera_orientation": "facing participants",
        "recording_start_time": "2026-09-23T09:00:00+05:30",
        "consent_status": "recorded",
        "consent_version": "group-consent-2.0",
        "participant_count": 2,
        "consent_identities": [{"form_line": 1, "legal_name": "Ada Example"}],
    }
    payload.update(overrides)
    return payload


def evidence_item(letter: str, score: str = "3") -> dict:
    item = {
        "item_letter": letter,
        "score": score,
        "fair_opportunity": True,
        "preceding_event": "The moderator restated the previous claim.",
        "observed_response": "The participant continued with the earlier point.",
        "intervals": [{"kind": "evidence", "start_s": 12, "end_s": 18, "description": "observed response"}],
    }
    if letter in "QRST":
        item["intervals"] = [
            {"kind": "baseline", "start_s": 10, "end_s": 12, "description": "earlier pace"},
            {"kind": "trigger", "start_s": 12, "end_s": 13, "description": "a peer disagreed with the claim"},
            {"kind": "evidence", "start_s": 13, "end_s": 18, "description": "delivery changed"},
        ]
    return item


def full_sheet(score: str = "N/O") -> list[dict]:
    rows = []
    for letter in "ABCDEFGHIJKLMNOPQRST":
        if score == "N/O":
            rows.append({"item_letter": letter, "score": "N/O", "no_score_reason": "no_opportunity"})
        elif score == "0":
            rows.append({"item_letter": letter, "score": "0", "fair_opportunity": True, "intervals": []})
        else:
            rows.append(evidence_item(letter, score))
    return rows


def test_video_validation_rejects_missing_audio_bad_magic_and_oversized_files() -> None:
    with pytest.raises(ValueError, match="original audio track"):
        validate_video("room.mp4", mp4_bytes(audio=False))
    with pytest.raises(ValueError, match="not an mp4"):
        validate_video("room.mp4", b"not-a-video")
    with pytest.raises(ValueError, match="2 GB"):
        validate_video("room.mp4", b"\x00\x00\x00\x14ftypisom", max_bytes=8)
    accepted = validate_video("room.mp4", mp4_bytes(audio=True))
    assert accepted["audio_codec"] == "aac"
    assert accepted["video_codec"] == "h264"
    assert "MAX_UPLOAD_BYTES = 12 * 1024 * 1024" in (ROOT / "demo" / "audio_web_app.py").read_text(encoding="utf-8")


def test_schema_keeps_device_sessions_and_adds_group_tables() -> None:
    schema = (ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")
    assert "participant_id UUID NOT NULL REFERENCES participants(id)" in schema
    for table in (
        "group_sessions",
        "group_participants",
        "recordings",
        "seat_assignments",
        "speaker_turns",
        "speaker_mappings",
        "marksheets",
        "item_ratings",
        "evidence_intervals",
        "reviews",
        "model_predictions",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    evaluation = (ROOT / "research" / "evaluation.py").read_text(encoding="utf-8")
    assert "binary labels" in evaluation
    assert "research.group_observation" in evaluation


def test_group_page_renders() -> None:
    service = GroupObservationService(MemoryGroupStore(), MemoryStorage(), probe=probe)
    client = build_app(service).test_client()
    page = client.get("/group")
    assert page.status_code == 200
    assert b"SESSION CONSOLE" in page.data
    assert b"dashboard.css" in page.data
    assert b"right side" in page.data


def test_roles_seats_mappings_marksheets_review_withdrawal_and_export(stack) -> None:
    client = stack["client"]
    service = stack["service"]
    created = client.post("/api/v1/group-sessions", json=session_payload(), headers=auth(stack["operator_token"]))
    assert created.status_code == 201
    body = created.get_json()["group_session"]
    session_id = body["session"]["id"]
    participants = body["participants"]
    listed = client.get("/api/v1/group-sessions", headers=auth(stack["operator_token"]))
    assert listed.status_code == 200
    assert session_id in {row["id"] for row in listed.get_json()["group_sessions"]}
    identity = client.get("/api/v1/group-accounts/me", headers=auth(stack["operator_token"]))
    assert identity.get_json()["account"]["id"] == stack["operator"]["id"]
    assert [person["label"] for person in participants] == ["Participant 1", "Participant 2"]
    assert "Ada Example" not in created.get_data(as_text=True)
    assert service.store.consent_records[0]["legal_name"] == "Ada Example"

    denied = client.put(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['operator']['id']}",
        json={"items": full_sheet()},
        headers=auth(stack["operator_token"]),
    )
    assert denied.status_code == 403
    anonymous = client.get(f"/api/v1/group-sessions/{session_id}")
    assert anonymous.status_code == 401

    video = client.post(
        f"/api/v1/group-sessions/{session_id}/recording",
        data={"file": (io.BytesIO(b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"), "room.mp4")},
        headers=auth(stack["operator_token"]),
        content_type="multipart/form-data",
    )
    assert video.status_code == 201
    assert video.get_json()["recording"]["sha256"]
    silent = client.post(
        f"/api/v1/group-sessions/{session_id}/recording",
        data={"file": (io.BytesIO(b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"), "room.mp4")},
        headers=auth(stack["operator_token"]),
        content_type="multipart/form-data",
    )
    assert silent.status_code == 400 or silent.status_code == 409

    frame = client.post(
        f"/api/v1/group-sessions/{session_id}/reference-frame",
        data={"file": (io.BytesIO(b"\xff\xd8\xff\xd9"), "frame.jpg")},
        headers=auth(stack["operator_token"]),
        content_type="multipart/form-data",
    )
    assert frame.status_code == 200
    wrong_order = client.put(
        f"/api/v1/group-sessions/{session_id}/participants",
        json={
            "confirmed": True,
            "camera_orientation": "facing participants",
            "frame_time_s": 1,
            "regions": [
                {"x": 0.05, "y": 0.2, "width": 0.2, "height": 0.5, "slot_number": 1},
                {"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.5, "slot_number": 2},
            ],
        },
        headers=auth(stack["operator_token"]),
    )
    assert wrong_order.status_code == 400
    assert "right to left" in wrong_order.get_json()["error"]["message"]
    overlap = client.put(
        f"/api/v1/group-sessions/{session_id}/participants",
        json={
            "confirmed": True,
            "frame_time_s": 1,
            "regions": [
                {"x": 0.4, "y": 0.2, "width": 0.3, "height": 0.5},
                {"x": 0.45, "y": 0.25, "width": 0.3, "height": 0.5},
            ],
        },
        headers=auth(stack["operator_token"]),
    )
    assert overlap.status_code == 400
    seated = client.put(
        f"/api/v1/group-sessions/{session_id}/participants",
        json={
            "confirmed": True,
            "camera_orientation": "facing participants",
            "frame_time_s": 1,
            "regions": [
                {"x": 0.05, "y": 0.2, "width": 0.2, "height": 0.5, "research_code": "P-LEFT"},
                {"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.5, "research_code": "P-RIGHT"},
            ],
        },
        headers=auth(stack["operator_token"]),
    )
    assert seated.status_code == 200
    seats = seated.get_json()["seats"]
    assert seats[0]["slot_number"] == 1
    assert seats[0]["center_x"] > seats[1]["center_x"]
    assert seats[0]["participant_id"] == participants[0]["id"]

    job = service.claim_job("test-worker")
    service.run_job(job)
    frames = service.store.recording_for_session(session_id)["processing"]["frames"]
    assert frames[0]["visible_slots"] == [1, 2]
    status = client.get(f"/api/v1/group-sessions/{session_id}/recording", headers=auth(stack["operator_token"]))
    assert status.get_json()["recording"]["processing_state"] == "complete"
    view = client.get(f"/api/v1/group-sessions/{session_id}", headers=auth(stack["operator_token"])).get_json()
    assert {turn["cluster_label"] for turn in view["speaker_turns"]} == {"cluster-a", "cluster-b"}
    assert all(turn["proposed_participant_id"] is None for turn in view["speaker_turns"])

    mapped = client.put(
        f"/api/v1/group-sessions/{session_id}/speaker-mappings",
        json={
            "mappings": [
                {"cluster_label": "cluster-a", "participant_id": participants[0]["id"], "status": "confirmed"},
                {"cluster_label": "cluster-b", "status": "unknown"},
            ]
        },
        headers=auth(stack["operator_token"]),
    )
    assert mapped.status_code == 200
    corrected = client.put(
        f"/api/v1/group-sessions/{session_id}/speaker-mappings",
        json={
            "mappings": [
                {"cluster_label": "cluster-a", "participant_id": participants[1]["id"], "status": "confirmed"},
                {"cluster_label": "cluster-b", "participant_id": participants[1]["id"], "status": "uncertain"},
            ]
        },
        headers=auth(stack["operator_token"]),
    )
    assert corrected.status_code == 200
    assert corrected.get_json()["revision"] == 2
    current = client.get(f"/api/v1/group-sessions/{session_id}", headers=auth(stack["operator_token"])).get_json()
    assert current["speaker_mappings"]["cluster-a"]["participant_id"] == participants[1]["id"]
    assert current["mapping_history_count"] == 4
    assert all(turn["cluster_label"] in {"cluster-a", "cluster-b"} for turn in current["speaker_turns"])

    first_items = full_sheet("N/O")
    first_items[0] = evidence_item("A", "3")
    saved = client.put(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}",
        json={"items": first_items},
        headers=auth(stack["psychologist_token"]),
    )
    assert saved.status_code == 200
    missing_evidence = full_sheet("N/O")
    missing_evidence[0] = {"item_letter": "A", "score": "3", "preceding_event": "short", "observed_response": "short", "intervals": []}
    missing = client.put(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[1]['id']}/marksheets/{stack['psychologist']['id']}",
        json={"items": missing_evidence},
        headers=auth(stack["psychologist_token"]),
    )
    assert missing.status_code == 400
    assert "evidence" in missing.get_json()["error"]["message"]
    submitted = client.post(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}/submit",
        headers=auth(stack["psychologist_token"]),
    )
    assert submitted.status_code == 200
    reviewer_sheet = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}",
        headers=auth(stack["reviewer_token"]),
    )
    assert reviewer_sheet.status_code == 200
    hidden = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}",
        headers=auth(stack["second_token"]),
    )
    assert hidden.status_code == 403
    independent = client.put(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['second']['id']}",
        json={"items": full_sheet("0")},
        headers=auth(stack["second_token"]),
    )
    assert independent.get_json()["marksheet"]["rating_role"] == "independent"
    client.post(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['second']['id']}/submit",
        headers=auth(stack["second_token"]),
    )
    disagreements = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/disagreements",
        headers=auth(stack["reviewer_token"]),
    )
    assert disagreements.status_code == 200
    assert any(row["item_letter"] == "A" for row in disagreements.get_json()["disagreements"])
    review = client.post(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/review",
        json={"reason": "The cited moment supports the higher score.", "items": first_items},
        headers=auth(stack["reviewer_token"]),
    )
    assert review.status_code == 200
    assert review.get_json()["originals_retained"] is True
    primary_after = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}",
        headers=auth(stack["psychologist_token"]),
    ).get_json()
    assert primary_after["items"][0]["score"] == "3"

    pdf = b"%PDF-1.4 SCORE-FROM-PDF-9"
    attached = client.post(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/attachments",
        data={"file": (io.BytesIO(pdf), "sheet.pdf")},
        headers=auth(stack["psychologist_token"]),
        content_type="multipart/form-data",
    )
    assert attached.status_code == 201
    assert attached.get_json()["attachment"]["pdf_text_used_as_labels"] is False
    foreign = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[1]['id']}/attachments/{attached.get_json()['attachment']['id']}",
        headers=auth(stack["psychologist_token"]),
    )
    assert foreign.status_code == 404

    blocked = client.get(f"/api/v1/group-sessions/{session_id}/export", headers=auth(stack["psychologist_token"]))
    assert blocked.status_code == 403
    package = client.get(f"/api/v1/group-sessions/{session_id}/export", headers=auth(stack["operator_token"])).get_json()
    encoded = json.dumps(package)
    assert "Ada Example" not in encoded
    assert "SCORE-FROM-PDF-9" not in encoded
    assert "consent/" not in encoded
    assert package["pdf_text_used_as_labels"] is False
    signed = client.post(
        f"/api/v1/group-sessions/{session_id}/consent-signatures",
        data={"form_line": "1", "file": (io.BytesIO(b"\xff\xd8signature-bytes"), "sign.jpg")},
        headers=auth(stack["operator_token"]),
        content_type="multipart/form-data",
    )
    assert signed.status_code == 201
    assert service.store.consent_records[0]["signature_object_key"]
    again = json.dumps(client.get(f"/api/v1/group-sessions/{session_id}/export", headers=auth(stack["operator_token"])).get_json())
    assert "signature-bytes" not in again
    assert "Ada Example" not in again
    no_score = next(row for row in package["examples"] if row["participant_id"] == participants[0]["id"] and row["item_letter"] == "B")
    assert no_score["score"] == "N/O"
    assert no_score["supervised_score"] is None
    rated = next(row for row in package["examples"] if row["item_letter"] == "A" and row["rating_role"] == "primary")
    assert rated["score"] == "3"
    assert rated["source_recording_sha256"] == package["recording_sha256"]

    before = primary_after["items"][0]["score"]
    predictions = client.post(f"/api/v1/group-sessions/{session_id}/predictions", headers=auth(stack["psychologist_token"])).get_json()
    after = client.get(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[0]['id']}/marksheets/{stack['psychologist']['id']}",
        headers=auth(stack["psychologist_token"]),
    ).get_json()
    assert after["items"][0]["score"] == before
    for prediction in predictions["predictions"]:
        if prediction["playback_fragment"]:
            start, end = prediction["playback_fragment"].removeprefix("#t=").split(",")
            assert float(end) > float(start)
            assert prediction["evidence_start_s"] == float(start)
    assert predictions["ratings_unchanged"] is True

    withdrawn = client.post(
        f"/api/v1/group-sessions/{session_id}/participants/{participants[1]['id']}/withdraw",
        json={"reason": "participant withdrew"},
        headers=auth(stack["operator_token"]),
    )
    assert "peers" in withdrawn.get_json()["note"]
    exported = client.get(f"/api/v1/group-sessions/{session_id}/export", headers=auth(stack["operator_token"])).get_json()
    assert participants[1]["id"] not in {row["participant_id"] for row in exported["examples"]}
    assert exported["recording_sha256"] == package["recording_sha256"]
    actions = {row["action"] for row in service.store.audits_for(session_id)}
    assert {"upload_recording", "assign_seats", "map_speakers", "submit_marksheet", "export", "withdraw_participant"} <= actions
    assert all("Ada Example" not in json.dumps(row) for row in service.store.audits_for(session_id))
