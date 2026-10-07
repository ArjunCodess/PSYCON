"""Local research API; mutation requests require an explicit same-origin header."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
import sqlite3
import zipfile
from urllib.parse import urlsplit
from ipaddress import ip_address

from flask import Blueprint, current_app, jsonify, render_template, request, send_file, Response

from .features import DICTIONARY, UNAVAILABLE
from .profiles import build_reference, DIMENSIONS, METHOD, ROLE_FRAMEWORKS
from .research import queue_runs, evaluation, annotate, CRITERIA
from .store import encode, uid, now

api = Blueprint("instrument_api", __name__, url_prefix="/api/instrument")
pages = Blueprint("instrument_pages", __name__)


def instrument():
    if "psycon_instrument" not in current_app.extensions:
        import os
        from .service import Instrument
        current_app.extensions["psycon_instrument"] = Instrument(os.getenv("PSYCON_INSTRUMENT_ROOT", "instance/instrument"))
    return current_app.extensions["psycon_instrument"]


def json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body


@api.before_request
def guard():
    host = urlsplit("http://"+request.host).hostname
    if host not in ("127.0.0.1", "localhost", "::1") or not ip_address(request.remote_addr or "0.0.0.0").is_loopback:
        return jsonify(error="The audio research workspace is local-only. Use the standalone localhost runtime."), 403
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("X-PSYCON-Request") != "research-instrument":
            return jsonify(error="This mutation requires the research-instrument request header"), 403
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(error="Cross-origin mutations are disabled"), 403


@pages.before_request
def local_pages():
    return guard()


@api.errorhandler(ValueError)
def invalid(exc):
    return jsonify(error=str(exc)), 400


@api.errorhandler(LookupError)
def missing(exc):
    return jsonify(error=str(exc)), 404


@api.errorhandler(sqlite3.Error)
def database_failure(exc):
    current_app.logger.error("Instrument database failure: %s", type(exc).__name__)
    return jsonify(error="Database operation failed. No analysis result was fabricated."), 503


@pages.get("/instrument")
def workspace():
    return render_template("instrument.html")


@pages.get("/review/<blind_id>")
def review_page(blind_id):
    return render_template("instrument_review.html", blind_id=blind_id)


@api.get("/state")
def state():
    store = instrument().store
    sessions = store.rows("SELECT id,filename,recorded_at,context,split,status,duration,error,dataset FROM sessions ORDER BY recorded_at DESC,created_at DESC")
    return jsonify(sessions=sessions, profiles=store.rows("SELECT * FROM profiles ORDER BY created_at"),
                   target_archetype=store.one("SELECT value FROM workspace_settings WHERE name='target_archetype'")["value"],
                   total_duration=sum(s["duration"] or 0 for s in sessions),
                   speaker_count=store.one("SELECT COUNT(*) AS n FROM speakers")["n"],
                   definition=current_app.config.get("PSYCON_DEFINITION"),
                   evaluated=False, pipeline="audio → speaker evidence → context → baseline → reference → interpretation")


@api.patch("/settings")
def workspace_settings():
    role = json_body().get("target_archetype")
    if role not in ROLE_FRAMEWORKS:
        raise ValueError("Select a supported communication reference")
    store = instrument().store
    store.execute("UPDATE workspace_settings SET value=? WHERE name='target_archetype'", (role,))
    store.execute("UPDATE llm_runs SET status='stale',error='Comparison goal changed; queue a new run' "
                  "WHERE status IN ('queued','running','complete') AND speaker_id IN "
                  "(SELECT id FROM speakers WHERE profile_id IS NULL)")
    return jsonify(target_archetype=role)


@api.post("/sessions")
def upload():
    files = request.files.getlist("recordings")
    if not files:
        raise ValueError("Select at least one recording")
    metadata = json.loads(request.form.get("metadata", "{}"))
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be an object")
    created, errors = [], []
    for file in files:
        try:
            created.append(instrument().ingest(file.stream, file.filename or "", metadata))
        except ValueError as exc:
            errors.append(dict(filename=file.filename, error=str(exc)))
    return jsonify(sessions=created, errors=errors), 201 if created else 400


@api.get("/sessions/<session_id>")
def detail(session_id):
    return jsonify(instrument().detail(session_id))


@api.post("/sessions/<session_id>/retry")
def retry(session_id):
    instrument().retry(session_id)
    return jsonify(status="queued")


@api.delete("/sessions/<session_id>")
def delete(session_id):
    instrument().delete(session_id)
    return jsonify(status="deleted")


@api.patch("/sessions/<session_id>")
def edit_metadata(session_id):
    return jsonify(instrument().edit_metadata(session_id, json_body()))


@api.get("/sessions/<session_id>/audio")
def audio(session_id):
    row = instrument().store.one("SELECT original_path,filename FROM sessions WHERE id=?", (session_id,))
    normalized = Path(row["original_path"]).parent/"normalized.wav"
    if request.args.get("original") == "1":
        return send_file(row["original_path"], download_name=row["filename"], conditional=True)
    if not normalized.exists():
        raise ValueError("Normalized playback is unavailable until preprocessing completes")
    return send_file(normalized, mimetype="audio/wav", conditional=True)


@api.post("/profiles")
def create_profile():
    body = json_body()
    label = str(body.get("label", "")).strip()
    role = body.get("target_archetype", "Executive")
    if not label or len(label) > 100 or role not in ROLE_FRAMEWORKS:
        raise ValueError("Provide a person label and a supported target communication profile")
    row = dict(id=uid(), user_id="local", label=label, created_at=now(), target_archetype=role)
    instrument().store.insert("profiles", row)
    return jsonify(row), 201


@api.patch("/profiles/<profile_id>")
def edit_profile(profile_id):
    role = json_body().get("target_archetype")
    instrument().store.one("SELECT * FROM profiles WHERE id=?", (profile_id,))
    if role not in ROLE_FRAMEWORKS:
        raise ValueError("Select Executive, Builder, Salesperson, or Negotiator")
    instrument().store.execute("UPDATE profiles SET target_archetype=? WHERE id=?", (role, profile_id))
    instrument().store.execute("UPDATE llm_runs SET status='stale',error='Comparison goal changed; queue a new run' "
                               "WHERE speaker_id IN (SELECT id FROM speakers WHERE profile_id=?) AND status IN ('complete','queued','running')", (profile_id,))
    return jsonify(status="updated")


@api.get("/profiles/<profile_id>")
def profile(profile_id):
    return jsonify(instrument().profile(profile_id))


@api.patch("/speakers/<speaker_id>")
def mapping(speaker_id):
    return jsonify(instrument().map_speaker(speaker_id, json_body()))


@api.get("/evidence")
def evidence():
    store = instrument().store
    query = request.args.get("q", "")[:200]
    speaker = request.args.get("speaker_id", "")
    rows = store.rows("SELECT e.*,p.display_name,s.filename FROM evidence e JOIN speakers p ON p.id=e.speaker_id "
                      "JOIN sessions s ON s.id=e.session_id WHERE (e.text LIKE ? OR e.feature LIKE ?) "
                      "AND (?='' OR e.speaker_id=?) ORDER BY s.recorded_at DESC,e.start LIMIT 500",
                      ("%"+query+"%", "%"+query+"%", speaker, speaker))
    for row in rows:
        row["context"] = json.loads(row["context"])
    return jsonify(evidence=rows, limit=500)


@api.get("/dictionary")
def dictionary():
    return jsonify(features=DICTIONARY, unavailable=UNAVAILABLE, normalization=DIMENSIONS, similarity_method=METHOD)


@api.get("/evidence/<evidence_id>")
def evidence_record(evidence_id):
    store = instrument().store
    rows = store.rows("SELECT e.*,p.display_name,s.filename FROM evidence e JOIN speakers p ON p.id=e.speaker_id "
                      "JOIN sessions s ON s.id=e.session_id WHERE e.id=?", (evidence_id,))
    if rows:
        from .annotations import EVENTS
        row = rows[0]
        row["context"] = json.loads(row["context"])
        row["annotations"] = store.rows("SELECT * FROM behavior_annotations WHERE evidence_id=?", (evidence_id,))
        row["session_speakers"] = store.rows("SELECT id,display_name FROM speakers WHERE session_id=?", (row["session_id"],))
        names = {speaker["id"]: speaker["display_name"] for speaker in row["session_speakers"]}
        for direction in ("preceding", "following"):
            neighbor = row["context"].get(direction)
            if neighbor:
                neighbor["display_name"] = names.get(neighbor.get("speaker_id"), "Unattributed")
        row["behavior_types"] = EVENTS
        return jsonify(row)
    # Transcript-only runs cite utterance IDs; those are observable sources too.
    row = store.one("SELECT u.*,p.display_name,s.filename,s.context AS session_context,s.topic FROM utterances u "
                    "LEFT JOIN speakers p ON p.id=u.speaker_id JOIN sessions s ON s.id=u.session_id WHERE u.id=?", (evidence_id,))
    row.update(feature="utterance", level="measured", confidence="moderate", context=dict(session_context=row.pop("session_context"), topic=row.pop("topic")))
    return jsonify(row)


@api.post("/evidence/<evidence_id>/annotations")
def behavior_annotation(evidence_id):
    from .annotations import annotate_behavior
    return jsonify(annotate_behavior(instrument(), evidence_id, json_body())), 201


@api.get("/archetypes")
def archetypes():
    store = instrument().store
    rows = store.rows("SELECT * FROM archetypes ORDER BY sample_count DESC,name")
    for row in rows:
        row["features"] = store.rows("SELECT * FROM archetype_features WHERE archetype_id=?", (row["id"],))
        for feature in row["features"]:
            feature["distribution"] = json.loads(feature["distribution"]) if feature["distribution"] else None
    candidates = store.rows("SELECT p.*,s.filename,s.recorded_at FROM speakers p JOIN sessions s ON s.id=p.session_id "
                            "WHERE s.split='reference' AND s.status='complete'")
    return jsonify(archetypes=rows, reference_speakers=candidates, method=METHOD, normalization=DIMENSIONS)


@api.post("/archetypes")
def reference():
    body = json_body()
    return jsonify(build_reference(instrument().store, str(body.get("name", "")), body.get("speaker_ids", []),
                                   str(body.get("source", "")), bool(body.get("role_labeled", False)))), 201


@api.post("/archetypes/group-lenses")
def group_lenses():
    from .corpus import build_group_lenses
    return jsonify(archetypes=build_group_lenses(instrument())), 201


@api.post("/speakers/<speaker_id>/runs")
def run(speaker_id):
    body = json_body()
    conditions = body.get("conditions", ["A", "B", "C"])
    return jsonify(runs=queue_runs(instrument(), speaker_id, conditions)), 202


@api.get("/runs/<run_id>")
def run_result(run_id):
    row = instrument().store.one("SELECT * FROM llm_runs WHERE id=?", (run_id,))
    for key in ("input", "output"):
        row[key] = json.loads(row[key]) if row[key] else None
    return jsonify(row)


@api.get("/research")
def research():
    return jsonify(evaluation(instrument().store))


@api.get("/review/<blind_id>")
def blinded_report(blind_id):
    row = instrument().store.one("SELECT output,input FROM llm_runs WHERE blind_id=? AND status='complete'", (blind_id,))
    packet = json.loads(row["input"])
    report = json.loads(row["output"])
    records = {source["id"]: source for source in packet["transcript"]}
    records.update({source["id"]: source for source in packet.get("evidence", [])})
    cited = list(dict.fromkeys(source_id for claim in report["claims"] for source_id in claim["evidence_ids"]))
    sources = [{key: records[source_id].get(key) for key in ("id", "speaker_id", "start", "end", "text")}
               for source_id in cited if source_id in records]
    # Omit condition, features, baseline, model, digest, and run ID from reviewer payload.
    return jsonify(blind_id=blind_id, report=report, transcript=packet["transcript"], sources=sources,
                   criteria=CRITERIA, blinding_limitation="Report wording may reveal its condition; reviewers receive no condition labels.")


@api.post("/review/<blind_id>")
def annotate_report(blind_id):
    annotate(instrument().store, blind_id, json_body())
    return jsonify(status="saved")


@api.post("/feature-annotations")
def feature_annotation():
    body = json_body()
    feature = body.get("feature")
    reviewer = str(body.get("reviewer_id", "")).strip()
    expected = body.get("expected")
    if feature not in DICTIONARY or not reviewer or type(expected) not in (int, float) or not math.isfinite(expected):
        raise ValueError("Specify a defined feature, independent reviewer, and finite numeric reference value")
    spec = DICTIONARY[feature]
    lower, upper = spec["valid_range"]
    if expected < lower or (upper is not None and expected > upper):
        raise ValueError("Reference value is outside the feature's defined range")
    row = instrument().store.one("SELECT session_id FROM speakers WHERE id=?", (body.get("speaker_id"),))
    instrument().store.insert("evaluations", dict(id=uid(), session_id=row["session_id"], speaker_id=body["speaker_id"],
                  feature=feature, reviewer_id=reviewer, expected=expected, created_at=now()))
    return jsonify(status="saved"), 201


def csv_text(rows):
    target = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: encode(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    return target.getvalue()


@api.get("/sessions/<session_id>/export/<format>")
def export(session_id, format):
    result = instrument().detail(session_id)
    if format == "json":
        return Response(encode(result), mimetype="application/json", headers={"Content-Disposition": f'attachment; filename="psycon-{session_id}.json"'})
    if format == "csv":
        return Response(csv_text(result["features"]), mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="features.csv"'})
    if format == "rttm":
        labels = {s["id"]: s["label"] for s in result["speakers"]}
        content = "\n".join(f"SPEAKER {session_id} 1 {t['start']:.3f} {t['end']-t['start']:.3f} <NA> <NA> {labels[t['speaker_id']]} <NA> <NA>" for t in result["turns"])
        return Response(content, mimetype="text/plain", headers={"Content-Disposition": 'attachment; filename="diarization.rttm"'})
    if format == "transcript":
        labels = {s["id"]: s["display_name"] for s in result["speakers"]}
        content = "\n".join(f"[{u['start']:.2f}–{u['end']:.2f}] {labels.get(u['speaker_id'], 'Unattributed')}: {u['text']}" for u in result["utterances"])
        return Response(content, mimetype="text/plain", headers={"Content-Disposition": 'attachment; filename="transcript.txt"'})
    if format == "zip":
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("analysis.json", encode(result))
            archive.writestr("feature_dictionary.json", encode(DICTIONARY))
            archive.writestr("research.json", encode(evaluation(instrument().store)))
            archive.writestr("llm_runs.json", encode(instrument().store.rows("SELECT * FROM llm_runs WHERE session_id=?", (session_id,))))
            for name in ("speakers", "turns", "utterances", "words", "features", "evidence", "interactions"):
                archive.writestr(name+".csv", csv_text(result[name]))
        memory.seek(0)
        return send_file(memory, mimetype="application/zip", as_attachment=True, download_name=f"psycon-{session_id}.zip")
    raise ValueError("Choose json, csv, rttm, transcript, or zip")


@api.get("/research/export")
def research_export():
    store = instrument().store
    payload = dict(summary=evaluation(store), annotations=store.rows("SELECT * FROM reviewer_annotations"),
                   feature_annotations=store.rows("SELECT * FROM evaluations"),
                   dataset_manifest=store.rows("SELECT id,sha256,recorded_at,context,dataset,split,participant_ids,conditions,consent,versions FROM sessions"))
    return Response(encode(payload), mimetype="application/json", headers={"Content-Disposition": 'attachment; filename="psycon-research.json"'})
