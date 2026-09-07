from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from protocol.chunk import ChunkV2

from .auth import create_token, hash_token
from .sync import ClockEstimate, estimate_clock


REQUIRED_VERSIONS = {
    "firmware",
    "hardware",
    "pcb",
    "protocol",
    "dataset",
    "model",
    "configuration",
    "calibration",
    "documentation",
}


def _json(value: Any) -> Jsonb:
    return Jsonb(value)


def _public(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = {}
    for key, value in row.items():
        if isinstance(value, (UUID, datetime)):
            result[key] = str(value)
        else:
            result[key] = value
    return result


class Repository:
    def __init__(self, database, *, max_sync_uncertainty_us: int = 250_000) -> None:
        self.database = database
        self.max_sync_uncertainty_us = max_sync_uncertainty_us

    def create_session(self, anonymous_code: str, versions: dict, metadata: dict) -> dict:
        anonymous_code = anonymous_code.strip()
        if not anonymous_code or len(anonymous_code) > 80:
            raise ValueError("anonymous participant code is required and must be at most 80 characters")
        missing = sorted(REQUIRED_VERSIONS - set(versions))
        if missing or any(not str(versions[key]).strip() for key in REQUIRED_VERSIONS):
            raise ValueError(f"session versions are incomplete: {', '.join(missing) or 'blank value'}")
        participant_id = uuid4()
        session_id = uuid4()
        with self.database.connection() as connection:
            participant = connection.execute(
                """
                INSERT INTO participants(id, anonymous_code) VALUES (%s, %s)
                ON CONFLICT(anonymous_code) DO UPDATE SET anonymous_code = EXCLUDED.anonymous_code
                RETURNING id
                """,
                (participant_id, anonymous_code),
            ).fetchone()
            row = connection.execute(
                """
                INSERT INTO sessions(id, participant_id, state, versions, metadata)
                VALUES (%s, %s, 'open', %s, %s)
                RETURNING *
                """,
                (session_id, participant["id"], _json(versions), _json(metadata)),
            ).fetchone()
        return _public(row)

    def issue_device(self, label: str, device_id: int, session_id: str) -> tuple[dict, str]:
        if not label.strip() or not 0 <= device_id <= 0xFFFFFFFF:
            raise ValueError("device label and unsigned 32-bit device_id are required")
        token = create_token()
        with self.database.connection() as connection:
            if connection.execute("SELECT 1 FROM sessions WHERE id=%s AND state='open'", (session_id,)).fetchone() is None:
                raise LookupError("open session not found")
            if connection.execute("SELECT 1 FROM session_devices WHERE session_id=%s AND device_id=%s", (session_id, device_id)).fetchone():
                raise ValueError("device_id is already assigned to this session")
            row = connection.execute(
                """
                INSERT INTO credentials(id, label, role, device_id, token_hash)
                VALUES (%s, %s, 'device', %s, %s)
                RETURNING id, label, role, device_id, created_at
                """,
                (uuid4(), label.strip(), device_id, hash_token(token)),
            ).fetchone()
            connection.execute(
                "INSERT INTO session_devices(session_id, credential_id, device_id) VALUES (%s,%s,%s)",
                (session_id, row["id"], device_id),
            )
        return _public(row), token

    def session_allows_device(self, session_id: str, credential_id: str, device_id: int) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM session_devices WHERE session_id=%s AND credential_id=%s AND device_id=%s",
                (session_id, credential_id, device_id),
            ).fetchone()
        return row is not None

    def record_audit(self, actor_id: str | None, action: str, resource_type: str, resource_id: str | None, detail: dict | None = None) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO audit_events(actor_id, action, resource_type, resource_id, detail) VALUES (%s,%s,%s,%s,%s)",
                (actor_id, action, resource_type, resource_id, _json(detail or {})),
            )

    def session(self, session_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT s.*, p.anonymous_code
                FROM sessions s JOIN participants p ON p.id = s.participant_id
                WHERE s.id = %s
                """,
                (session_id,),
            ).fetchone()
        return _public(row)

    def list_sessions(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.state, s.started_at, s.ended_at, p.anonymous_code,
                       count(DISTINCT c.id) AS chunk_count,
                       count(DISTINCT se.id) AS status_count
                FROM sessions s JOIN participants p ON p.id = s.participant_id
                LEFT JOIN chunks c ON c.session_id = s.id
                LEFT JOIN status_events se ON se.session_id = s.id
                GROUP BY s.id, p.anonymous_code ORDER BY s.started_at DESC LIMIT 100
                """
            ).fetchall()
        return [_public(row) for row in rows]

    def existing_chunk(self, device_id: int, stream_type: str, sequence: int) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM chunks WHERE device_id=%s AND stream_type=%s AND sequence=%s",
                (device_id, stream_type, sequence),
            ).fetchone()
        return _public(row)

    def clock_estimate(self, session_id: str, device_id: int) -> ClockEstimate | None:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT t0_backend_us, t1_device_us, t2_device_us, t3_backend_us, delay_us, offset_us
                FROM clock_observations WHERE session_id=%s AND device_id=%s
                ORDER BY created_at DESC LIMIT 16
                """,
                (session_id, device_id),
            ).fetchall()
        return estimate_clock(rows, max_uncertainty_us=self.max_sync_uncertainty_us)

    def insert_chunk(self, session_id: str, chunk: ChunkV2, stored) -> dict:
        header = chunk.header
        estimate = self.clock_estimate(session_id, header.device_id)
        synchronized = estimate.synchronize(header.device_timestamp_us) if estimate else None
        uncertainty = estimate.uncertainty_us if estimate else None
        with self.database.connection() as connection:
            session = connection.execute("SELECT state FROM sessions WHERE id=%s FOR SHARE", (session_id,)).fetchone()
            if session is None:
                raise LookupError("session not found")
            if session["state"] != "open":
                raise ValueError("session is not open")
            row = connection.execute(
                """
                INSERT INTO chunks(
                    id, session_id, device_id, stream_type, sequence, device_timestamp_us,
                    synchronized_timestamp_us, sync_uncertainty_us, sample_count,
                    sample_period_us, payload_length, crc32, sha256, object_key
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    uuid4(), session_id, header.device_id, header.stream_type, header.sequence,
                    header.device_timestamp_us, synchronized, uncertainty, header.sample_count,
                    header.sample_period_us, header.payload_length, header.crc32, stored.sha256, stored.key,
                ),
            ).fetchone()
        return _public(row)

    def add_clock_observation(self, session_id: str, device_id: int, observation) -> dict:
        with self.database.connection() as connection:
            if connection.execute("SELECT 1 FROM sessions WHERE id=%s", (session_id,)).fetchone() is None:
                raise LookupError("session not found")
            row = connection.execute(
                """
                INSERT INTO clock_observations(
                    session_id, device_id, t0_backend_us, t1_device_us, t2_device_us,
                    t3_backend_us, delay_us, offset_us
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    session_id, device_id, observation.t0_backend_us, observation.t1_device_us,
                    observation.t2_device_us, observation.t3_backend_us,
                    observation.delay_us, observation.offset_us,
                ),
            ).fetchone()
        estimate = self.clock_estimate(session_id, device_id)
        result = _public(row)
        result["estimate"] = asdict(estimate) if estimate else None
        return result

    def add_status(self, session_id: str, device_id: int, event_type: str, device_timestamp_us: int | None, payload: dict) -> dict:
        estimate = self.clock_estimate(session_id, device_id)
        synchronized = estimate.synchronize(device_timestamp_us) if estimate and device_timestamp_us is not None else None
        with self.database.connection() as connection:
            if connection.execute("SELECT 1 FROM sessions WHERE id=%s", (session_id,)).fetchone() is None:
                raise LookupError("session not found")
            row = connection.execute(
                """
                INSERT INTO status_events(session_id, device_id, event_type, device_timestamp_us,
                                          synchronized_timestamp_us, payload)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (session_id, device_id, event_type, device_timestamp_us, synchronized, _json(payload)),
            ).fetchone()
        return _public(row)

    def enqueue(self, session_id: str, job_type: str) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO processing_jobs(id, session_id, job_type, state)
                VALUES (%s,%s,%s,'queued')
                ON CONFLICT(session_id, job_type) DO UPDATE SET
                  state=CASE WHEN processing_jobs.state='complete' THEN processing_jobs.state ELSE 'queued' END,
                  available_at=now(), updated_at=now()
                RETURNING *
                """,
                (uuid4(), session_id, job_type),
            ).fetchone()
        return _public(row)

    def claim_job(self, worker_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT id FROM processing_jobs
                    WHERE state='queued' AND available_at <= now()
                    ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE processing_jobs j SET state='running', attempts=attempts+1,
                    locked_at=now(), locked_by=%s, updated_at=now()
                FROM candidate WHERE j.id=candidate.id RETURNING j.*
                """,
                (worker_id,),
            ).fetchone()
        return _public(row)

    def heartbeat(self, worker_id: str, current_job_id: str | None = None) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO worker_heartbeats(worker_id, last_seen_at, current_job_id)
                VALUES (%s, now(), %s)
                ON CONFLICT(worker_id) DO UPDATE SET last_seen_at=now(), current_job_id=EXCLUDED.current_job_id
                """,
                (worker_id, current_job_id),
            )

    def worker_status(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT worker_id, last_seen_at, current_job_id,
                       last_seen_at >= now() - interval '10 seconds' AS healthy
                FROM worker_heartbeats ORDER BY last_seen_at DESC
                """
            ).fetchall()
        return [_public(row) for row in rows]

    def complete_job(self, job_id: str) -> None:
        with self.database.connection() as connection:
            connection.execute("UPDATE processing_jobs SET state='complete', updated_at=now() WHERE id=%s", (job_id,))

    def fail_job(self, job_id: str, message: str) -> None:
        safe = message[:500]
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE processing_jobs SET state=CASE WHEN attempts < 3 THEN 'queued' ELSE 'failed' END,
                    available_at=now() + interval '10 seconds', error=%s, updated_at=now() WHERE id=%s
                """,
                (safe, job_id),
            )

    def chunks_for_session(self, session_id: str, stream_type: str | None = None) -> list[dict]:
        query = "SELECT * FROM chunks WHERE session_id=%s"
        params: list[Any] = [session_id]
        if stream_type:
            query += " AND stream_type=%s"
            params.append(stream_type)
        query += " ORDER BY synchronized_timestamp_us NULLS LAST, received_at"
        with self.database.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_public(row) for row in rows]

    def save_feature(self, session_id: str, chunk_id: str, modality: str, quality: str, extractor: str, features: dict, provenance: dict) -> dict:
        version = "1"
        start = provenance.get("device_timestamp_us")
        count = provenance.get("sample_count", 0)
        rate = provenance.get("sample_rate_hz", 0)
        end = start + round(count * 1_000_000 / rate) if start is not None and rate else None
        with self.database.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO feature_windows(id, session_id, source_chunk_id, modality, window_start_us,
                    window_end_us, quality_state, extractor, extractor_version, features, provenance)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(source_chunk_id, extractor, extractor_version) DO UPDATE SET
                    quality_state=EXCLUDED.quality_state, features=EXCLUDED.features, provenance=EXCLUDED.provenance
                RETURNING *
                """,
                (uuid4(), session_id, chunk_id, modality, start, end, quality, extractor, version, _json(features), _json(provenance)),
            ).fetchone()
        return _public(row)

    def save_inference(self, session_id: str, feature_window_id: str, decision) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO inference_results(id, session_id, feature_window_id, state, score,
                    confidence, model_name, model_version, reasons)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(feature_window_id, model_name, model_version) DO UPDATE SET
                    state=EXCLUDED.state, score=EXCLUDED.score, confidence=EXCLUDED.confidence, reasons=EXCLUDED.reasons
                RETURNING *
                """,
                (
                    uuid4(), session_id, feature_window_id, decision.state, decision.score,
                    decision.confidence, decision.model_name, decision.model_version,
                    _json(list(decision.reasons)),
                ),
            ).fetchone()
        return _public(row)

    def snapshot(self, session_id: str) -> dict:
        session = self.session(session_id)
        if session is None:
            raise LookupError("session not found")
        with self.database.connection() as connection:
            chunks = connection.execute(
                """
                SELECT device_id, stream_type, count(*) AS count, min(sequence) AS first_sequence,
                       max(sequence) AS last_sequence, max(received_at) AS last_received_at,
                       max(sync_uncertainty_us) AS max_sync_uncertainty_us,
                       (max(sequence) - min(sequence) + 1 - count(*)) AS missing_sequence_count
                FROM chunks WHERE session_id=%s GROUP BY device_id, stream_type ORDER BY device_id
                """,
                (session_id,),
            ).fetchall()
            status = connection.execute(
                "SELECT DISTINCT ON(device_id) * FROM status_events WHERE session_id=%s ORDER BY device_id, received_at DESC",
                (session_id,),
            ).fetchall()
            features = connection.execute(
                "SELECT modality, quality_state, extractor, features, provenance FROM feature_windows WHERE session_id=%s ORDER BY window_start_us",
                (session_id,),
            ).fetchall()
            jobs = connection.execute(
                "SELECT id, job_type, state, attempts, error, updated_at FROM processing_jobs WHERE session_id=%s ORDER BY created_at",
                (session_id,),
            ).fetchall()
            inferences = connection.execute(
                "SELECT state, score, confidence, model_name, model_version, reasons, created_at FROM inference_results WHERE session_id=%s ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return {
            "session": session,
            "streams": [_public(row) for row in chunks],
            "status": [_public(row) for row in status],
            "features": [_public(row) for row in features],
            "jobs": [_public(row) for row in jobs],
            "inferences": [_public(row) for row in inferences],
        }

    def close_session(self, session_id: str) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                "UPDATE sessions SET state='complete', ended_at=now() WHERE id=%s AND state='open' RETURNING *",
                (session_id,),
            ).fetchone()
        if row is None:
            raise LookupError("open session not found")
        return _public(row)

    def export_rows(self, session_id: str) -> dict[str, list[dict]]:
        tables = {
            "chunks": "SELECT * FROM chunks WHERE session_id=%s ORDER BY received_at",
            "clock_observations": "SELECT * FROM clock_observations WHERE session_id=%s ORDER BY created_at",
            "status_events": "SELECT * FROM status_events WHERE session_id=%s ORDER BY received_at",
            "feature_windows": "SELECT * FROM feature_windows WHERE session_id=%s ORDER BY window_start_us",
            "inference_results": "SELECT * FROM inference_results WHERE session_id=%s ORDER BY created_at",
            "processing_jobs": "SELECT * FROM processing_jobs WHERE session_id=%s ORDER BY created_at",
        }
        with self.database.connection() as connection:
            result = {name: [_public(row) for row in connection.execute(query, (session_id,)).fetchall()] for name, query in tables.items()}
            result["audit_events"] = [
                _public(row)
                for row in connection.execute(
                    "SELECT * FROM audit_events WHERE resource_id=%s OR detail->>'session_id'=%s ORDER BY created_at",
                    (session_id, session_id),
                ).fetchall()
            ]
            return result

    def save_export(self, session_id: str, stored) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO exports(id, session_id, object_key, sha256, size_bytes)
                VALUES (%s,%s,%s,%s,%s) RETURNING *
                """,
                (uuid4(), session_id, stored.key, stored.sha256, stored.size),
            ).fetchone()
        return _public(row)

    def latest_export(self, session_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM exports WHERE session_id=%s ORDER BY created_at DESC LIMIT 1", (session_id,)).fetchone()
        return _public(row)

    def session_object_keys(self, session_id: str) -> list[str]:
        with self.database.connection() as connection:
            if connection.execute("SELECT 1 FROM sessions WHERE id=%s", (session_id,)).fetchone() is None:
                raise LookupError("session not found")
            chunk_keys = connection.execute("SELECT object_key FROM chunks WHERE session_id=%s", (session_id,)).fetchall()
            export_keys = connection.execute("SELECT object_key FROM exports WHERE session_id=%s", (session_id,)).fetchall()
        return [row["object_key"] for row in chunk_keys + export_keys]

    def delete_session_rows(self, session_id: str) -> None:
        with self.database.connection() as connection:
            session = connection.execute("SELECT participant_id FROM sessions WHERE id=%s", (session_id,)).fetchone()
            if session is None:
                raise LookupError("session not found")
            credential_ids = [
                row["credential_id"]
                for row in connection.execute("SELECT credential_id FROM session_devices WHERE session_id=%s", (session_id,)).fetchall()
            ]
            connection.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
            if credential_ids:
                connection.execute("DELETE FROM credentials WHERE id = ANY(%s)", (credential_ids,))
            connection.execute(
                "DELETE FROM participants WHERE id=%s AND NOT EXISTS (SELECT 1 FROM sessions WHERE participant_id=%s)",
                (session["participant_id"], session["participant_id"]),
            )
