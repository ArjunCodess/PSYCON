from __future__ import annotations

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.group import psycon
from backend.group.coaching import GroupCoaching, suggest_practice
from backend.group.errors import GroupError
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupObservationService


def workflow():
    store = MemoryGroupStore()
    service = GroupObservationService(store, Mock())
    actor = service.local_principal()
    session_id = service.create_session(actor, {"participant_count": 2, "language": "en", "topic": "Planning a class project"})["session"]["id"]
    store.insert_recording({"group_session_id": session_id, "sha256": "source-hash", "processing_state": "complete",
                            "processing": {"psycon_matching": {"status": "complete", "version": psycon.MATCHING_VERSION,
                                                                 "model_revision": psycon.MODEL_REVISION},
                                           "transcript": [{"start_s": 1, "end_s": 2, "text": "We could divide the work."},
                                                          {"start_s": 2, "end_s": 5, "text": "Crosses the speaker boundary."}]}})
    store.replace_voice_analysis(session_id, [
        {"id": str(uuid4()), "slot_number": 1, "status": "assigned", "start_s": 1, "end_s": 3, "evidence": {}},
        {"id": str(uuid4()), "slot_number": None, "status": "unknown", "start_s": 5, "end_s": 6, "evidence": {}},
    ], [], "psycon")
    service.import_labels(actor, session_id, "ratings.csv", b"participant,class,A,E,L\n1,student,0,3,N/O\n2,student,2,0,0\n")
    return store, service, actor, session_id


def test_spreadsheet_provenance_feedback_and_shared_context():
    store, service, actor, session_id = workflow()
    source = store.label_imports_for(session_id)[0]
    assert source["csv"].startswith("participant,class,A,E,L")
    assert source["rows"][0]["scores"]["L"] == "N/O"
    assert len(store.training_labels_for(session_id)) == 6
    seen = []
    def interpreter(context, findings):
        seen.append(context)
        return {"state": "local_llm", "suggestions": {f["id"]: "Use one example from this class project." for f in findings}}
    coach = GroupCoaching(service, interpreter=interpreter)
    coach.request(actor, session_id, {"topic": "Class project", "setting": "Classroom", "objective": "Agree on responsibilities"})
    coach.run(store.claim_job("test-worker"))
    report = coach.get(actor, session_id)
    assert report["status"] == "complete"
    assert len(report["people"]) == 2
    assert seen == [report["shared_context"]]
    first = report["people"][0]
    assert first["strengths"][0]["score"] == "0"
    assert first["improvements"][0]["item_letter"] == "E"
    assert first["improvements"][0]["practice"] == "Use one example from this class project."
    assert first["not_observed"] == ["L"]
    assert first["evidence"][0]["text"] == "We could divide the work."
    assert len(first["evidence"]) == 1
    assert len(store.training_labels_for(session_id)) == 6


def test_corrections_withdrawal_and_context_invalidate_feedback():
    store, service, actor, session_id = workflow()
    coach = GroupCoaching(service, interpreter=lambda *_: {"state": "rule_based", "suggestions": {}})
    coach.run(store.claim_job("worker"))
    assert coach.get(actor, session_id)["status"] == "complete"
    person = store.participants(session_id)[0]
    store.update_participant(person["id"], withdrawn_at="now")
    assert coach.get(actor, session_id)["status"] == "stale"
    assert coach.get(actor, session_id)["people"] == []
    coach.request(actor, session_id, {"topic": "Updated topic"})
    coach.run(store.claim_job("worker"))
    assert [p["slot_number"] for p in coach.get(actor, session_id)["people"]] == [2]
    service.import_labels(actor, session_id, "corrected.csv", b"participant,class,A\n2,student,1\n")
    assert len(store.label_imports_for(session_id)) == 2
    assert coach.get(actor, session_id)["people"] == []
    assert coach.get(actor, session_id)["context"]["topic"] == "Updated topic"


def test_old_worker_cannot_overwrite_new_request():
    store, service, actor, session_id = workflow()
    def interpreter(*_):
        GroupCoaching(service).request(actor, session_id, {"topic": "New context"}, force=True)
        return {"state": "rule_based", "suggestions": {}}
    GroupCoaching(service, interpreter=interpreter).run(store.claim_job("worker"))
    row = store.feedback_for(session_id)
    assert row["status"] == "queued"
    assert row["context"]["topic"] == "New context"


def test_feedback_requires_labels_and_rejects_bad_context():
    store, service, actor, session_id = workflow()
    coach = GroupCoaching(service)
    with pytest.raises(GroupError, match="context"):
        coach.request(actor, session_id, {"topic": "x" * 501})
    store.replace_training_labels(session_id, [])
    with pytest.raises(GroupError, match="spreadsheet"):
        coach.request(actor, session_id)


def test_invalid_reupload_keeps_existing_labels_and_report():
    store, service, actor, session_id = workflow()
    prior = store.feedback_for(session_id)
    with pytest.raises(GroupError):
        service.import_labels(actor, session_id, "bad.csv", b"participant,class,A\n1,student,9\n")
    assert store.feedback_for(session_id) == prior
    assert len(store.training_labels_for(session_id)) == 6


def test_llm_rejects_invented_evidence_and_keeps_rule_fallback(monkeypatch):
    monkeypatch.setenv("PSYCON_OLLAMA_DIGEST", "pinned")
    responses = [{"models": [{"name": "qwen3.5:4b", "digest": "pinned"}]},
                 {"message": {"content": json.dumps({"suggestions": [{"evidence_id": "invented", "practice": "Invented exercise"}]})}}]
    def opened(*args, **kwargs):
        import io
        return io.StringIO(json.dumps(responses.pop(0)))
    monkeypatch.setattr("backend.group.coaching.urlopen", opened)
    result = suggest_practice({}, [{"id": "rating:1:A"}])
    assert result["state"] == "rule_based"
    assert result["suggestions"] == {}


def test_report_deleted_with_session():
    store, service, actor, session_id = workflow()
    store.delete_session(session_id)
    assert store.feedback_for(session_id) is None
    assert store.label_imports_for(session_id) == []


def test_feedback_api_persists_context_and_reviewer_is_read_only():
    from tests.backend.test_group_workflow import build_app
    store, service, actor, session_id = workflow()
    app = build_app(service)
    client = app.test_client()
    response = client.post(f"/api/v1/group-sessions/{session_id}/feedback", json={"context": {"topic": "Shared topic"}})
    assert response.status_code == 202
    assert client.get(f"/api/v1/group-sessions/{session_id}/feedback").json["context"]["topic"] == "Shared topic"
    _, token = service.provision_account(label="Review", role="reviewer", account_code="REVIEW-FEEDBACK")
    headers = {"Authorization": "Bearer " + token}
    assert client.get(f"/api/v1/group-sessions/{session_id}/feedback", headers=headers).status_code == 200
    assert client.post(f"/api/v1/group-sessions/{session_id}/feedback", headers=headers, json={}).status_code == 403
