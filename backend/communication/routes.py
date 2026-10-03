"""Bearer-only private pilot API. No development authentication bypass."""
import json
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, render_template, request

from backend.auth import require_role
from backend.group.errors import GroupError
from backend.routes import error
from .rubrics import ROLES

communication_api = Blueprint("communication", __name__, url_prefix="/api/v1/communication")
coach_pages = Blueprint("coach_pages", __name__)


def service():
    return current_app.extensions["psycon_communication"]


def access(*scopes):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            principal = service().authenticate(header[7:] if header.startswith("Bearer ") else "")
            if not principal:
                return error("unauthorized", "A wearer or explicitly granted token is required", 401)
            if principal["scope"] not in scopes:
                return error("forbidden", "This grant cannot perform that action", 403)
            g.communication = principal
            try:
                return view(*args, **kwargs)
            except LookupError as exc:
                return error("not_found", str(exc), 404)
            except (ValueError, TypeError, KeyError) as exc:
                return error("invalid_request", str(exc), 400)
        return wrapped
    return decorate


def pid():
    return g.communication["profile_id"]


def body_object():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    return body


@coach_pages.get("/coach")
def coach():
    return render_template("coach.html", roles=ROLES)


@communication_api.post("/profiles")
@require_role("operator")
def provision():
    try:
        body = body_object()
        return jsonify(service().provision(body.get("role", "general"), body.get("label", ""))), 201
    except ValueError as exc:
        return error("invalid_profile", str(exc), 400)


@communication_api.post("/source-links")
@require_role("operator")
def source_link():
    try:
        body = body_object()
        if body.get("identity_confirmed") is not True:
            raise ValueError("operator must explicitly confirm the person-to-profile identity link")
        if body.get("type") == "group":
            source = service().sources.group_descriptor(body["session_id"], int(body["slot"]))
        elif body.get("type") == "device":
            source = service().sources.device_descriptor(body["session_id"], body["profile_id"])
        else:
            raise ValueError("source type must be group or device")
        return jsonify(service().link_source(body["profile_id"], source, body["context"])), 202
    except GroupError as exc:
        return error(exc.code, str(exc), exc.status)
    except (ValueError, TypeError, KeyError, LookupError) as exc:
        return error("invalid_source_link", str(exc), 400)


@communication_api.get("/me")
@access("owner", "reviewer")
def me():
    return jsonify(service().profile(pid()) | {"access_scope": g.communication["scope"]})


@communication_api.patch("/me")
@access("owner")
def update_me():
    return jsonify(service().update_profile(pid(), body_object()))


@communication_api.post("/me/enrollment")
@access("owner")
def enrollment():
    files = request.files.getlist("clips")
    if len(files) != 3 or request.form.get("consent") != "yes":
        raise ValueError("three enrollment clips and explicit enrollment consent required")
    if request.content_length is None or request.content_length > 10*1024*1024:
        raise ValueError("enrollment upload limit is 10 MB")
    return jsonify(service().enroll(pid(), [file.read() for file in files])), 202


@communication_api.delete("/me/enrollment")
@access("owner")
def delete_enrollment():
    with service().store.lock(pid()):
        row = service().store.get("profile", pid())
        row.pop("enrollment", None)
        row["enrollment_generation"] = row.get("enrollment_generation", 0)+1
        row["enrollment_status"] = "deleted"
        service().store.put("profile", row)
        for job in service().store.rows("enrollment", pid()):
            try:
                (service().spool/(job["id"]+".encrypted")).unlink(missing_ok=True)
                service().store.delete("enrollment", job["id"])
            except OSError:
                job["state"] = "delete_pending"
                service().store.put("enrollment", job)
    return "", 204


@communication_api.get("/conversations")
@access("owner", "reviewer")
def conversations():
    return jsonify({"conversations": service().conversations(pid())})


@communication_api.post("/conversations")
@access("owner")
def upload():
    if request.content_length is None or request.content_length > 32*1024*1024:
        raise ValueError("personal audio upload limit is 32 MB")
    file = request.files.get("audio")
    if not file or not file.filename or file.filename.lower().split(".")[-1] not in {"wav", "mp3", "ogg", "oga"}:
        raise ValueError("choose a WAV, MP3 or OGG recording")
    row = service().upload(pid(), file.read(), file.filename, json.loads(request.form.get("context", "{}")), request.form.get("occurred_at", ""))
    return jsonify(row), 202


@communication_api.patch("/conversations/<cid>")
@access("owner")
def correction(cid):
    return jsonify(service().correct(pid(), cid, body_object()))


@communication_api.post("/conversations/<cid>/retry")
@access("owner")
def retry(cid):
    with service().store.lock(pid()):
        row = service().store.get("conversation", cid)
        if not row or row["profile_id"] != pid():
            raise LookupError("conversation not found")
        if row["state"] != "failed" or row["raw_state"] == "deleted":
            raise ValueError("retry requires a failed recording whose raw audio still exists")
        row.update(state="queued", revision=row["revision"]+1)
        service().store.put("conversation", row)
    return jsonify({"state": "queued"}), 202


@communication_api.delete("/conversations/<cid>")
@access("owner")
def delete_conversation(cid):
    service().delete_conversation(pid(), cid)
    return "", 204


@communication_api.get("/history")
@access("owner", "reviewer")
def history():
    return jsonify(service().history(pid()))


@communication_api.get("/context")
@access("owner", "context")
def context():
    return jsonify(service().export_context(pid()))


@communication_api.route("/grants", methods=["GET", "POST"])
@access("owner")
def grants():
    if request.method == "POST":
        return jsonify(service().grant(pid(), body_object().get("scope"))), 201
    return jsonify({"grants": [{k:v for k,v in row.items() if k != "token_hash"} for row in service().store.rows("grant", pid())]})


@communication_api.delete("/grants/<gid>")
@access("owner")
def revoke(gid):
    row = service().store.get("grant", gid)
    if not row or row["profile_id"] != pid():
        raise LookupError("grant not found")
    row["revoked"] = True
    service().store.put("grant", row)
    return "", 204


@communication_api.route("/goals", methods=["GET", "POST"])
@access("owner", "reviewer")
def goals():
    if request.method == "POST":
        if g.communication["scope"] != "owner":
            return error("forbidden", "Only the wearer can create goals", 403)
        body = body_object()
        return jsonify(service().goal(pid(), body.get("metric"), body.get("direction"))), 201
    return jsonify({"goals": service().goals(pid())})


@communication_api.delete("/me")
@access("owner")
def delete_me():
    with service().store.lock(pid()):
        profile = service().store.get("profile", pid())
        profile.update(revoked=True, consent=False, label="deleted")
        profile.pop("enrollment", None)
        service().store.put("profile", profile)
        for row in service().store.rows("conversation", pid()):
            service().delete_conversation(pid(), row["id"])
        for job in service().store.rows("enrollment", pid()):
            try:
                (service().spool/(job["id"]+".encrypted")).unlink(missing_ok=True)
                service().store.delete("enrollment", job["id"])
            except OSError:
                job["state"] = "delete_pending"
                service().store.put("enrollment", job)
        for kind in ("goal", "grant", "baseline", "link"):
            for row in service().store.rows(kind, pid()):
                service().store.delete(kind, row["id"])
    return "", 204
