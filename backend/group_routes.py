"""Authenticated group-observation routes."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, render_template, request

from .auth import require_role
from .group.errors import GroupError
from .routes import api, error, pages


group_api = Blueprint("group_api", __name__, url_prefix="/api/v1")


def _service():
    return current_app.extensions["psycon_group"]


def _failure(exc: GroupError):
    return error(exc.code, str(exc), exc.status)


def group_role(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
            if not token:
                g.principal = _service().local_principal()
                return view(*args, **kwargs)
            principal = _service().authenticate(token)
            if principal is None:
                return error("unauthorized", "A named account token is required", 401)
            if principal.role not in roles:
                return error("forbidden", "This account cannot perform that action", 403)
            g.principal = principal
            return view(*args, **kwargs)
        return wrapped
    return decorator


@pages.get("/group")
def group_console():
    return render_template("group_session.html")


@api.post("/group-accounts")
@require_role("operator")
def create_group_account():
    body = request.get_json(silent=True) or {}
    try:
        account, token = _service().provision_account(
            label=str(body.get("label") or ""),
            role=str(body.get("role") or ""),
            account_code=str(body.get("account_code") or ""),
        )
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "created", "account": account, "token": token}), 201


@group_api.get("/group-accounts/me")
@group_role("operator", "psychologist", "reviewer")
def current_group_account():
    return jsonify({"account": {"id": g.principal.id, "label": g.principal.label, "role": g.principal.role}})


@group_api.get("/group-sessions")
@group_role("operator", "psychologist", "reviewer")
def list_group_sessions():
    try:
        return jsonify({"group_sessions": _service().list_sessions(g.principal)})
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-sessions/from-video")
@group_role("operator")
def ingest_group_video():
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_recording", "Attach the video as file", 400)
    try:
        result = _service().ingest_video(g.principal, upload.filename or "", upload.read())
    except GroupError as exc:
        return _failure(exc)
    status = 201 if result["status"] == "marked" else 200
    return jsonify(result), status


@group_api.post("/group-sessions/<uuid:session_id>/labels")
@group_role("operator", "psychologist")
def import_group_labels(session_id):
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_labels", "Attach the spreadsheet as file", 400)
    try:
        stored = _service().import_labels(g.principal, str(session_id), upload.filename or "labels.csv", upload.read())
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "stored", **stored})


@group_api.get("/group-training/faces")
@group_role("operator", "psychologist", "reviewer")
def face_training_status():
    try:
        return jsonify(_service().training_status(g.principal))
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-training/faces")
@group_role("operator", "psychologist")
def run_face_training():
    try:
        return jsonify(_service().train_faces(g.principal))
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-sessions")
@group_role("operator")
def create_group_session():
    try:
        session = _service().create_session(g.principal, request.get_json(silent=True) or {})
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "created", "group_session": session}), 201


@group_api.get("/group-sessions/<uuid:session_id>")
@group_role("operator", "psychologist", "reviewer")
def get_group_session(session_id):
    try:
        return jsonify(_service().get_session(g.principal, str(session_id)))
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-sessions/<uuid:session_id>/consent-signatures")
@group_role("operator")
def store_consent_signature(session_id):
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_signature", "Attach the signature image as file", 400)
    try:
        form_line = int(request.form.get("form_line", "0"))
        stored = _service().store_signature(g.principal, str(session_id), form_line, upload.filename or "signature.jpg", upload.read())
    except GroupError as exc:
        return _failure(exc)
    except ValueError:
        return error("invalid_signature", "form_line must be a number", 400)
    return jsonify({"status": "stored", "signature": stored}), 201


@group_api.post("/group-sessions/<uuid:session_id>/recording")
@group_role("operator")
def upload_group_recording(session_id):
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_recording", "Attach the video as file", 400)
    try:
        result = _service().upload_recording(g.principal, str(session_id), upload.filename or "", upload.read())
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "accepted", **result}), 201


@group_api.get("/group-sessions/<uuid:session_id>/recording")
@group_role("operator", "psychologist", "reviewer")
def recording_status(session_id):
    try:
        view = _service().get_session(g.principal, str(session_id))
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"recording": view["recording"], "failure_reasons": view["processing_failure_reasons"]})


@group_api.post("/group-sessions/<uuid:session_id>/recording/playback")
@group_role("operator", "psychologist", "reviewer")
def playback_grant(session_id):
    try:
        return jsonify(_service().issue_playback(g.principal, str(session_id)))
    except GroupError as exc:
        return _failure(exc)


@group_api.get("/group-sessions/<uuid:session_id>/recording/media")
def recording_media(session_id):
    try:
        data, content_type = _service().read_media(str(session_id), request.args.get("playback_token", ""))
    except GroupError as exc:
        return _failure(exc)
    start, end = 0, len(data) - 1
    status = 200
    requested = request.headers.get("Range")
    if requested and requested.startswith("bytes=") and len(data):
        bounds = requested.removeprefix("bytes=").split("-", 1)
        try:
            start = int(bounds[0]) if bounds[0] else 0
            end = int(bounds[1]) if len(bounds) > 1 and bounds[1] else len(data) - 1
        except ValueError:
            return error("invalid_range", "Range must use byte offsets", 416)
        start = max(0, start)
        end = min(end, len(data) - 1)
        status = 206
    fragment = data[start : end + 1] if data else data
    response = Response(fragment, status=status, mimetype=content_type)
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    response.headers["Cache-Control"] = "no-store"
    return response


@group_api.post("/group-sessions/<uuid:session_id>/reference-frame")
@group_role("operator")
def upload_reference_frame(session_id):
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_frame", "Attach the reference frame as file", 400)
    try:
        return jsonify(_service().upload_reference_frame(g.principal, str(session_id), upload.filename or "", upload.read()))
    except GroupError as exc:
        return _failure(exc)


@group_api.get("/group-sessions/<uuid:session_id>/reference-frame")
@group_role("operator", "psychologist", "reviewer")
def read_reference_frame(session_id):
    try:
        data, content_type = _service().read_reference_frame(g.principal, str(session_id))
    except GroupError as exc:
        return _failure(exc)
    return Response(data, mimetype=content_type, headers={"Cache-Control": "no-store"})


@group_api.put("/group-sessions/<uuid:session_id>/participants")
@group_role("operator")
def assign_participants(session_id):
    try:
        return jsonify(_service().assign_seats(g.principal, str(session_id), request.get_json(silent=True) or {}))
    except GroupError as exc:
        return _failure(exc)


@group_api.put("/group-sessions/<uuid:session_id>/speaker-mappings")
@group_role("operator")
def map_speakers(session_id):
    try:
        return jsonify(_service().map_speakers(g.principal, str(session_id), request.get_json(silent=True) or {}))
    except GroupError as exc:
        return _failure(exc)


@group_api.get("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/marksheets/<uuid:rater_id>")
@group_role("psychologist", "reviewer")
def get_marksheet(session_id, participant_id, rater_id):
    try:
        return jsonify(_service().get_marksheet(g.principal, str(session_id), str(participant_id), str(rater_id)))
    except GroupError as exc:
        return _failure(exc)


@group_api.put("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/marksheets/<uuid:rater_id>")
@group_role("psychologist")
def save_marksheet(session_id, participant_id, rater_id):
    try:
        sheet = _service().save_marksheet(
            g.principal, str(session_id), str(participant_id), str(rater_id), request.get_json(silent=True) or {}
        )
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "draft", "marksheet": sheet})


@group_api.post("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/marksheets/<uuid:rater_id>/submit")
@group_role("psychologist")
def submit_marksheet(session_id, participant_id, rater_id):
    try:
        sheet = _service().submit_marksheet(g.principal, str(session_id), str(participant_id), str(rater_id))
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "submitted", "marksheet": sheet})


@group_api.post("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/marksheets/<uuid:rater_id>/corrections")
@group_role("reviewer")
def correct_marksheet(session_id, participant_id, rater_id):
    try:
        sheet = _service().correct_marksheet(
            g.principal, str(session_id), str(participant_id), str(rater_id), request.get_json(silent=True) or {}
        )
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "corrected", "marksheet": sheet})


@group_api.post("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/review")
@group_role("reviewer")
def review_marksheet(session_id, participant_id):
    try:
        return jsonify(_service().review(g.principal, str(session_id), str(participant_id), request.get_json(silent=True) or {}))
    except GroupError as exc:
        return _failure(exc)


@group_api.get("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/disagreements")
@group_role("reviewer")
def disagreements(session_id, participant_id):
    try:
        return jsonify(_service().disagreements(g.principal, str(session_id), str(participant_id)))
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/attachments")
@group_role("psychologist", "operator")
def attach_pdf(session_id, participant_id):
    upload = request.files.get("file")
    if upload is None:
        return error("invalid_attachment", "Attach the paper marksheet as file", 400)
    try:
        attachment = _service().attach_pdf(
            g.principal, str(session_id), str(participant_id), upload.filename or "marksheet.pdf", upload.read()
        )
    except GroupError as exc:
        return _failure(exc)
    return jsonify({"status": "stored", "attachment": attachment}), 201


@group_api.get("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/attachments/<uuid:attachment_id>")
@group_role("psychologist", "reviewer", "operator")
def read_attachment(session_id, participant_id, attachment_id):
    try:
        data, meta = _service().attachment_bytes(g.principal, str(session_id), str(participant_id), str(attachment_id))
    except GroupError as exc:
        return _failure(exc)
    return Response(data, mimetype="application/pdf", headers={"X-Content-SHA256": meta["sha256"], "Cache-Control": "no-store"})


@group_api.post("/group-sessions/<uuid:session_id>/participants/<uuid:participant_id>/withdraw")
@group_role("operator")
def withdraw_participant(session_id, participant_id):
    try:
        return jsonify(_service().withdraw_participant(g.principal, str(session_id), str(participant_id), request.get_json(silent=True) or {}))
    except GroupError as exc:
        return _failure(exc)


@group_api.delete("/group-sessions/<uuid:session_id>")
@group_role("operator")
def delete_group_session(session_id):
    try:
        _service().delete_session(g.principal, str(session_id))
    except GroupError as exc:
        return _failure(exc)
    return "", 204


@group_api.get("/group-sessions/<uuid:session_id>/export")
@group_role("operator", "reviewer")
def export_group_session(session_id):
    try:
        return jsonify(_service().export_session(g.principal, str(session_id)))
    except GroupError as exc:
        return _failure(exc)


@group_api.post("/group-sessions/<uuid:session_id>/predictions")
@group_role("operator", "psychologist", "reviewer")
def predict_group_session(session_id):
    try:
        return jsonify(_service().predict(g.principal, str(session_id)))
    except GroupError as exc:
        return _failure(exc)
