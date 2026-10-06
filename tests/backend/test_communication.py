import copy
import base64
import json
import io
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from flask import Flask

from backend.communication.analysis import observations
from backend.communication.llm import LocalInterpreter, validate_events
from backend.communication.longitudinal import summarize
from backend.communication.routes import communication_api, coach_pages
from backend.communication.service import CommunicationService, Enrollment
from backend.communication.sources import SourceAdapters, assemble_device_audio
from backend.communication.store import MemoryCommunicationStore
from backend.simulator import audio_packet
from protocol.chunk import encode_chunk_v2
from ml.src.speaker_analysis import VoiceProfile

CONTEXT = {"language": "en", "conversation_type": "discussion", "microphone": "mic-a", "setting": "work"}


class FakeInterpreter:
    def interpret(self, evidence, context=None):
        return {"state": "unavailable", "events": []}


def analysis(raw, filename, digest, profile):
    assert profile is not None
    return {"identity": "verified", "quality": "usable", "language": "en", "usable_speech_s": 400,
            "metrics": {"speaking_share": .3}, "evidence": [{"id": "e0", "start_s": 1, "end_s": 2, "excerpt": "one point"}],
            "_transient": [{"id": "t0", "text": "FULL PRIVATE TRANSCRIPT"}]}


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setenv("PSYCON_PROFILE_KEY", "test-private-key-"*4)
    store = MemoryCommunicationStore()
    service = CommunicationService(store, spool=tmp_path/"spool", analyzer=analysis, interpreter=FakeInterpreter())
    first, second = service.provision("leadership", "First wearer"), service.provision("sales", "Second wearer")
    for user in (first, second):
        service.update_profile(user["id"], {"consent": True})
        Enrollment(service, store.get("profile", user["id"])).save(VoiceProfile(np.array([1., 0.]), "fake", 3, 18))
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[2]/"backend/templates"))
    app.extensions["psycon_communication"] = service
    app.register_blueprint(communication_api)
    app.register_blueprint(coach_pages)
    return service, app.test_client(), first, second


def headers(user):
    return {"Authorization": "Bearer "+user["token"]}


def history_rows(count=8):
    return [{"id": str(i), "state": "complete", "occurred_at": f"2026-09-{i+1:02}T12:00:00+00:00", "context": copy.deepcopy(CONTEXT),
             "analysis": {"identity": "verified", "quality": "usable", "usable_speech_s": 400,
                          "metrics": {"speaking_share": .3 if i<5 else .8}, "evidence": []}} for i in range(count)]


def test_prior_only_baseline_and_three_later_sessions():
    rows = history_rows()
    assert summarize(rows[:5])["patterns"] == []
    assert summarize(rows[:7])["patterns"] == []
    report = summarize(rows)
    assert report["baselines"][0]["reference"]["metrics"]["speaking_share"]["median"] == .3
    assert report["patterns"][0]["source_ids"] == ["5", "6", "7"]
    comparison = summarize(rows[:6])["comparisons"][0]
    assert comparison["conversation_id"] == "5" and comparison["reference_source_ids"] == ["0", "1", "2", "3", "4"]
    assert comparison["metrics"]["speaking_share"]["delta"] == pytest.approx(.5)


def test_incompatible_capture_and_uncertain_identity_abstain():
    rows = history_rows()
    rows[-1]["context"]["microphone"] = "mic-b"
    assert summarize(rows)["patterns"] == []
    rows[-1]["context"]["microphone"] = "mic-a"
    rows[-1]["analysis"]["identity"] = "uncertain"
    assert summarize(rows)["patterns"] == []


def test_one_day_cannot_make_baseline_regardless_of_duration():
    rows = history_rows(5)
    for row in rows:
        row["occurred_at"] = "2026-09-01T12:00:00+00:00"
        row["analysis"]["usable_speech_s"] = 5000
    assert summarize(rows)["baselines"][0]["reference"]["state"] == "building"


