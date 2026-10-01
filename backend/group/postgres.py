"""PostgreSQL persistence for group observation records."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb


_SESSION_FIELDS = {
    "marked_frame_object_key",
    "camera_orientation",
    "state",
    "recording_disposition",
    "session_code",
    "session_date",
    "recording_start_time",
}
_PARTICIPANT_FIELDS = {"research_code", "withdrawn_at"}
_RECORDING_FIELDS = {"processing_state", "failure_reason", "quality_state", "processing", "tool_version", "audio_object_key", "thumbnail_object_key"}


def _public(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = {}
    for key, value in row.items():
        if isinstance(value, (UUID, datetime, date)):
            result[key] = value.isoformat() if isinstance(value, (datetime, date)) else str(value)
        else:
            result[key] = value
    return result


class PostgresGroupStore:
    def __init__(self, database) -> None:
        self.database = database

    def account_by_token(self, token_hash: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM group_accounts WHERE token_hash=%s AND revoked_at IS NULL",
                (token_hash,),
            ).fetchone()
        return _public(row)

    def account_by_id(self, account_id: str | None) -> dict | None:
        if not account_id:
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM group_accounts WHERE id=%s AND revoked_at IS NULL",
                (account_id,),
            ).fetchone()
        return _public(row)

    def insert_account(self, row: dict) -> dict:
        try:
            with self.database.connection() as connection:
                stored = connection.execute(
                    """
                    INSERT INTO group_accounts(id, label, account_code, role, token_hash)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (row["id"], row["label"], row["account_code"], row["role"], row["token_hash"]),
                ).fetchone()
        except UniqueViolation as exc:
            raise ValueError("account code already exists") from exc
        return _public(stored)

    def insert_session(self, row: dict) -> dict:
        try:
            with self.database.connection() as connection:
                stored = connection.execute(
                    """
                    INSERT INTO group_sessions(
                        id, session_code, session_date, class_name, section, topic, language,
                        moderator_code, camera_position, camera_orientation, recording_start_time,
                        consent_status, consent_version, protocol_version, participant_count, state,
                        created_by, marked_frame_object_key, recording_disposition
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        row["id"], row["session_code"], row["session_date"], row["class_name"], row["section"],
                        row["topic"], row["language"], row["moderator_code"], row["camera_position"],
                        row["camera_orientation"], row["recording_start_time"], row["consent_status"],
                        row["consent_version"], row["protocol_version"], row["participant_count"], row["state"],
                        row["created_by"], row["marked_frame_object_key"], row["recording_disposition"],
                    ),
                ).fetchone()
        except UniqueViolation as exc:
            raise ValueError("session code already exists") from exc
        return _public(stored)

    def session_by_code(self, code: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM group_sessions WHERE session_code=%s", (code,)).fetchone()
        return _public(row)

    def session(self, session_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM group_sessions WHERE id=%s", (session_id,)).fetchone()
        return _public(row)

    def list_sessions(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM group_sessions ORDER BY created_at DESC").fetchall()
        return [_public(row) for row in rows]

    def update_session(self, session_id: str, **fields: Any) -> dict:
        return self._update("group_sessions", session_id, fields, _SESSION_FIELDS)

    def insert_participant(self, row: dict) -> dict:
        with self.database.connection() as connection:
            stored = connection.execute(
                """
                INSERT INTO group_participants(id, group_session_id, slot_number, anonymous_code, label, research_code, withdrawn_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    row["id"], row["group_session_id"], row["slot_number"], row["anonymous_code"],
                    row["label"], row["research_code"], row["withdrawn_at"],
                ),
            ).fetchone()
        return _public(stored)

    def participants(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM group_participants WHERE group_session_id=%s ORDER BY slot_number",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def participant(self, session_id: str, participant_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM group_participants WHERE group_session_id=%s AND id=%s",
                (session_id, participant_id),
            ).fetchone()
        return _public(row)

    def update_participant(self, participant_id: str, **fields: Any) -> dict:
        unknown = set(fields) - _PARTICIPANT_FIELDS
        if unknown:
            raise ValueError(f"unsupported participant fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key}=%s" for key in fields)
        with self.database.connection() as connection:
            row = connection.execute(
                f"UPDATE group_participants SET {assignments} WHERE id=%s RETURNING *",
                (*fields.values(), participant_id),
            ).fetchone()
        return _public(row)

    def insert_consent(self, row: dict) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO consent_records(id, group_session_id, form_line, legal_name, signature_object_key)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (row["id"], row["group_session_id"], row["form_line"], row["legal_name"], row["signature_object_key"]),
            )

    def set_consent_signature(self, session_id: str, form_line: int, object_key: str) -> None:
        with self.database.connection() as connection:
            updated = connection.execute(
                """
                UPDATE consent_records SET signature_object_key=%s
                WHERE group_session_id=%s AND form_line=%s
                RETURNING id
                """,
                (object_key, session_id, form_line),
            ).fetchone()
            if updated is None:
                connection.execute(
                    """
                    INSERT INTO consent_records(id, group_session_id, form_line, legal_name, signature_object_key)
                    VALUES (%s,%s,%s,'',%s)
                    """,
                    (str(uuid4()), session_id, form_line, object_key),
                )

    def insert_recording(self, row: dict) -> dict:
        try:
            with self.database.connection() as connection:
                stored = connection.execute(
                    """
                    INSERT INTO recordings(
                        id, group_session_id, object_key, sha256, filename, content_type, size_bytes,
                        duration_s, video_codec, audio_codec, width, height, timestamps_readable,
                        processing_state, failure_reason, quality_state, processing, tool_version
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        row["id"], row["group_session_id"], row["object_key"], row["sha256"], row["filename"],
                        row["content_type"], row["size_bytes"], row["duration_s"], row["video_codec"],
                        row["audio_codec"], row["width"], row["height"], row["timestamps_readable"],
                        row["processing_state"], row["failure_reason"], row["quality_state"],
                        Jsonb(row["processing"]), row["tool_version"],
                    ),
                ).fetchone()
        except UniqueViolation as exc:
            raise ValueError("this group session already has a recording") from exc
        return _public(stored)

    def recording_for_session(self, session_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM recordings WHERE group_session_id=%s", (session_id,)).fetchone()
        return _public(row)

    def update_recording(self, session_id: str, **fields: Any) -> dict:
        unknown = set(fields) - _RECORDING_FIELDS
        if unknown:
            raise ValueError(f"unsupported recording fields: {sorted(unknown)}")
        values = []
        assignments = []
        for key, value in fields.items():
            assignments.append(f"{key}=%s")
            values.append(Jsonb(value) if key == "processing" else value)
        with self.database.connection() as connection:
            row = connection.execute(
                f"UPDATE recordings SET {', '.join(assignments)} WHERE group_session_id=%s RETURNING *",
                (*values, session_id),
            ).fetchone()
        return _public(row)

    def replace_seats(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            connection.execute("DELETE FROM seat_assignments WHERE group_session_id=%s", (session_id,))
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO seat_assignments(
                        id, group_session_id, participant_id, slot_number, label, x, y, width, height,
                        center_x, valid_from_s, valid_to_s, camera_orientation, marked_frame_object_key,
                        frame_time_s, confirmed_by, confirmed_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"], session_id, row["participant_id"], row["slot_number"], row["label"],
                        row["x"], row["y"], row["width"], row["height"], row["center_x"], row["valid_from_s"],
                        row["valid_to_s"], row["camera_orientation"], row["marked_frame_object_key"],
                        row["frame_time_s"], row["confirmed_by"], row["confirmed_at"],
                    ),
                )
        return self.seats_for(session_id)

    def seats_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM seat_assignments WHERE group_session_id=%s ORDER BY slot_number",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def replace_turns(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            recording = connection.execute("SELECT id FROM recordings WHERE group_session_id=%s", (session_id,)).fetchone()
            connection.execute("DELETE FROM speaker_turns WHERE group_session_id=%s", (session_id,))
            if recording is not None:
                for row in rows:
                    connection.execute(
                        """
                        INSERT INTO speaker_turns(
                            id, group_session_id, recording_id, cluster_label, start_s, end_s, overlap,
                            engine, tool_version, proposed_participant_id
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            str(uuid4()), session_id, recording["id"], row["cluster_label"], row["start_s"],
                            row["end_s"], bool(row.get("overlap")), row.get("engine") or "unassigned",
                            row.get("tool_version") or "group-processing-1.0.0", row.get("proposed_participant_id"),
                        ),
                    )
        return self.turns_for(session_id)

    def turns_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM speaker_turns WHERE group_session_id=%s ORDER BY start_s, cluster_label",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def add_mappings(self, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO speaker_mappings(
                        id, group_session_id, cluster_label, participant_id, status, note, mapped_by, mapped_at, revision
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"], row["group_session_id"], row["cluster_label"], row["participant_id"],
                        row["status"], row["note"], row["mapped_by"], row["mapped_at"], row["revision"],
                    ),
                )
        return rows

    def mappings_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM speaker_mappings WHERE group_session_id=%s ORDER BY revision",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def save_marksheet(self, row: dict) -> dict:
        with self.database.connection() as connection:
            existing = connection.execute("SELECT id FROM marksheets WHERE id=%s", (row["id"],)).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO marksheets(
                        id, group_session_id, participant_id, rater_id, rating_role, revision,
                        marksheet_version, state, submitted_at, supersedes_id, corrected_by, correction_reason, updated_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"], row["group_session_id"], row["participant_id"], row["rater_id"], row["rating_role"],
                        row["revision"], row["marksheet_version"], row["state"], row.get("submitted_at"),
                        row.get("supersedes_id"), row.get("corrected_by"), row.get("correction_reason"), row.get("updated_at"),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE marksheets
                    SET state=%s, submitted_at=%s, updated_at=%s
                    WHERE id=%s
                    """,
                    (row["state"], row.get("submitted_at"), row.get("updated_at"), row["id"]),
                )
            connection.execute(
                """
                DELETE FROM evidence_intervals
                WHERE item_rating_id IN (SELECT id FROM item_ratings WHERE marksheet_id=%s)
                """,
                (row["id"],),
            )
            connection.execute("DELETE FROM item_ratings WHERE marksheet_id=%s", (row["id"],))
            for item in row.get("items") or []:
                item_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO item_ratings(
                        id, marksheet_id, item_letter, score, preceding_event, observed_response,
                        fair_opportunity, no_score_reason
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        item_id, row["id"], item["item_letter"], item.get("score"),
                        item.get("preceding_event") or "", item.get("observed_response") or "",
                        item.get("fair_opportunity"), item.get("no_score_reason"),
                    ),
                )
                for interval in item.get("intervals") or []:
                    connection.execute(
                        """
                        INSERT INTO evidence_intervals(id, item_rating_id, interval_kind, start_s, end_s, description)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            str(uuid4()), item_id, interval["kind"], interval["start_s"], interval["end_s"],
                            interval.get("description") or "",
                        ),
                    )
        sheets = self.marksheets_for_participant(row["participant_id"])
        return next(sheet for sheet in sheets if sheet["id"] == row["id"])

    def marksheets_for_participant(self, participant_id: str) -> list[dict]:
        with self.database.connection() as connection:
            sheets = connection.execute(
                "SELECT * FROM marksheets WHERE participant_id=%s ORDER BY revision",
                (participant_id,),
            ).fetchall()
            result = []
            for sheet in sheets:
                items = connection.execute(
                    "SELECT * FROM item_ratings WHERE marksheet_id=%s ORDER BY item_letter",
                    (sheet["id"],),
                ).fetchall()
                nested = []
                for item in items:
                    intervals = connection.execute(
                        "SELECT * FROM evidence_intervals WHERE item_rating_id=%s ORDER BY start_s",
                        (item["id"],),
                    ).fetchall()
                    public_item = _public(item)
                    public_item["intervals"] = [
                        {
                            "kind": interval["interval_kind"],
                            "start_s": interval["start_s"],
                            "end_s": interval["end_s"],
                            "description": interval["description"],
                        }
                        for interval in intervals
                    ]
                    nested.append(public_item)
                public_sheet = _public(sheet)
                public_sheet["items"] = nested
                result.append(public_sheet)
        return result

    def add_review(self, row: dict) -> dict:
        with self.database.connection() as connection:
            stored = connection.execute(
                """
                INSERT INTO reviews(
                    id, group_session_id, participant_id, primary_marksheet_id, independent_marksheet_id,
                    adjudicated_marksheet_id, reviewer_id, reason, changes
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    row["id"], row["group_session_id"], row["participant_id"], row["primary_marksheet_id"],
                    row["independent_marksheet_id"], row["adjudicated_marksheet_id"], row["reviewer_id"],
                    row["reason"], Jsonb(row["changes"]),
                ),
            ).fetchone()
        return _public(stored)

    def reviews_for(self, participant_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM reviews WHERE participant_id=%s", (participant_id,)).fetchall()
        return [_public(row) for row in rows]

    def add_attachment(self, row: dict) -> dict:
        with self.database.connection() as connection:
            stored = connection.execute(
                """
                INSERT INTO marksheet_attachments(
                    id, group_session_id, participant_id, object_key, sha256, filename, byte_size,
                    uploaded_by, pdf_text_used_as_labels
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    row["id"], row["group_session_id"], row["participant_id"], row["object_key"], row["sha256"],
                    row["filename"], row["byte_size"], row["uploaded_by"], False,
                ),
            ).fetchone()
        return _public(stored)

    def attachments_for(self, participant_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM marksheet_attachments WHERE participant_id=%s",
                (participant_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def add_predictions(self, rows: list[dict]) -> list[dict]:
        stored_rows = []
        with self.database.connection() as connection:
            for row in rows:
                stored = connection.execute(
                    """
                    INSERT INTO model_predictions(
                        id, group_session_id, participant_id, rater_id, item_letter, predicted_label,
                        abstained, confidence, account, evidence_start_s, evidence_end_s, evidence_source,
                        model_version, model_family, reason, source_recording_sha256, psychologist_score
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        str(uuid4()), row["group_session_id"], row["participant_id"], row.get("rater_id"),
                        row["item_letter"], row["predicted_label"], row["abstained"], row.get("confidence"),
                        row["account"], row.get("evidence_start_s"), row.get("evidence_end_s"),
                        row.get("evidence_source"), row["model_version"], row.get("model_family"), row.get("reason"),
                        row["source_recording_sha256"], row.get("psychologist_score"),
                    ),
                ).fetchone()
                stored_rows.append(_public(stored))
        return stored_rows

    def predictions_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM model_predictions WHERE group_session_id=%s",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def enqueue_job(self, row: dict) -> dict:
        with self.database.connection() as connection:
            stored = connection.execute(
                """
                INSERT INTO group_jobs(id, group_session_id, job_type, state)
                VALUES (%s,%s,%s,%s)
                RETURNING *
                """,
                (row["id"], row["group_session_id"], row["job_type"], row["state"]),
            ).fetchone()
        return _public(stored)

    def claim_job(self, worker_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                UPDATE group_jobs SET state='running', locked_by=%s
                WHERE id = (
                    SELECT id FROM group_jobs WHERE state='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                RETURNING *
                """,
                (worker_id,),
            ).fetchone()
        return _public(row)

    def finish_job(self, job_id: str, *, state: str, error: str | None) -> None:
        with self.database.connection() as connection:
            connection.execute("UPDATE group_jobs SET state=%s, error=%s WHERE id=%s", (state, error, job_id))

    def add_grant(self, token_hash: str, row: dict) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO playback_grants(token_hash, group_session_id, account_id, expires_at, object_key)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (token_hash, row["group_session_id"], row["account_id"], row["expires_at"], row["object_key"]),
            )

    def grant(self, token_hash: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM playback_grants WHERE token_hash=%s", (token_hash,)).fetchone()
        return _public(row)

    def audit(self, row: dict) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events(actor_id, action, resource_type, resource_id, detail)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (row["actor_id"], row["action"], row["resource_type"], row["resource_id"], Jsonb(row["detail"])),
            )

    def audits_for(self, resource_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE resource_id=%s ORDER BY id",
                (resource_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def delete_session(self, session_id: str) -> list[str]:
        keys = []
        with self.database.connection() as connection:
            recording = connection.execute("SELECT * FROM recordings WHERE group_session_id=%s", (session_id,)).fetchone()
            session = connection.execute("SELECT * FROM group_sessions WHERE id=%s", (session_id,)).fetchone()
            attachments = connection.execute(
                "SELECT object_key FROM marksheet_attachments WHERE group_session_id=%s",
                (session_id,),
            ).fetchall()
            signatures = connection.execute(
                "SELECT signature_object_key FROM consent_records WHERE group_session_id=%s",
                (session_id,),
            ).fetchall()
            if recording:
                keys.extend(value for value in (recording["object_key"],) if value)
            if session and session.get("marked_frame_object_key"):
                keys.append(session["marked_frame_object_key"])
            keys.extend(row["object_key"] for row in attachments)
            keys.extend(row["signature_object_key"] for row in signatures if row["signature_object_key"])
            connection.execute("DELETE FROM group_sessions WHERE id=%s", (session_id,))
        return keys

    def replace_face_samples(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            connection.execute("DELETE FROM face_samples WHERE group_session_id=%s", (session_id,))
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO face_samples(
                        id, group_session_id, participant_id, slot_number, x, y, width, height, feature
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"], row["group_session_id"], row["participant_id"], row["slot_number"],
                        row["x"], row["y"], row["width"], row["height"], Jsonb(row["feature"]),
                    ),
                )
        return self.face_samples_for(session_id)

    def face_samples_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM face_samples WHERE group_session_id=%s ORDER BY slot_number",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def all_face_samples(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM face_samples ORDER BY group_session_id, slot_number").fetchall()
        return [_public(row) for row in rows]

    def replace_voice_segments(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            self._write_voice_segments(connection, session_id, rows)
        return self.voice_segments_for(session_id)

    @staticmethod
    def _write_voice_segments(connection, session_id: str, rows: list[dict], method: str = "existing") -> None:
        connection.execute("DELETE FROM voice_segments WHERE group_session_id=%s AND method=%s", (session_id, method))
        for row in rows:
            connection.execute(
                "INSERT INTO voice_segments(id,group_session_id,method,start_s,end_s,cluster_label,overlap_refused_s,source_turn_index,slot_number,confidence,status,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (row["id"], session_id, method, row["start_s"], row["end_s"], row.get("cluster_label"),
                 row.get("overlap_refused_s", 0.0), row.get("source_turn_index"),
                 row["slot_number"], row["confidence"], row["status"], Jsonb(row.get("evidence") or {})),
            )

    def voice_segments_for(self, session_id: str, method: str = "existing") -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM voice_segments WHERE group_session_id=%s AND method=%s ORDER BY start_s", (session_id, method)).fetchall()
        return [_public(row) for row in rows]

    def replace_voice_profiles(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            self._write_voice_profiles(connection, session_id, rows)
        return self.voice_profiles_for(session_id)

    @staticmethod
    def _write_voice_profiles(connection, session_id: str, rows: list[dict], method: str = "existing") -> None:
        connection.execute("DELETE FROM voice_profiles WHERE group_session_id=%s AND method=%s", (session_id, method))
        for row in rows:
            connection.execute(
                "INSERT INTO voice_profiles(id,group_session_id,method,slot_number,engine,usable_seconds,vector,embedding_engine,embedding,metrics,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (row["id"], session_id, method, row["slot_number"], row["engine"], row["usable_seconds"],
                 Jsonb(row["vector"]), row.get("embedding_engine"), Jsonb(row.get("embedding")),
                 Jsonb(row["metrics"]), row["status"]),
            )

    def replace_voice_analysis(self, session_id: str, segments: list[dict], profiles: list[dict], method: str = "existing") -> None:
        with self.database.connection() as connection:
            with connection.transaction():
                self._write_voice_segments(connection, session_id, segments, method)
                self._write_voice_profiles(connection, session_id, profiles, method)

    def voice_profiles_for(self, session_id: str, method: str = "existing") -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM voice_profiles WHERE group_session_id=%s AND method=%s ORDER BY slot_number", (session_id, method)).fetchall()
        return [_public(row) for row in rows]

    def all_voice_profiles(self, method: str = "existing") -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM voice_profiles WHERE method=%s ORDER BY group_session_id, slot_number", (method,)).fetchall()
        return [_public(row) for row in rows]

    def replace_training_labels(self, session_id: str, rows: list[dict]) -> list[dict]:
        with self.database.connection() as connection:
            connection.execute("DELETE FROM training_labels WHERE group_session_id=%s", (session_id,))
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO training_labels(
                        id, group_session_id, participant_id, slot_number, item_letter, score, class_name
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"], row["group_session_id"], row["participant_id"], row["slot_number"],
                        row["item_letter"], row["score"], row["class_name"],
                    ),
                )
        return self.training_labels_for(session_id)

    def training_labels_for(self, session_id: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM training_labels WHERE group_session_id=%s ORDER BY slot_number, item_letter",
                (session_id,),
            ).fetchall()
        return [_public(row) for row in rows]

    def all_training_labels(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM training_labels ORDER BY group_session_id, slot_number, item_letter"
            ).fetchall()
        return [_public(row) for row in rows]

    def _update(self, table: str, row_id: str, fields: dict, allowed: set[str]) -> dict:
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported fields: {sorted(unknown)}")
        assignments = ", ".join(f"{key}=%s" for key in fields)
        with self.database.connection() as connection:
            row = connection.execute(
                f"UPDATE {table} SET {assignments} WHERE id=%s RETURNING *",
                (*fields.values(), row_id),
            ).fetchone()
        return _public(row)
