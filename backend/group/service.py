"""Operator, psychologist, and reviewer workflows for one shared recording."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from backend.auth import Principal, create_token, hash_token
from research.group_observation import (
    associate_turns,
    build_training_examples,
    interpret_examples,
    playback_fragment,
    predict_examples,
)

from .errors import GroupError
from .extract import extract_group_recording
from .media import MediaError, validate_video
from .rubric import CONSENT_VERSION, MARKSHEET_VERSION, PROTOCOL_VERSION, RubricError, validate_marksheet
from .seats import MAX_PARTICIPANTS, MIN_PARTICIPANTS, SeatError, order_seats


_SESSION_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_ACCOUNT_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")
_RESEARCH_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,31}$")
_ROLES = {"operator", "psychologist", "reviewer"}
_CONSENT_STATES = {"pending", "recorded", "refused"}
_MAX_PDF_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_GRANT_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


class GroupObservationService:
    def __init__(self, store, storage, *, probe: Callable | None = None, extractor: Callable | None = None) -> None:
        self.store = store
        self.storage = storage
        self.probe = probe
        self.extractor = extractor or extract_group_recording

    def authenticate(self, token: str) -> Principal | None:
        account = self.store.account_by_token(hash_token(token))
        if account is None:
            return None
        return Principal(account["id"], account["role"], None, account["label"])

    def provision_account(self, *, label: str, role: str, account_code: str) -> tuple[dict, str]:
        cleaned_role = role.strip()
        cleaned_code = account_code.strip().upper()
        cleaned_label = label.strip()
        if cleaned_role not in _ROLES or not cleaned_label or not _ACCOUNT_CODE.fullmatch(cleaned_code):
            raise GroupError("invalid_account", "A named account needs a label, an account code, and a known role", 400)
        token = create_token()
        try:
            account = self.store.insert_account(
                {
                    "id": str(uuid4()),
                    "label": cleaned_label,
                    "role": cleaned_role,
                    "account_code": cleaned_code,
                    "token_hash": hash_token(token),
                    "revoked_at": None,
                    "created_at": _stamp(),
                }
            )
        except ValueError as exc:
            raise GroupError("duplicate_account", str(exc), 409) from exc
        public = {key: account[key] for key in ("id", "label", "role", "account_code", "created_at")}
        return public, token

    def create_session(self, actor: Principal, payload: dict) -> dict:
        self._require(actor, "operator")
        session_code = str(payload.get("session_code") or "").strip()
        if not _SESSION_CODE.fullmatch(session_code):
            raise GroupError("invalid_session", "session_code must be 3 to 64 letters, numbers, dots, or dashes", 400)
        try:
            participant_count = int(payload.get("participant_count"))
        except (TypeError, ValueError) as exc:
            raise GroupError("invalid_session", "participant_count must be between 2 and 10", 400) from exc
        if not MIN_PARTICIPANTS <= participant_count <= MAX_PARTICIPANTS:
            raise GroupError("invalid_session", "participant_count must be between 2 and 10", 400)
        consent_status = str(payload.get("consent_status") or "")
        if consent_status not in _CONSENT_STATES:
            raise GroupError("invalid_session", "consent_status must be pending, recorded, or refused", 400)
        if str(payload.get("consent_version") or CONSENT_VERSION) != CONSENT_VERSION:
            raise GroupError("invalid_session", f"group sessions require consent version {CONSENT_VERSION}", 400)
        self._parse_time(payload.get("recording_start_time"), "recording_start_time")
        self._date(payload.get("session_date"))
        session_id = str(uuid4())
        row = {
            "id": session_id,
            "session_code": session_code,
            "session_date": str(payload.get("session_date")),
            "class_name": self._text(payload, "class_name"),
            "section": self._text(payload, "section"),
            "topic": self._text(payload, "topic"),
            "language": self._text(payload, "language"),
            "moderator_code": self._text(payload, "moderator_code"),
            "camera_position": self._text(payload, "camera_position"),
            "camera_orientation": self._text(payload, "camera_orientation"),
            "recording_start_time": str(payload.get("recording_start_time")),
            "consent_status": consent_status,
            "consent_version": CONSENT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "participant_count": participant_count,
            "state": "collecting",
            "created_by": actor.id,
            "created_at": _stamp(),
            "marked_frame_object_key": None,
            "recording_disposition": "retain_under_session_protocol",
        }
        try:
            self.store.insert_session(row)
        except ValueError as exc:
            raise GroupError("duplicate_session", str(exc), 409) from exc
        participants = []
        for slot in range(1, participant_count + 1):
            participants.append(
                self.store.insert_participant(
                    {
                        "id": str(uuid4()),
                        "group_session_id": session_id,
                        "slot_number": slot,
                        "anonymous_code": f"P{slot:02d}",
                        "label": f"Participant {slot}",
                        "research_code": None,
                        "withdrawn_at": None,
                    }
                )
            )
        for identity in payload.get("consent_identities") or []:
            legal_name = str(identity.get("legal_name") or "").strip()
            if not legal_name:
                raise GroupError("invalid_consent", "A consent identity needs a name stored only on the consent record", 400)
            self.store.insert_consent(
                {
                    "id": str(uuid4()),
                    "group_session_id": session_id,
                    "form_line": int(identity.get("form_line") or 0),
                    "legal_name": legal_name,
                    "signature_object_key": None,
                    "created_at": _stamp(),
                }
            )
        self._audit(actor, "create", session_id, {"participant_count": participant_count, "consent_version": CONSENT_VERSION})
        return self._view(actor, session_id, participants=participants)

    def get_session(self, actor: Principal, session_id: str) -> dict:
        self._require(actor, "operator", "psychologist", "reviewer")
        return self._view(actor, session_id)

    def list_sessions(self, actor: Principal) -> list[dict]:
        self._require(actor, "operator", "psychologist", "reviewer")
        summaries = []
        for row in self.store.list_sessions():
            recording = self.store.recording_for_session(row["id"])
            summaries.append(
                {
                    "id": row["id"],
                    "session_code": row["session_code"],
                    "session_date": row["session_date"],
                    "consent_status": row["consent_status"],
                    "consent_version": row["consent_version"],
                    "state": row["state"],
                    "participant_count": row["participant_count"],
                    "language": row["language"],
                    "topic": row["topic"],
                    "recording_state": None if recording is None else recording["processing_state"],
                }
            )
        return summaries

    def upload_recording(self, actor: Principal, session_id: str, filename: str, data: bytes) -> dict:
        self._require(actor, "operator")
        self._session(session_id)
        if self.store.recording_for_session(session_id):
            raise GroupError("recording_exists", "A group session keeps one recording", 409)
        try:
            inspected = validate_video(filename, data, probe=self.probe)
        except MediaError as exc:
            raise GroupError("invalid_recording", str(exc), 400) from exc
        digest = hashlib.sha256(data).hexdigest()
        key = f"group-recordings/{session_id}/original"
        stored = self.storage.put_immutable(key, data, "video/mp4")
        recording = self.store.insert_recording(
            {
                "id": str(uuid4()),
                "group_session_id": session_id,
                "object_key": stored.key,
                "sha256": digest,
                "filename": PathName(filename),
                "content_type": "video/mp4",
                "size_bytes": stored.size,
                "duration_s": inspected["duration_s"],
                "video_codec": inspected["video_codec"],
                "audio_codec": inspected["audio_codec"],
                "width": inspected["width"],
                "height": inspected["height"],
                "timestamps_readable": True,
                "processing_state": "queued",
                "failure_reason": None,
                "quality_state": "unprocessed",
                "processing": {},
                "tool_version": None,
            }
        )
        if stored.sha256 != digest:
            raise GroupError("storage_error", "Stored recording hash did not match the upload", 500)
        job = self.store.enqueue_job(
            {"id": str(uuid4()), "group_session_id": session_id, "job_type": "process_recording", "state": "queued", "error": None}
        )
        self._audit(actor, "upload_recording", session_id, {"sha256": digest, "job_id": job["id"]})
        return {"recording": _public_recording(recording), "job": job}

    def upload_reference_frame(self, actor: Principal, session_id: str, filename: str, data: bytes) -> dict:
        self._require(actor, "operator")
        self._session(session_id)
        if len(data) > _MAX_IMAGE_BYTES or not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG")):
            raise GroupError("invalid_frame", "The reference frame must be a JPEG or PNG under 5 MB", 400)
        key = f"group-recordings/{session_id}/reference-frame"
        stored = self.storage.put_immutable(key, data, "image/jpeg" if data.startswith(b"\xff\xd8") else "image/png")
        self.store.update_session(session_id, marked_frame_object_key=stored.key)
        self._audit(actor, "reference_frame", session_id, {"sha256": stored.sha256})
        return {"object_key": stored.key, "sha256": stored.sha256}

    def assign_seats(self, actor: Principal, session_id: str, payload: dict) -> dict:
        self._require(actor, "operator")
        session = self._session(session_id)
        recording = self._recording(session_id)
        if not payload.get("confirmed"):
            raise GroupError("unconfirmed_seats", "Seat assignment must be explicitly confirmed", 400)
        if not session.get("marked_frame_object_key"):
            raise GroupError("missing_frame", "Upload the frame that shows every participant before assigning seats", 400)
        orientation = str(payload.get("camera_orientation") or session["camera_orientation"]).strip()
        if not orientation:
            raise GroupError("invalid_seats", "camera orientation is required", 400)
        try:
            frame_time = float(payload.get("frame_time_s", 0))
            ordered = order_seats(list(payload.get("regions") or []), duration_s=float(recording["duration_s"]))
        except (SeatError, TypeError, ValueError) as exc:
            raise GroupError("invalid_seats", str(exc), 400) from exc
        participants = sorted(self.store.participants(session_id), key=lambda item: item["slot_number"])
        if len(ordered) != len(participants):
            raise GroupError("invalid_seats", "Mark one seat for every participant slot", 400)
        if frame_time < 0 or frame_time > float(recording["duration_s"]):
            raise GroupError("invalid_seats", "The marked frame time must fall inside the recording", 400)
        rows = []
        for region, participant in zip(ordered, participants):
            research_code = region.get("research_code") or (payload.get("research_codes") or {}).get(str(region["slot_number"]))
            if research_code:
                research_code = str(research_code).strip().upper()
                if not _RESEARCH_CODE.fullmatch(research_code):
                    raise GroupError("invalid_participant", "research codes are anonymous identifiers such as P-7F3A", 400)
                self.store.update_participant(participant["id"], research_code=research_code)
            rows.append(
                {
                    "id": str(uuid4()),
                    "group_session_id": session_id,
                    "participant_id": participant["id"],
                    "slot_number": region["slot_number"],
                    "label": region["label"],
                    "x": region["x"],
                    "y": region["y"],
                    "width": region["width"],
                    "height": region["height"],
                    "center_x": region["center_x"],
                    "valid_from_s": region["valid_from_s"],
                    "valid_to_s": region["valid_to_s"],
                    "camera_orientation": orientation,
                    "marked_frame_object_key": session["marked_frame_object_key"],
                    "frame_time_s": frame_time,
                    "confirmed_by": actor.id,
                    "confirmed_at": _stamp(),
                }
            )
        self.store.replace_seats(session_id, rows)
        self.store.update_session(session_id, camera_orientation=orientation)
        self._mark_visible_seats(session_id)
        self._audit(actor, "assign_seats", session_id, {"slots": [row["slot_number"] for row in rows], "camera_orientation": orientation})
        return {"seats": rows}

    def map_speakers(self, actor: Principal, session_id: str, payload: dict) -> dict:
        self._require(actor, "operator")
        self._session(session_id)
        turns = self.store.turns_for(session_id)
        clusters = sorted({turn["cluster_label"] for turn in turns})
        if not clusters:
            raise GroupError("missing_clusters", "Speaker clusters are not available yet", 409)
        incoming = payload.get("mappings")
        if not isinstance(incoming, list):
            raise GroupError("invalid_mapping", "mappings must list every cluster", 400)
        labels = [str(item.get("cluster_label") or "") for item in incoming]
        if sorted(labels) != clusters or len(labels) != len(set(labels)):
            raise GroupError("invalid_mapping", "Map every anonymous cluster explicitly. Speaker numbers are not participant numbers", 400)
        previous = _current_mappings(self.store.mappings_for(session_id))
        revision = 1 + max((row["revision"] for row in self.store.mappings_for(session_id)), default=0)
        participants = {row["id"]: row for row in self.store.participants(session_id)}
        stored = []
        for item in incoming:
            status = str(item.get("status") or "")
            participant_id = item.get("participant_id")
            if status not in {"confirmed", "uncertain", "unknown"}:
                raise GroupError("invalid_mapping", "mapping status must be confirmed, uncertain, or unknown", 400)
            if status == "unknown" and participant_id:
                raise GroupError("invalid_mapping", "An unknown cluster cannot be given a participant", 400)
            if status == "confirmed" and participant_id not in participants:
                raise GroupError("invalid_mapping", "Confirmed mappings must name a participant slot in this session", 400)
            if status == "uncertain" and participant_id is not None and participant_id not in participants:
                raise GroupError("invalid_mapping", "Uncertain mappings must name a participant slot or stay empty", 400)
            if status != "confirmed":
                participant_id = participant_id if status == "uncertain" else None
            stored.append(
                {
                    "id": str(uuid4()),
                    "group_session_id": session_id,
                    "cluster_label": item["cluster_label"],
                    "participant_id": participant_id,
                    "status": status,
                    "note": str(item.get("note") or "")[:240],
                    "mapped_by": actor.id,
                    "mapped_at": _stamp(),
                    "revision": revision,
                }
            )
        self.store.add_mappings(stored)
        self._audit(
            actor,
            "map_speakers",
            session_id,
            {
                "revision": revision,
                "previous": {label: row.get("participant_id") for label, row in previous.items()},
                "current": {row["cluster_label"]: row["participant_id"] for row in stored},
            },
        )
        return {"revision": revision, "mappings": stored, "history_retained": True}

    def get_marksheet(self, actor: Principal, session_id: str, participant_id: str, rater_id: str) -> dict:
        self._require(actor, "psychologist", "reviewer")
        self._participant(session_id, participant_id)
        sheet = _latest(self.store.marksheets_for_participant(participant_id), rater_id=rater_id)
        if sheet is None:
            raise GroupError("marksheet_not_found", "No marksheet exists for this rater", 404)
        if actor.id != rater_id:
            if not (actor.role == "reviewer" and sheet["state"] == "submitted"):
                raise GroupError("blind_rating", "Another rater's scores stay hidden", 403)
        return sheet

    def save_marksheet(self, actor: Principal, session_id: str, participant_id: str, rater_id: str, payload: dict) -> dict:
        self._require(actor, "psychologist")
        if actor.id != rater_id:
            raise GroupError("blind_rating", "Ratings are stored on the named psychologist account", 403)
        participant = self._participant(session_id, participant_id)
        if participant.get("withdrawn_at"):
            raise GroupError("withdrawn", "Withdrawn participant labels are closed", 409)
        try:
            items = validate_marksheet(list(payload.get("items") or []), strict=False)
        except RubricError as exc:
            raise GroupError("invalid_marksheet", str(exc), 400) from exc
        existing = _latest(self.store.marksheets_for_participant(participant_id), rater_id=rater_id)
        if existing and existing["state"] == "submitted":
            raise GroupError("immutable_marksheet", "Submitted ratings stay unchanged. Record a reviewer correction", 409)
        role = existing["rating_role"] if existing else self._rating_role(participant_id, rater_id)
        sheet = existing or {
            "id": str(uuid4()),
            "group_session_id": session_id,
            "participant_id": participant_id,
            "rater_id": rater_id,
            "rating_role": role,
            "revision": 1,
            "marksheet_version": MARKSHEET_VERSION,
            "created_at": _stamp(),
        }
        sheet.update({"state": "draft", "submitted_at": None, "items": items, "updated_at": _stamp()})
        return self.store.save_marksheet(sheet)

    def submit_marksheet(self, actor: Principal, session_id: str, participant_id: str, rater_id: str) -> dict:
        self._require(actor, "psychologist")
        if actor.id != rater_id:
            raise GroupError("blind_rating", "Only the named psychologist can submit these ratings", 403)
        sheet = _latest(self.store.marksheets_for_participant(participant_id), rater_id=rater_id)
        if sheet is None:
            raise GroupError("marksheet_not_found", "Save a draft before submitting", 404)
        try:
            items = validate_marksheet(sheet["items"], strict=True)
        except RubricError as exc:
            raise GroupError("invalid_marksheet", str(exc), 400) from exc
        sheet["items"] = items
        sheet["state"] = "submitted"
        sheet["submitted_at"] = _stamp()
        saved = self.store.save_marksheet(sheet)
        self._audit(
            actor,
            "submit_marksheet",
            session_id,
            {
                "participant_id": participant_id,
                "rater_id": rater_id,
                "marksheet_version": MARKSHEET_VERSION,
                "submitted_at": saved["submitted_at"],
                "rating_role": saved["rating_role"],
            },
        )
        return saved

    def correct_marksheet(self, actor: Principal, session_id: str, participant_id: str, rater_id: str, payload: dict) -> dict:
        self._require(actor, "reviewer")
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 8:
            raise GroupError("invalid_correction", "A correction needs a reviewer reason", 400)
        original = _latest(self.store.marksheets_for_participant(participant_id), rater_id=rater_id)
        if original is None or original["state"] != "submitted":
            raise GroupError("marksheet_not_found", "Corrections apply to a submitted marksheet", 404)
        try:
            items = validate_marksheet(list(payload.get("items") or []), strict=True)
        except RubricError as exc:
            raise GroupError("invalid_marksheet", str(exc), 400) from exc
        changes = _score_changes(original["items"], items)
        corrected = {
            **original,
            "id": str(uuid4()),
            "revision": original["revision"] + 1,
            "items": items,
            "supersedes_id": original["id"],
            "state": "submitted",
            "submitted_at": _stamp(),
            "corrected_by": actor.id,
            "correction_reason": reason,
        }
        saved = self.store.save_marksheet(corrected)
        self._audit(
            actor,
            "correct_marksheet",
            session_id,
            {"participant_id": participant_id, "rater_id": rater_id, "reviewer_id": actor.id, "reason": reason, "changes": changes},
        )
        return saved

    def review(self, actor: Principal, session_id: str, participant_id: str, payload: dict) -> dict:
        self._require(actor, "reviewer")
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 8:
            raise GroupError("invalid_review", "Adjudication needs a reviewer reason", 400)
        sheets = self.store.marksheets_for_participant(participant_id)
        primary = _latest_role(sheets, "primary")
        independent = _latest_role(sheets, "independent")
        if primary is None or independent is None or primary["state"] != "submitted" or independent["state"] != "submitted":
            raise GroupError("review_not_ready", "Adjudication waits for two submitted ratings", 409)
        try:
            items = validate_marksheet(list(payload.get("items") or []), strict=True)
        except RubricError as exc:
            raise GroupError("invalid_marksheet", str(exc), 400) from exc
        adjudicated = self.store.save_marksheet(
            {
                "id": str(uuid4()),
                "group_session_id": session_id,
                "participant_id": participant_id,
                "rater_id": actor.id,
                "rating_role": "adjudicated",
                "revision": 1,
                "marksheet_version": MARKSHEET_VERSION,
                "state": "submitted",
                "submitted_at": _stamp(),
                "created_at": _stamp(),
                "items": items,
            }
        )
        changes = []
        primary_scores = {item["item_letter"]: item.get("score") for item in primary["items"]}
        independent_scores = {item["item_letter"]: item.get("score") for item in independent["items"]}
        for item in items:
            letter = item["item_letter"]
            if primary_scores.get(letter) != independent_scores.get(letter) or item["score"] not in {primary_scores.get(letter), independent_scores.get(letter)}:
                changes.append(
                    {
                        "item_letter": letter,
                        "primary": primary_scores.get(letter),
                        "independent": independent_scores.get(letter),
                        "adjudicated": item["score"],
                    }
                )
        review = self.store.add_review(
            {
                "id": str(uuid4()),
                "group_session_id": session_id,
                "participant_id": participant_id,
                "primary_marksheet_id": primary["id"],
                "independent_marksheet_id": independent["id"],
                "adjudicated_marksheet_id": adjudicated["id"],
                "reviewer_id": actor.id,
                "reason": reason,
                "changes": changes,
                "created_at": _stamp(),
            }
        )
        self._audit(actor, "review_marksheet", session_id, {"participant_id": participant_id, "review_id": review["id"], "change_count": len(changes)})
        return {"review": review, "adjudicated": adjudicated, "originals_retained": True}

    def disagreements(self, actor: Principal, session_id: str, participant_id: str) -> dict:
        self._require(actor, "reviewer")
        self._participant(session_id, participant_id)
        sheets = self.store.marksheets_for_participant(participant_id)
        primary = _latest_role(sheets, "primary")
        independent = _latest_role(sheets, "independent")
        if primary is None or independent is None or primary["state"] != "submitted" or independent["state"] != "submitted":
            raise GroupError("review_not_ready", "Disagreements appear after both ratings are submitted", 409)
        rows = []
        independent_items = {item["item_letter"]: item for item in independent["items"]}
        for item in primary["items"]:
            other = independent_items.get(item["item_letter"], {})
            if item.get("score") != other.get("score"):
                rows.append({"item_letter": item["item_letter"], "primary": item.get("score"), "independent": other.get("score")})
        return {"participant_id": participant_id, "disagreements": rows, "primary_rater_id": primary["rater_id"], "independent_rater_id": independent["rater_id"]}

    def attach_pdf(self, actor: Principal, session_id: str, participant_id: str, filename: str, data: bytes) -> dict:
        self._require(actor, "psychologist", "operator")
        self._participant(session_id, participant_id)
        if not data.startswith(b"%PDF-") or len(data) > _MAX_PDF_BYTES:
            raise GroupError("invalid_attachment", "The attachment must be a PDF under 20 MB", 400)
        key = f"group-recordings/{session_id}/participants/{participant_id}/marksheet.pdf"
        stored = self.storage.put_immutable(key, data, "application/pdf")
        attachment = self.store.add_attachment(
            {
                "id": str(uuid4()),
                "group_session_id": session_id,
                "participant_id": participant_id,
                "object_key": stored.key,
                "sha256": stored.sha256,
                "filename": PathName(filename),
                "byte_size": stored.size,
                "uploaded_by": actor.id,
                "created_at": _stamp(),
                "pdf_text_used_as_labels": False,
            }
        )
        self._audit(actor, "attach_pdf", session_id, {"participant_id": participant_id, "sha256": stored.sha256})
        return {key: attachment[key] for key in ("id", "participant_id", "sha256", "filename", "byte_size", "pdf_text_used_as_labels")}

    def attachment_bytes(self, actor: Principal, session_id: str, participant_id: str, attachment_id: str) -> tuple[bytes, dict]:
        self._require(actor, "psychologist", "reviewer", "operator")
        self._participant(session_id, participant_id)
        found = next((row for row in self.store.attachments_for(participant_id) if row["id"] == attachment_id), None)
        if found is None:
            raise GroupError("attachment_not_found", "This PDF belongs to another participant slot", 404)
        self._audit(actor, "read_attachment", session_id, {"participant_id": participant_id, "attachment_id": attachment_id})
        return self.storage.get(found["object_key"]), found

    def issue_playback(self, actor: Principal, session_id: str) -> dict:
        self._require(actor, "operator", "psychologist", "reviewer")
        recording = self._recording(session_id)
        token = create_token()
        expires = _now() + timedelta(minutes=_GRANT_MINUTES)
        self.store.add_grant(
            hash_token(token),
            {"group_session_id": session_id, "account_id": actor.id, "expires_at": _stamp(expires), "object_key": recording["object_key"]},
        )
        self._audit(actor, "playback_grant", session_id, {"expires_at": _stamp(expires)})
        return {
            "playback_token": token,
            "expires_at": _stamp(expires),
            "media_path": f"/api/v1/group-sessions/{session_id}/recording/media",
        }

    def read_media(self, session_id: str, playback_token: str) -> tuple[bytes, str]:
        grant = self.store.grant(hash_token(playback_token or ""))
        if grant is None or grant["group_session_id"] != session_id or grant["expires_at"] < _stamp():
            raise GroupError("unauthorized", "A current playback grant is required", 401)
        self._audit(Principal(grant["account_id"], "operator", None, ""), "read_recording", session_id, {})
        recording = self._recording(session_id)
        return self.storage.get(recording["object_key"]), recording["content_type"]

    def read_reference_frame(self, actor: Principal, session_id: str) -> tuple[bytes, str]:
        self._require(actor, "operator", "psychologist", "reviewer")
        session = self._session(session_id)
        key = session.get("marked_frame_object_key")
        if not key:
            raise GroupError("missing_frame", "No reference frame has been uploaded", 404)
        self._audit(actor, "read_reference_frame", session_id, {})
        data = self.storage.get(key)
        content_type = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        return data, content_type

    def withdraw_participant(self, actor: Principal, session_id: str, participant_id: str, payload: dict) -> dict:
        self._require(actor, "operator")
        participant = self._participant(session_id, participant_id)
        self.store.update_participant(participant_id, withdrawn_at=_stamp())
        session = self.store.session(session_id)
        self._audit(actor, "withdraw_participant", session_id, {"participant_id": participant_id, "reason": str(payload.get("reason") or "")[:240]})
        return {
            "participant_id": participant_id,
            "anonymous_code": participant["anonymous_code"],
            "withdrawn_at": self.store.participant(session_id, participant_id)["withdrawn_at"],
            "recording_disposition": session["recording_disposition"],
            "note": "Labels and derived rows leave future dataset versions. The shared recording also contains peers, so its file follows the session retention protocol.",
        }

    def delete_session(self, actor: Principal, session_id: str) -> None:
        self._require(actor, "operator")
        self._session(session_id)
        keys = self.store.delete_session(session_id)
        for key in keys:
            self.storage.delete(key)
        self._audit(actor, "delete_session", session_id, {"object_count": len(keys)})

    def export_session(self, actor: Principal, session_id: str) -> dict:
        self._require(actor, "operator", "reviewer")
        session = self._session(session_id)
        if session["consent_status"] != "recorded":
            raise GroupError("consent_required", "Export waits for recorded consent on the versioned group form", 409)
        package = self._package(session)
        self._audit(actor, "export", session_id, {"package_sha256": package["package_sha256"], "example_count": len(package["examples"])})
        return package

    def predict(self, actor: Principal, session_id: str) -> dict:
        self._require(actor, "operator", "reviewer", "psychologist")
        session = self._session(session_id)
        examples = self._examples(session)
        turns = self._prediction_turns(session_id)
        predictions = predict_examples(examples, [], turns)
        if predictions:
            self.store.add_predictions(predictions)
        interpretation = interpret_examples(examples)
        model_patterns = [
            {
                "participant_id": row["participant_id"],
                "item_letter": row["item_letter"],
                "score": row["predicted_label"],
                "evidence_start_s": row["evidence_start_s"],
                "evidence_end_s": row["evidence_end_s"],
                "playback_fragment": playback_fragment(row),
            }
            for row in predictions
            if not row["abstained"] and row["predicted_label"] in {"3", "4"} and playback_fragment(row)
        ]
        return {
            "psychologist": interpretation["psychologist_session_patterns"],
            "model": model_patterns,
            "predictions": [{**row, "playback_fragment": playback_fragment(row)} for row in predictions],
            "ratings_unchanged": True,
        }

    def claim_job(self, worker_id: str) -> dict | None:
        return self.store.claim_job(worker_id)

    def run_job(self, job: dict) -> None:
        session_id = job["group_session_id"]
        recording = self.store.recording_for_session(session_id)
        try:
            data = self.storage.get(recording["object_key"])
            derived = self.extractor(data, recording)
            if not isinstance(derived, dict):
                raise ValueError("extractor returned no processing record")
            self._store_derived_media(session_id, derived)
            self.store.replace_turns(session_id, list(derived.get("turns") or []))
            reasons = list(derived.get("failure_reasons") or [])
            fatal = "audio_samples_not_extracted" in reasons or any(reason.startswith("audio_extraction_failed") for reason in reasons)
            kept = {key: value for key, value in derived.items() if key not in {"turns", "audio_wav", "thumbnail_jpeg"}}
            self.store.update_recording(
                session_id,
                processing_state="failed" if fatal else "complete",
                failure_reason=";".join(reasons) or None,
                quality_state=derived.get("quality_state") or "unprocessed",
                processing=kept,
                tool_version=derived.get("tool_version"),
                audio_object_key=derived.get("audio_object_key"),
                thumbnail_object_key=derived.get("thumbnail_object_key"),
            )
            if derived.get("thumbnail_object_key") and not self._session(session_id).get("marked_frame_object_key"):
                self.store.update_session(session_id, marked_frame_object_key=derived["thumbnail_object_key"])
            self._mark_visible_seats(session_id)
        except Exception as exc:
            self.store.update_recording(session_id, processing_state="failed", failure_reason=f"{type(exc).__name__}")
            self.store.finish_job(job["id"], state="failed", error=type(exc).__name__)
            return
        failed = self.store.recording_for_session(session_id)["processing_state"] == "failed"
        self.store.finish_job(job["id"], state="failed" if failed else "complete", error=None if not failed else "audio_not_extracted")

    def _mark_visible_seats(self, session_id: str) -> None:
        recording = self.store.recording_for_session(session_id)
        if recording is None:
            return
        processing = dict(recording.get("processing") or {})
        frames = list(processing.get("frames") or [])
        seats = self.store.seats_for(session_id)
        if not frames or not seats:
            return
        checked = []
        for frame in frames:
            time_s = float(frame["time_s"])
            visible = [
                int(seat["slot_number"])
                for seat in seats
                if float(seat["valid_from_s"]) <= time_s <= float(seat["valid_to_s"])
            ]
            checked.append({**frame, "visible_slots": visible, "missing_slots": [
                int(seat["slot_number"]) for seat in seats if int(seat["slot_number"]) not in visible
            ]})
        processing["frames"] = checked
        self.store.update_recording(session_id, processing=processing)

    def store_signature(self, actor: Principal, session_id: str, form_line: int, filename: str, data: bytes) -> dict:
        self._require(actor, "operator")
        self._session(session_id)
        if form_line < 1 or form_line > 10:
            raise GroupError("invalid_signature", "Signature form line must be from 1 to 10", 400)
        if len(data) > _MAX_IMAGE_BYTES or not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG")):
            raise GroupError("invalid_signature", "A signature must be a JPEG or PNG under 5 MB", 400)
        key = f"group-recordings/{session_id}/consent/{form_line}/signature"
        content_type = "image/jpeg" if data.startswith(b"\xff\xd8") else "image/png"
        stored = self.storage.put_immutable(key, data, content_type)
        self.store.set_consent_signature(session_id, form_line, stored.key)
        self._audit(actor, "store_signature", session_id, {"form_line": form_line, "sha256": stored.sha256})
        return {"form_line": form_line, "sha256": stored.sha256, "stored_on_consent_record": True}

    def _store_derived_media(self, session_id: str, derived: dict) -> None:
        if derived.get("audio_wav"):
            stored = self.storage.put_immutable(f"group-recordings/{session_id}/audio.wav", derived["audio_wav"], "audio/wav")
            derived["audio_object_key"] = stored.key
        if derived.get("thumbnail_jpeg"):
            stored = self.storage.put_immutable(f"group-recordings/{session_id}/thumbnail.jpg", derived["thumbnail_jpeg"], "image/jpeg")
            derived["thumbnail_object_key"] = stored.key

    def _package(self, session: dict) -> dict:
        examples = self._examples(session)
        participants = [row for row in self.store.participants(session["id"]) if not row.get("withdrawn_at")]
        sheets = []
        attachments = []
        for participant in self.store.participants(session["id"]):
            if participant.get("withdrawn_at"):
                continue
            for sheet in self.store.marksheets_for_participant(participant["id"]):
                if sheet["state"] == "submitted":
                    sheets.append(sheet)
            for attachment in self.store.attachments_for(participant["id"]):
                attachments.append(
                    {
                        "participant_id": participant["id"],
                        "sha256": attachment["sha256"],
                        "filename": attachment["filename"],
                        "pdf_text_used_as_labels": False,
                    }
                )
        recording = self.store.recording_for_session(session["id"])
        package = {
            "package_version": PROTOCOL_VERSION,
            "consent_version": session["consent_version"],
            "marksheet_version": MARKSHEET_VERSION,
            "protocol_version": session["protocol_version"],
            "group_session_id": session["id"],
            "session_code": session["session_code"],
            "language": session["language"],
            "topic": session["topic"],
            "recording_sha256": None if recording is None else recording["sha256"],
            "recording_disposition": session["recording_disposition"],
            "participants": [
                {"id": row["id"], "anonymous_code": row["anonymous_code"], "research_code": row.get("research_code"), "slot_number": row["slot_number"]}
                for row in participants
            ],
            "marksheets": sheets,
            "attachments": attachments,
            "examples": examples,
            "reviews": [
            row
            for participant in participants
            for row in self.store.reviews_for(participant["id"])
        ],
            "pdf_text_used_as_labels": False,
        }
        encoded = _canonical(package)
        package["package_sha256"] = hashlib.sha256(encoded).hexdigest()
        return package

    def _examples(self, session: dict) -> list[dict]:
        recording = self.store.recording_for_session(session["id"])
        if recording is None:
            return []
        participants = self.store.participants(session["id"])
        sheets = []
        for participant in participants:
            if participant.get("withdrawn_at"):
                continue
            for sheet in self.store.marksheets_for_participant(participant["id"]):
                if sheet["state"] == "submitted":
                    sheets.append(sheet)
        return build_training_examples(
            group_session_id=session["id"],
            recording_sha256=recording["sha256"],
            quality_state=recording.get("quality_state") or "unprocessed",
            participants=participants,
            marksheets=sheets,
            turns=self._prediction_turns(session["id"]),
            language=session["language"],
            topic=session["topic"],
        )

    def _prediction_turns(self, session_id: str) -> list[dict]:
        recording = self.store.recording_for_session(session_id) or {}
        processing = recording.get("processing") or {}
        transcript = processing.get("transcript") or []
        associated = associate_turns(self.store.turns_for(session_id), self.store.mappings_for(session_id))
        for turn in associated:
            snippets = [
                segment["text"]
                for segment in transcript
                if segment.get("cluster_label") == turn["cluster_label"]
                and float(segment["start_s"]) < turn["end_s"]
                and float(segment["end_s"]) > turn["start_s"]
            ]
            turn["text"] = " ".join(snippets)
            turn["modality"] = "audio"
        for seat in self.store.seats_for(session_id):
            associated.append(
                {
                    "cluster_label": f"seat-{seat['slot_number']}",
                    "start_s": seat["valid_from_s"],
                    "end_s": seat["valid_to_s"],
                    "modality": "video",
                    "confirmed_participant_id": seat["participant_id"],
                    "overlap": False,
                }
            )
        return associated

    def _view(self, actor: Principal, session_id: str, participants: list[dict] | None = None) -> dict:
        session = self._session(session_id)
        people = participants if participants is not None else self.store.participants(session_id)
        recording = self.store.recording_for_session(session_id)
        visible_people = []
        for person in sorted(people, key=lambda item: item["slot_number"]):
            summaries = []
            for sheet in self.store.marksheets_for_participant(person["id"]):
                if actor.role == "psychologist" and sheet["rater_id"] != actor.id:
                    continue
                summaries.append(
                    {
                        "rater_id": sheet["rater_id"],
                        "rating_role": sheet["rating_role"],
                        "state": sheet["state"],
                        "revision": sheet["revision"],
                        "mine": sheet["rater_id"] == actor.id,
                    }
                )
            visible_people.append({**person, "marksheets": summaries, "attachments": [
                {"id": row["id"], "sha256": row["sha256"], "filename": row["filename"], "pdf_text_used_as_labels": False}
                for row in self.store.attachments_for(person["id"])
            ]})
        processing = {} if recording is None else recording.get("processing") or {}
        return {
            "session": {key: value for key, value in session.items() if key != "marked_frame_object_key"},
            "marked_frame_ready": bool(session.get("marked_frame_object_key")),
            "participants": visible_people,
            "recording": None if recording is None else _public_recording(recording),
            "seats": self.store.seats_for(session_id),
            "speaker_turns": self.store.turns_for(session_id),
            "speaker_mappings": _current_mappings(self.store.mappings_for(session_id)),
            "mapping_history_count": len(self.store.mappings_for(session_id)),
            "transcript": processing.get("transcript") or [],
            "processing_failure_reasons": processing.get("failure_reasons") or [],
        }

    def _rating_role(self, participant_id: str, rater_id: str) -> str:
        sheets = self.store.marksheets_for_participant(participant_id)
        primary = _latest_role(sheets, "primary")
        independent = _latest_role(sheets, "independent")
        if primary is None:
            return "primary"
        if primary["rater_id"] == rater_id:
            return "primary"
        if independent is None:
            return "independent"
        if independent["rater_id"] == rater_id:
            return "independent"
        raise GroupError("ratings_full", "Two psychologists have already started ratings for this participant", 409)

    def _participant(self, session_id: str, participant_id: str) -> dict:
        self._session(session_id)
        found = self.store.participant(session_id, participant_id)
        if found is None:
            raise GroupError("participant_not_found", "Participant slot not found in this group session", 404)
        return found

    def _participant_withdrawn(self, session_id: str, participant_id: str) -> bool:
        found = self.store.participant(session_id, participant_id)
        return bool(found and found.get("withdrawn_at"))

    def _session(self, session_id: str) -> dict:
        found = self.store.session(session_id)
        if found is None:
            raise GroupError("session_not_found", "Group session not found", 404)
        return found

    def _recording(self, session_id: str) -> dict:
        found = self.store.recording_for_session(session_id)
        if found is None:
            raise GroupError("recording_not_found", "Upload the group recording first", 404)
        return found

    def _require(self, actor: Principal, *roles: str) -> None:
        if actor.role not in roles:
            raise GroupError("forbidden", "This account cannot perform that action", 403)

    def _audit(self, actor: Principal, action: str, session_id: str, detail: dict) -> None:
        safe = dict(detail)
        safe.pop("legal_name", None)
        self.store.audit(
            {
                "actor_id": actor.id,
                "action": action,
                "resource_type": "group_session",
                "resource_id": session_id,
                "detail": safe,
                "created_at": _stamp(),
            }
        )

    @staticmethod
    def _text(payload: dict, field: str) -> str:
        value = str(payload.get(field) or "").strip()
        if not value or len(value) > 160:
            raise GroupError("invalid_session", f"{field} is required", 400)
        return value

    @staticmethod
    def _date(value: Any) -> None:
        try:
            datetime.strptime(str(value), "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise GroupError("invalid_session", "session_date must be YYYY-MM-DD", 400) from exc

    @staticmethod
    def _parse_time(value: Any, field: str) -> None:
        try:
            datetime.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise GroupError("invalid_session", f"{field} must be an ISO timestamp", 400) from exc


def _public_recording(recording: dict) -> dict:
    hidden = {"processing"}
    return {key: value for key, value in recording.items() if key not in hidden}


def _current_mappings(rows: list[dict]) -> dict[str, dict]:
    current: dict[str, dict] = {}
    for row in sorted(rows, key=lambda item: item["revision"]):
        current[row["cluster_label"]] = row
    return current


def _latest(rows: list[dict], *, rater_id: str) -> dict | None:
    owned = [row for row in rows if row["rater_id"] == rater_id and row["rating_role"] != "adjudicated"]
    if not owned:
        return None
    return max(owned, key=lambda row: row["revision"])


def _latest_role(rows: list[dict], role: str) -> dict | None:
    owned = [row for row in rows if row["rating_role"] == role]
    if not owned:
        return None
    return max(owned, key=lambda row: (row["revision"], row.get("submitted_at") or ""))


def _score_changes(previous: list[dict], current: list[dict]) -> list[dict]:
    before = {item["item_letter"]: item.get("score") for item in previous}
    return [
        {"item_letter": item["item_letter"], "previous_score": before.get(item["item_letter"]), "new_score": item.get("score")}
        for item in current
        if before.get(item["item_letter"]) != item.get("score")
    ]


def _canonical(package: dict) -> bytes:
    import json

    body = {key: value for key, value in package.items() if key != "package_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def PathName(filename: str) -> str:
    cleaned = (filename or "upload").replace("\\", "/").split("/")[-1]
    return cleaned[:180] or "upload"