def test_future_conversations_cannot_build_or_influence_history(system):
    service, _, user, _ = system
    future = (datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
    with pytest.raises(ValueError, match="future"):
        service.upload(user["id"], b"future", "future.wav", CONTEXT, future)
    rows = history_rows()
    rows[-1]["occurred_at"] = future
    assert summarize(rows)["patterns"] == []


def test_baseline_snapshot_changes_when_support_is_corrected():
    rows = history_rows(5)
    original = summarize(rows)["baselines"][0]["reference"]["snapshot_id"]
    assert summarize(copy.deepcopy(rows))["baselines"][0]["reference"]["snapshot_id"] == original
    rows[0]["revision"] = 1
    assert summarize(rows)["baselines"][0]["reference"]["snapshot_id"] != original


def test_dedup_encrypted_raw_and_delete_after_processing(system):
    service, _, user, _ = system
    row = service.upload(user["id"], b"private raw", "test.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    duplicate = service.upload(user["id"], b"private raw", "test.wav", CONTEXT, "2026-09-02T12:00:00+00:00")
    assert row["id"] == duplicate["id"]
    assert b"private raw" not in (service.spool/(row["id"]+".encrypted")).read_bytes()
    assert service.process_one()
    completed = service.conversations(user["id"])[0]
    assert completed["state"] == "complete" and completed["raw_state"] == "deleted"
    assert not list(service.spool.iterdir())
    assert "FULL PRIVATE TRANSCRIPT" not in repr(service.store.records)


def test_private_access_and_revocable_context_grants(system):
    service, client, user, other = system
    assert client.get("/api/v1/communication/me").status_code == 401
    assert client.get("/api/v1/communication/me", headers=headers(user)).json["id"] == user["id"]
    assert client.get("/api/v1/communication/me", headers=headers(other)).json["id"] == other["id"]
    grant = service.grant(user["id"], "context")
    assert client.get("/api/v1/communication/context", headers=headers(grant)).status_code == 200
    assert client.get("/api/v1/communication/history", headers=headers(grant)).status_code == 403
    assert client.delete("/api/v1/communication/grants/"+grant["id"], headers=headers(user)).status_code == 204
    assert client.get("/api/v1/communication/context", headers=headers(grant)).status_code == 401


def test_read_only_reviewer_and_foreign_conversation_protection(system):
    service, client, user, other = system
    grant = service.grant(user["id"], "reviewer")
    assert client.get("/api/v1/communication/history", headers=headers(grant)).status_code == 200
    assert client.patch("/api/v1/communication/me", json={"role": "law"}, headers=headers(grant)).status_code == 403
    row = service.upload(user["id"], b"one", "one.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    path = "/api/v1/communication/conversations/"+row["id"]
    assert client.delete(path, headers=headers(other)).status_code == 404
    assert client.patch(path, json={"context": CONTEXT}, headers=headers(other)).status_code == 404


def test_profile_deletion_revokes_access_and_removes_enrollment(system):
    service, client, user, other = system
    grant = service.grant(user["id"], "reviewer")
    service.upload(user["id"], b"one", "one.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    assert client.delete("/api/v1/communication/me", headers=headers(user)).status_code == 204
    assert service.authenticate(user["token"]) is None and service.authenticate(grant["token"]) is None
    assert service.conversations(user["id"]) == [] and not list(service.spool.iterdir())
    assert "enrollment" not in service.store.get("profile", user["id"])
    assert service.authenticate(other["token"])


def test_correction_invalidates_frozen_goal_and_pattern(system):
    service, _, user, _ = system
    for row in history_rows():
        row.update(profile_id=user["id"], revision=0, raw_state="deleted", created_at=row["occurred_at"])
        service.store.put("conversation", row)
    goal = service.goal(user["id"], "speaking_share", "decrease")
    assert service.history(user["id"])["patterns"]
    service.correct(user["id"], "7", {"context": CONTEXT | {"microphone": "mic-b"}})
    assert service.store.get("goal", goal["id"])["state"] == "reference_invalidated"
    assert service.history(user["id"])["patterns"] == []
    service.delete_conversation(user["id"], "6")
    assert service.store.get("conversation", "6") is None


def test_failed_cleanup_remains_durable_until_retry(system, monkeypatch):
    service, _, user, _ = system
    row = service.upload(user["id"], b"one", "one.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", lambda *a, **k: (_ for _ in ()).throw(OSError("locked")))
        service.delete_conversation(user["id"], row["id"])
        assert service.store.get("conversation", row["id"])["state"] == "delete_pending"
    assert service.process_one()
    assert service.store.get("conversation", row["id"]) is None


def test_failed_upload_expires(system):
    service, client, user, _ = system
    row = service.upload(user["id"], b"bad", "bad.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    stored = service.store.get("conversation", row["id"])
    stored.update(state="failed", created_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
    service.store.put("conversation", stored)
    service.process_one()
    assert service.store.get("conversation", row["id"])["raw_state"] == "deleted"
    assert client.post(f"/api/v1/communication/conversations/{row['id']}/retry", headers=headers(user)).status_code == 400


def test_context_export_omits_biometrics_and_private_evidence(system):
    service, _, user, _ = system
    text = json.dumps(service.export_context(user["id"]))
    assert all(word not in text for word in ("embedding", "enrollment", "excerpt", "token_hash"))


def test_semantics_requires_valid_evidence_and_observable_type():
    evidence = [{"id": "t0"}]
    assert validate_events({"events": [{"type": "objection", "evidence_ids": ["t0"]}]}, evidence)
    for output in ({"events": [{"type": "defensive_personality", "evidence_ids": ["t0"]}]},
                   {"events": [{"type": "criticism", "evidence_ids": ["invented"]}]}, {"events": "bad"}):
        with pytest.raises(ValueError):
            validate_events(output, evidence)


def test_local_llm_abstains_without_pin_and_rejects_cloud(monkeypatch):
    monkeypatch.delenv("PSYCON_OLLAMA_DIGEST", raising=False)
    assert LocalInterpreter().interpret([])["state"] == "unavailable"
    monkeypatch.setenv("PSYCON_OLLAMA_URL", "https://external.example")
    with pytest.raises(ValueError):
        LocalInterpreter()


def test_processing_counts_full_semantic_pass_before_excerpt_cap_and_correction(system):
    service, _, user, _ = system
    def analyzer(raw, filename, digest, profile):
        value = analysis(raw, filename, digest, profile)
        value["_transient"] = [{"id": f"t{i}", "speaker": "wearer", "start_s": i*3, "end_s": i*3+2,
                                "text": "I recognize your point.", "word_count": 5} for i in range(20)]
        return value
    class Interpreter:
        def interpret(self, evidence, context=None):
            assert context["role"] == "leadership" and context["setting"] == "work"
            return {"state": "validated", "coverage": "complete_windows", "enabled_types": ["acknowledgement"],
                    "events": [{"type": "acknowledgement", "evidence_ids": [e["id"]]} for e in evidence[:15]]}
    service.analyzer, service.interpreter = analyzer, Interpreter()
    row = service.upload(user["id"], b"semantic", "test.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    assert service.process_one()
    completed = service.conversations(user["id"])[0]
    assert completed["analysis"]["metrics"]["acknowledgement_per_turn"] == .75
    assert "clarification_per_turn" not in completed["analysis"]["metrics"]
    assert len(completed["analysis"]["events"]) == 12
    assert completed["analysis"]["semantic_counts"]["acknowledgement_per_turn"]["observed"] == 15
    assert completed["raw_state"] == "deleted"
    service.correct(user["id"], row["id"], {"events": []})
    assert "acknowledgement_per_turn" not in service.history_rows(user["id"])[0]["analysis"]["metrics"]


def test_paired_correction_uses_original_turns_despite_duplicate_excerpts(system):
    service, _, user, _ = system
    row = service.upload(user["id"], b"paired", "test.wav", CONTEXT, "2026-09-01T12:00:00+00:00")
    assert service.process_one()
    stored = service.store.get("conversation", row["id"])
    other = {"id": "q", "speaker": "other_1", "start_s": 0, "end_s": 2, "excerpt": "When?"}
    own = {"id": "a", "speaker": "wearer", "start_s": 3, "end_s": 5, "excerpt": "Tomorrow."}
    stored["analysis"].update(evidence=[other, own, {**own, "id": "duplicate"}], turns=[other, own])
    service.store.put("conversation", stored)
    correction = {"events": [{"type": "direct_answer", "evidence_ids": ["q", "a"]}]}
    assert service.correct(user["id"], row["id"], correction)["analysis"]["human_events"][0]["evidence_ids"] == ["q", "a"]
    stored = service.store.get("conversation", row["id"])
    stored["analysis"]["turns"].insert(1, {"speaker": "other_2", "start_s": 2, "end_s": 2.5})
    service.store.put("conversation", stored)
    with pytest.raises(ValueError, match="consecutive"):
        service.correct(user["id"], row["id"], correction)


def test_device_assembly_rejects_time_gaps():
    packets = [encode_chunk_v2(stream_type="audio_pcm", device_id=1, sequence=i+1, device_timestamp_us=i*500000,
                               sample_count=8000, sample_period_us=62, payload=np.zeros(8000,dtype="<i2").tobytes()) for i in range(2)]
    rows = [{"synchronized_timestamp_us": 1000000+i*500000, "sync_uncertainty_us": 1000} for i in range(2)]
    assert assemble_device_audio(packets, rows).startswith(b"RIFF")
    rows[1]["synchronized_timestamp_us"] += 20000
    with pytest.raises(ValueError, match="gaps"):
        assemble_device_audio(packets, rows)
    rows[1]["synchronized_timestamp_us"] -= 20000
    rows[1]["sync_uncertainty_us"] = None
    with pytest.raises(ValueError, match="uncertainty"):
        assemble_device_audio(packets, rows)
    with pytest.raises(ValueError, match="timing record"):
        assemble_device_audio(packets[:1], rows)


def test_group_source_uses_original_timing_and_rechecks_consent(system):
    service, _, user, _ = system
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
        handle.writeframes((np.sin(np.arange(160000)*2*np.pi*200/16000)*4000).astype("<i2").tobytes())
    session = {"consent_status": "recorded", "recording_start_time": "2026-09-01T12:00:00+00:00"}
    store = SimpleNamespace(
        session=lambda sid: session,
        participants=lambda sid: [{"id": "source-person", "slot_number": 1}],
        recording_for_session=lambda sid: {"sha256": "original-hash", "audio_object_key": "shared-audio"},
        voice_segments_for=lambda sid, method: [{"slot_number": 1, "status": "assigned", "start_s": 5., "end_s": 9.}],
        voice_profiles_for=lambda sid, method: [{"slot_number": 1, "metrics": {"transcription": {"language": "en", "words": [
            {"start_s": 5.2, "end_s": 5.8, "text": "clear"}]}}}])
    group = SimpleNamespace(store=store, get_session=lambda actor, sid: {},
                            face_voice_details=lambda actor, sid, method: {"people": [{"slot_number": 1, "voice": {"status": "ready"}}]})
    service.sources = SourceAdapters(group, None, SimpleNamespace(get=lambda key: output.getvalue()))
    source = service.sources.group_descriptor("group-a", 1)
    row = service.link_source(user["id"], source, CONTEXT)
    assert service.process_one()
    completed = service.store.get("conversation", row["id"])
    result = completed["analysis"]
    assert completed["state"] == "complete" and completed["raw_state"] == "research_source_retained"
    assert result["attributed_words"][0]["start_s"] == 5.2
    assert result["evidence"][0]["start_s"] == 5.
    assert "response_gap_s" not in result["metrics"] and "candidate_interruptions_per_min" not in result["metrics"]
    service.delete_conversation(user["id"], row["id"])
    session["consent_status"] = "withdrawn"
    with pytest.raises(ValueError, match="consent"):
        service.sources.group_descriptor("group-a", 1)


def test_overlap_is_excluded_from_personal_acoustics():
    rate = 16000
    samples = np.ones(rate*6, dtype=np.int16)*100
    turns = [{"start_s": 0, "end_s": 6, "speaker_id": "wearer"}]
    regular = turns+[{"start_s": 2, "end_s": 4, "speaker_id": "other"}]
    result = observations(samples, rate, turns, regular, [], "wearer", [{"start_s": 0, "end_s": 6, "status": "usable"}], "verified")
    assert result["usable_speech_s"] == 4
    assert result["metrics"]["speaking_share"] == pytest.approx(4/6)
    assert result["overlap_events"] == [{"start_s": 2, "end_s": 4}]


@pytest.mark.parametrize("role", ["general","leadership","sales","teaching","law","debate","negotiation","medicine","student","presentation"])
def test_all_role_reports_keep_evidence_and_general_focus(role):
    report = summarize(history_rows(), role)
    assert report["focus"] and report["general_focus"] and report["patterns"][0]["evidence_count"] == 3
    assert "score" not in report


def test_coach_renders_without_exposing_personal_data(system):
    _, client, _, _ = system
    response = client.get("/coach")
    assert response.status_code == 200 and b"Your communication, over time" in response.data


def test_enrollment_queues_encrypted_clips_and_runs_on_worker(system, monkeypatch):
    service, _, user, _ = system
    class Embedder:
        engine_name = "fake-enrollment"
        def embed(self, samples, rate):
            return np.array([1., 0.], dtype=np.float32)
    monkeypatch.setattr("backend.communication.service.SpeechBrainEmbedder", Embedder)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        signal = (np.sin(np.arange(96000)*2*np.pi*200/16000)*4000).astype("<i2")
        wav.writeframes(signal.tobytes())
    raw = buffer.getvalue()
    assert service.enroll(user["id"], [raw]*3)["state"] == "queued"
    assert service.profile(user["id"])["enrollment_status"] == "queued"
    job = service.store.rows("enrollment", user["id"])[0]
    encrypted = (service.spool/(job["id"]+".encrypted")).read_bytes()
    assert encrypted != raw and not encrypted.startswith(b"RIFF")
    assert [base64.b64decode(clip) for clip in json.loads(service.cipher().decrypt(encrypted))] == [raw]*3
    assert service.process_one()
    assert service.profile(user["id"])["enrollment_status"] == "complete"
    assert service.voice(user["id"]).engine == "fake-enrollment"
    assert service.store.rows("enrollment", user["id"]) == [] and not list(service.spool.iterdir())


def test_deleting_enrollment_cancels_queued_work(system):
    service, client, user, _ = system
    service.enroll(user["id"], [b"clip"]*3)
    assert client.delete("/api/v1/communication/me/enrollment", headers=headers(user)).status_code == 204
    assert service.store.rows("enrollment", user["id"]) == []
    assert service.voice(user["id"]) is None and not list(service.spool.iterdir())


@pytest.mark.parametrize("path", ["/me", "/goals", "/grants"])
def test_api_rejects_non_object_json(system, path):
    _, client, user, _ = system
    method = "PATCH" if path == "/me" else "POST"
    response = client.open("/api/v1/communication"+path, method=method, json=["invalid"], headers=headers(user))
    assert response.status_code == 400
