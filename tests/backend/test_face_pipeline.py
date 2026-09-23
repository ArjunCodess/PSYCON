from __future__ import annotations

import io

import numpy as np

from backend.group.faces import face_feature, number_faces
from backend.group.labels import parse_label_csv
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupObservationService
from research.face_training import train_face_items
from tests.backend.test_group_workflow import MemoryStorage, auth, build_app, probe


def test_faces_are_numbered_from_the_right() -> None:
    numbered = number_faces(
        [
            {"x": 0.05, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [0.0]},
            {"x": 0.72, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [1.0]},
            {"x": 0.40, "y": 0.4, "width": 0.12, "height": 0.2, "feature": [0.5]},
        ]
    )
    assert [face["slot_number"] for face in numbered] == [1, 2, 3]
    assert numbered[0]["x"] == 0.72
    image = np.full((32, 32, 3), 30, dtype=np.uint8)
    assert len(face_feature(image, (0.1, 0.1, 0.4, 0.4))) == 80


def test_spreadsheet_uses_marked_participant_numbers() -> None:
    text = "participant,class,A,B,T\n1,10-A,0,2,N/O\nParticipant 2,9-B,1,NO,4\n"
    rows = parse_label_csv(text.encode())
    assert rows[0]["class_name"] == "10-A"
    assert rows[0]["scores"] == {"A": "0", "B": "2", "T": "N/O"}
    assert rows[1]["slot_number"] == 2
    assert rows[1]["class_name"] == "9-B"
    assert rows[1]["scores"]["B"] == "N/O"


def test_upload_marks_faces_and_stores_the_spreadsheet() -> None:
    def marker(_data: bytes) -> dict:
        return {
            "jpeg": b"\xff\xd8marked",
            "time_s": 0,
            "faces": [
                {"x": 0.08, "y": 0.35, "width": 0.16, "height": 0.22, "feature": [0.1] * 80},
                {"x": 0.70, "y": 0.35, "width": 0.16, "height": 0.22, "feature": [0.9] * 80},
            ],
        }

    service = GroupObservationService(MemoryGroupStore(), MemoryStorage(), probe=probe, face_marker=marker)
    _operator, token = service.provision_account(label="Operator", role="operator", account_code="OP-FACE")
    client = build_app(service).test_client()
    uploaded = client.post(
        "/api/v1/group-sessions/from-video",
        data={"file": (io.BytesIO(b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"), "WhatsApp Video 2026-09-23 at 11.35.12 PM.mp4")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    body = uploaded.get_json()
    assert body["face_count"] == 2
    assert body["marked_frame_base64"]
    session_id = body["group_session"]["session"]["id"]
    seats = body["group_session"]["seats"]
    assert seats[0]["slot_number"] == 1
    assert seats[0]["center_x"] > seats[1]["center_x"]
    assert body["group_session"]["session"]["session_code"] == "WhatsApp-Video-2026-09-23-at-11.35.12-PM"
    sheet = "participant,class,A,T\n1,10-A,3,1\n2,9-B,0,4\n".encode()
    stored = client.post(
        f"/api/v1/group-sessions/{session_id}/labels",
        data={"file": (io.BytesIO(sheet), "session.csv")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert stored.status_code == 200
    assert stored.get_json()["participants"] == [1, 2]
    assert stored.get_json()["classes"] == {"1": "10-A", "2": "9-B"}
    missing = client.post(
        f"/api/v1/group-sessions/{session_id}/labels",
        data={"file": (io.BytesIO(b"participant,A\n9,1\n"), "bad.csv")},
        headers=auth(token),
        content_type="multipart/form-data",
    )
    assert missing.status_code == 400
    page = client.get("/group")
    assert b"Submit recording" in page.data
    assert b"Submit spreadsheet" in page.data
    assert b'id="intake-video"' in page.data
    assert b'id="screen-mark" class="intake-screen" hidden' in page.data


def test_image_training_stays_unavailable_until_enough_sessions_exist() -> None:
    one = train_face_items(
        [
            {
                "group_session_id": "s1",
                "slot_number": 1,
                "item_letter": "T",
                "score": "2",
                "feature": [0.2] * 80,
            }
        ]
    )
    assert one["items"][0]["status"] == "unavailable"
    assert one["validated_psychological_result"] is False
    examples = []
    for session in range(5):
        examples.append(
            {
                "group_session_id": f"s{session}",
                "slot_number": 1,
                "item_letter": "T",
                "score": "1",
                "feature": [float(session), 0.1] + [0.0] * 78,
            }
        )
        examples.append(
            {
                "group_session_id": f"s{session}",
                "slot_number": 2,
                "item_letter": "T",
                "score": "3",
                "feature": [float(session), 0.9] + [0.0] * 78,
            }
        )
    fitted = train_face_items(examples, seed=42)
    item = fitted["items"][0]
    assert item["status"] == "fitted"
    assert item["test_metrics"]["test_examples"] > 0
