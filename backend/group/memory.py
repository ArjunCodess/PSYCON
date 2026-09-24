"""In-memory group store used by the workflow tests and local rehearsal."""

from __future__ import annotations

import copy
from typing import Any


class MemoryGroupStore:
    def __init__(self) -> None:
        self.accounts: dict[str, dict] = {}
        self.tokens: dict[str, str] = {}
        self.sessions: dict[str, dict] = {}
        self.participant_rows: dict[str, list[dict]] = {}
        self.consent_records: list[dict] = []
        self.recordings: dict[str, dict] = {}
        self.seats: dict[str, list[dict]] = {}
        self.turns: dict[str, list[dict]] = {}
        self.mappings: list[dict] = []
        self.marksheets: list[dict] = []
        self.reviews: list[dict] = []
        self.attachments: list[dict] = []
        self.predictions: list[dict] = []
        self.jobs: list[dict] = []
        self.grants: dict[str, dict] = {}
        self.audit_events: list[dict] = []
        self.face_samples: dict[str, list[dict]] = {}
        self.training_labels: list[dict] = []
        self.voice_segments: dict[str, list[dict]] = {}
        self.voice_profiles: dict[str, list[dict]] = {}

    def account_by_token(self, token_hash: str) -> dict | None:
        account_id = self.tokens.get(token_hash)
        return self.account_by_id(account_id) if account_id else None

    def account_by_id(self, account_id: str | None) -> dict | None:
        row = self.accounts.get(account_id or "")
        return None if row is None or row.get("revoked_at") else copy.deepcopy(row)

    def insert_account(self, row: dict) -> dict:
        if any(account["account_code"] == row["account_code"] for account in self.accounts.values()):
            raise ValueError("account code already exists")
        self.accounts[row["id"]] = copy.deepcopy(row)
        self.tokens[row["token_hash"]] = row["id"]
        return self.account_by_id(row["id"])

    def insert_session(self, row: dict) -> dict:
        if self.session_by_code(row["session_code"]):
            raise ValueError("session code already exists")
        self.sessions[row["id"]] = copy.deepcopy(row)
        self.participant_rows[row["id"]] = []
        return self.session(row["id"])

    def session_by_code(self, code: str) -> dict | None:
        for row in self.sessions.values():
            if row["session_code"] == code:
                return copy.deepcopy(row)
        return None

    def session(self, session_id: str) -> dict | None:
        row = self.sessions.get(session_id)
        return None if row is None else copy.deepcopy(row)

    def list_sessions(self) -> list[dict]:
        rows = [copy.deepcopy(row) for row in self.sessions.values()]
        rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return rows

    def update_session(self, session_id: str, **fields: Any) -> dict:
        self.sessions[session_id].update(fields)
        return self.session(session_id)

    def insert_participant(self, row: dict) -> dict:
        self.participant_rows.setdefault(row["group_session_id"], []).append(copy.deepcopy(row))
        return copy.deepcopy(row)

    def participants(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.participant_rows.get(session_id, []))

    def participant(self, session_id: str, participant_id: str) -> dict | None:
        for row in self.participant_rows.get(session_id, []):
            if row["id"] == participant_id:
                return copy.deepcopy(row)
        return None

    def update_participant(self, participant_id: str, **fields: Any) -> dict:
        for rows in self.participant_rows.values():
            for row in rows:
                if row["id"] == participant_id:
                    row.update(fields)
                    return copy.deepcopy(row)
        raise KeyError(participant_id)

    def insert_consent(self, row: dict) -> None:
        self.consent_records.append(copy.deepcopy(row))

    def set_consent_signature(self, session_id: str, form_line: int, object_key: str) -> None:
        for row in self.consent_records:
            if row["group_session_id"] == session_id and int(row["form_line"]) == int(form_line):
                row["signature_object_key"] = object_key
                return
        self.consent_records.append(
            {
                "id": object_key,
                "group_session_id": session_id,
                "form_line": int(form_line),
                "legal_name": "",
                "signature_object_key": object_key,
            }
        )

    def insert_recording(self, row: dict) -> dict:
        if row["group_session_id"] in self.recordings:
            raise ValueError("this group session already has a recording")
        self.recordings[row["group_session_id"]] = copy.deepcopy(row)
        return copy.deepcopy(row)

    def recording_for_session(self, session_id: str) -> dict | None:
        row = self.recordings.get(session_id)
        return None if row is None else copy.deepcopy(row)

    def update_recording(self, session_id: str, **fields: Any) -> dict:
        self.recordings[session_id].update(fields)
        return self.recording_for_session(session_id)

    def replace_seats(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.seats[session_id] = copy.deepcopy(rows)
        return self.seats_for(session_id)

    def seats_for(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.seats.get(session_id, []))

    def replace_turns(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.turns[session_id] = copy.deepcopy(rows)
        return self.turns_for(session_id)

    def turns_for(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.turns.get(session_id, []))

    def add_mappings(self, rows: list[dict]) -> list[dict]:
        self.mappings.extend(copy.deepcopy(rows))
        return copy.deepcopy(rows)

    def mappings_for(self, session_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.mappings if row["group_session_id"] == session_id]

    def save_marksheet(self, row: dict) -> dict:
        for index, existing in enumerate(self.marksheets):
            if existing["id"] == row["id"]:
                self.marksheets[index] = copy.deepcopy(row)
                return copy.deepcopy(row)
        self.marksheets.append(copy.deepcopy(row))
        return copy.deepcopy(row)

    def marksheets_for_participant(self, participant_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.marksheets if row["participant_id"] == participant_id]

    def add_review(self, row: dict) -> dict:
        self.reviews.append(copy.deepcopy(row))
        return copy.deepcopy(row)

    def reviews_for(self, participant_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.reviews if row["participant_id"] == participant_id]

    def add_attachment(self, row: dict) -> dict:
        self.attachments.append(copy.deepcopy(row))
        return copy.deepcopy(row)

    def attachments_for(self, participant_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.attachments if row["participant_id"] == participant_id]

    def add_predictions(self, rows: list[dict]) -> list[dict]:
        self.predictions.extend(copy.deepcopy(rows))
        return copy.deepcopy(rows)

    def predictions_for(self, session_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.predictions if row["group_session_id"] == session_id]

    def enqueue_job(self, row: dict) -> dict:
        self.jobs.append(copy.deepcopy(row))
        return copy.deepcopy(row)

    def claim_job(self, worker_id: str) -> dict | None:
        for row in self.jobs:
            if row["state"] == "queued":
                row["state"] = "running"
                row["locked_by"] = worker_id
                return copy.deepcopy(row)
        return None

    def finish_job(self, job_id: str, *, state: str, error: str | None) -> None:
        for row in self.jobs:
            if row["id"] == job_id:
                row["state"] = state
                row["error"] = error

    def add_grant(self, token_hash: str, row: dict) -> None:
        self.grants[token_hash] = copy.deepcopy(row)

    def grant(self, token_hash: str) -> dict | None:
        row = self.grants.get(token_hash)
        return None if row is None else copy.deepcopy(row)

    def audit(self, row: dict) -> None:
        self.audit_events.append(copy.deepcopy(row))

    def audits_for(self, resource_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.audit_events if row.get("resource_id") == resource_id]

    def delete_session(self, session_id: str) -> list[str]:
        keys = []
        recording = self.recordings.pop(session_id, None)
        if recording:
            for field in ("object_key", "audio_object_key", "thumbnail_object_key"):
                if recording.get(field):
                    keys.append(recording[field])
        session = self.sessions.pop(session_id, None)
        if session and session.get("marked_frame_object_key"):
            keys.append(session["marked_frame_object_key"])
        for row in self.consent_records:
            if row["group_session_id"] == session_id and row.get("signature_object_key"):
                keys.append(row["signature_object_key"])
        self.consent_records = [row for row in self.consent_records if row["group_session_id"] != session_id]
        participant_ids = {row["id"] for row in self.participant_rows.pop(session_id, [])}
        for row in self.attachments:
            if row["participant_id"] in participant_ids:
                keys.append(row["object_key"])
        self.attachments = [row for row in self.attachments if row["participant_id"] not in participant_ids]
        self.marksheets = [row for row in self.marksheets if row["participant_id"] not in participant_ids]
        self.reviews = [row for row in self.reviews if row["participant_id"] not in participant_ids]
        self.predictions = [row for row in self.predictions if row["group_session_id"] != session_id]
        self.mappings = [row for row in self.mappings if row["group_session_id"] != session_id]
        self.seats.pop(session_id, None)
        self.turns.pop(session_id, None)
        self.jobs = [row for row in self.jobs if row["group_session_id"] != session_id]
        self.face_samples.pop(session_id, None)
        self.voice_segments.pop(session_id, None)
        self.voice_profiles.pop(session_id, None)
        self.training_labels = [row for row in self.training_labels if row["group_session_id"] != session_id]
        return keys

    def replace_face_samples(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.face_samples[session_id] = copy.deepcopy(rows)
        return self.face_samples_for(session_id)

    def face_samples_for(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.face_samples.get(session_id, []))

    def all_face_samples(self) -> list[dict]:
        return [copy.deepcopy(row) for rows in self.face_samples.values() for row in rows]

    def replace_voice_segments(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.voice_segments[session_id] = copy.deepcopy(rows)
        return self.voice_segments_for(session_id)

    def voice_segments_for(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.voice_segments.get(session_id, []))

    def replace_voice_profiles(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.voice_profiles[session_id] = copy.deepcopy(rows)
        return self.voice_profiles_for(session_id)

    def voice_profiles_for(self, session_id: str) -> list[dict]:
        return copy.deepcopy(self.voice_profiles.get(session_id, []))

    def all_voice_profiles(self) -> list[dict]:
        return [copy.deepcopy(row) for rows in self.voice_profiles.values() for row in rows]

    def replace_voice_analysis(self, session_id: str, segments: list[dict], profiles: list[dict]) -> None:
        saved_segments, saved_profiles = copy.deepcopy(segments), copy.deepcopy(profiles)
        self.voice_segments[session_id] = saved_segments
        self.voice_profiles[session_id] = saved_profiles

    def replace_training_labels(self, session_id: str, rows: list[dict]) -> list[dict]:
        self.training_labels = [row for row in self.training_labels if row["group_session_id"] != session_id]
        self.training_labels.extend(copy.deepcopy(rows))
        return self.training_labels_for(session_id)

    def training_labels_for(self, session_id: str) -> list[dict]:
        return [copy.deepcopy(row) for row in self.training_labels if row["group_session_id"] == session_id]

    def all_training_labels(self) -> list[dict]:
        return copy.deepcopy(self.training_labels)
