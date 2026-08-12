from __future__ import annotations

import time

from flask import Blueprint, current_app, g, jsonify, render_template, request

from .auth import require_role
from .services import IngestError
from .sync import ClockObservation


pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__, url_prefix="/api/v1")
CHUNK_MEDIA_TYPE = "application/vnd.psycon.chunk-v2"
STATUS_EVENTS = {"startup", "heartbeat", "sensor_error", "battery_warning", "reconnect", "overrun", "watchdog_reset", "shutdown", "light"}


def repository():
    return current_app.extensions["psycon_repository"]


def error(code: str, message: str, status: int):
    return jsonify({"status": "error", "error": {"code": code, "message": message}}), status


@pages.get("/")
def dashboard():
    return render_template("dashboard.html")


@api.get("/health")
def health():
    return jsonify({"status": "ok", "service": "psycon-backend"})


@api.get("/ready")
def ready():
    database = current_app.extensions["psycon_db"].ping()
    storage = current_app.extensions["psycon_storage"].ping()
    return jsonify({"status": "ready" if database and storage else "unavailable", "database": database, "object_storage": storage}), (200 if database and storage else 503)


@api.get("/time")
def backend_time():
    return jsonify({"backend_time_us": time.time_ns() // 1_000})


@api.get("/system")
@require_role("operator")
def system_status():
    return jsonify({"workers": repository().worker_status()})


@api.get("/sessions")
@require_role("operator")
def sessions():
    return jsonify({"sessions": repository().list_sessions()})


@api.post("/sessions")
@require_role("operator")
def create_session():
    body = request.get_json(silent=True) or {}
    try:
        session = repository().create_session(
            str(body.get("anonymous_code", "")),
            body.get("versions") if isinstance(body.get("versions"), dict) else {},
            body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
        )
    except ValueError as exc:
        return error("invalid_session", str(exc), 400)
    repository().record_audit(g.principal.id, "create", "session", session["id"])
    return jsonify({"status": "created", "session": session}), 201


@api.post("/devices")
@require_role("operator")
def create_device():
    body = request.get_json(silent=True) or {}
    try:
        device, token = repository().issue_device(
            str(body.get("label", "")), int(body.get("device_id", -1)), str(body.get("session_id", ""))
        )
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    except (TypeError, ValueError) as exc:
        return error("invalid_device", str(exc), 400)
    repository().record_audit(g.principal.id, "issue_credential", "device", str(device["device_id"]), {"session_id": body["session_id"]})
    return jsonify({"status": "created", "device": device, "token": token}), 201


@api.post("/sessions/<uuid:session_id>/chunks")
@require_role("operator", "device")
def ingest_chunk(session_id):
    if request.mimetype != CHUNK_MEDIA_TYPE:
        return error("unsupported_media_type", f"Content-Type must be {CHUNK_MEDIA_TYPE}", 415)
    settings = current_app.extensions["psycon_settings"]
    if request.content_length is not None and request.content_length > settings.max_chunk_bytes:
        return error("payload_too_large", "Protocol v2 request exceeds 65,576 bytes", 413)
    packet = request.get_data(cache=False)
    if len(packet) > settings.max_chunk_bytes:
        return error("payload_too_large", "Protocol v2 request exceeds 65,576 bytes", 413)
    try:
        status, row = current_app.extensions["psycon_ingestion"].ingest(str(session_id), packet, g.principal)
    except IngestError as exc:
        return error(exc.code, str(exc), exc.status_code)
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    except ValueError as exc:
        return error("invalid_session_state", str(exc), 409)
    return jsonify({"status": status, "chunk": row}), (201 if status == "accepted" else 200)


@api.post("/sessions/<uuid:session_id>/clock-sync")
@require_role("operator", "device")
def clock_sync(session_id):
    body = request.get_json(silent=True) or {}
    try:
        device_id = int(body["device_id"])
        if g.principal.role == "device" and g.principal.device_id != device_id:
            return error("device_mismatch", "Credential is not valid for this device", 403)
        if g.principal.role == "device" and not repository().session_allows_device(str(session_id), g.principal.id, device_id):
            return error("session_forbidden", "Device is not assigned to this session", 403)
        observation = ClockObservation(
            int(body["t0_backend_us"]), int(body["t1_device_us"]),
            int(body["t2_device_us"]), int(body.get("t3_backend_us", time.time_ns() // 1_000)),
        )
        observation.validate(current_app.extensions["psycon_settings"].sync_max_delay_us)
        result = repository().add_clock_observation(str(session_id), device_id, observation)
    except KeyError:
        return error("invalid_clock_exchange", "Four clock timestamps and device_id are required", 400)
    except (TypeError, ValueError) as exc:
        return error("invalid_clock_exchange", str(exc), 400)
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    return jsonify({"status": "accepted", "observation": result})


@api.post("/sessions/<uuid:session_id>/status")
@require_role("operator", "device")
def status_event(session_id):
    body = request.get_json(silent=True) or {}
    try:
        device_id = int(body["device_id"])
        event_type = str(body["event_type"])
        if event_type not in STATUS_EVENTS:
            raise ValueError("unsupported status event_type")
        if g.principal.role == "device" and g.principal.device_id != device_id:
            return error("device_mismatch", "Credential is not valid for this device", 403)
        if g.principal.role == "device" and not repository().session_allows_device(str(session_id), g.principal.id, device_id):
            return error("session_forbidden", "Device is not assigned to this session", 403)
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("status payload must be an object")
        result = repository().add_status(
            str(session_id), device_id, event_type,
            int(body["device_timestamp_us"]) if body.get("device_timestamp_us") is not None else None,
            payload,
        )
    except KeyError:
        return error("invalid_status", "device_id and event_type are required", 400)
    except (TypeError, ValueError) as exc:
        return error("invalid_status", str(exc), 400)
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    return jsonify({"status": "accepted", "event": result}), 201


@api.get("/sessions/<uuid:session_id>")
@require_role("operator")
def session_snapshot(session_id):
    try:
        return jsonify(repository().snapshot(str(session_id)))
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)


@api.post("/sessions/<uuid:session_id>/process")
@require_role("operator")
def process_session(session_id):
    if repository().session(str(session_id)) is None:
        return error("session_not_found", "session not found", 404)
    job = repository().enqueue(str(session_id), "process_session")
    return jsonify({"status": job["state"], "job": job}), 202


@api.post("/sessions/<uuid:session_id>/close")
@require_role("operator")
def close_session(session_id):
    try:
        session = repository().close_session(str(session_id))
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    repository().record_audit(g.principal.id, "close", "session", str(session_id))
    return jsonify({"status": "complete", "session": session})


@api.delete("/sessions/<uuid:session_id>")
@require_role("operator")
def delete_session(session_id):
    storage = current_app.extensions["psycon_storage"]
    try:
        keys = repository().session_object_keys(str(session_id))
        for key in keys:
            storage.delete(key)
        repository().delete_session_rows(str(session_id))
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    except Exception:
        return error("storage_error", "Session deletion stopped because one or more stored objects could not be removed", 500)
    repository().record_audit(g.principal.id, "delete", "session", str(session_id), {"object_count": len(keys)})
    return "", 204


@api.post("/sessions/<uuid:session_id>/exports")
@require_role("operator")
def create_export(session_id):
    try:
        export = current_app.extensions["psycon_exporter"].build(str(session_id))
    except LookupError as exc:
        return error("session_not_found", str(exc), 404)
    repository().record_audit(g.principal.id, "export", "session", str(session_id), {"export_id": export["id"]})
    return jsonify({"status": "created", "export": export}), 201


@api.get("/sessions/<uuid:session_id>/exports/latest")
@require_role("operator")
def latest_export(session_id):
    export = repository().latest_export(str(session_id))
    if export is None:
        return error("export_not_found", "No export exists for this session", 404)
    url = current_app.extensions["psycon_storage"].signed_download_url(export["object_key"])
    return jsonify({"export": export, "download_url": url, "expires_in_seconds": 300})
