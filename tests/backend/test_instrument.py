"""Synthetic fixtures exercise invariants; they are never displayed as research results."""
import io
import json
import sqlite3
import wave

import numpy as np
import pytest

from backend.instrument.app import create_app
from backend.instrument.audio import attribute, preprocess
from backend.instrument.features import extract, time_metrics
from backend.instrument.profiles import baseline, build_reference
from backend.instrument.research import queue_runs, process_run, evaluation, validate_output, annotate
from backend.instrument.service import Instrument
from backend.instrument.store import uid, now, encode


def recording(seconds=6, phase=0):
    samples = (np.sin(np.arange(16000*seconds)*.1+phase)*4000).astype(np.int16)
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, 16000, len(samples), "NONE", "NONE"))
        audio.writeframes(samples.tobytes())
    return output.getvalue()


class Diarizer:
    engine_name = "synthetic-test-diarizer"
    def __init__(self, config):
        pass
    def diarize(self, samples, rate):
        return [dict(speaker="SPEAKER_01", start=.1, end=2.8), dict(speaker="SPEAKER_02", start=3., end=5.9)]


class Transcriber:
    engine_name = "synthetic-test-transcriber"
    def __init__(self, config):
        pass
    def transcribe(self, samples, rate):
        return dict(segments=[dict(start=.2, end=2.5, text="We should test because evidence matters.", confidence=.95,
                                  words=[dict(start=.2, end=.5, text=" We", confidence=.95), dict(start=.5, end=.8, text=" should", confidence=.95),
                                         dict(start=.8, end=1.1, text=" test", confidence=.95), dict(start=1.1, end=1.4, text=" because", confidence=.95),
                                         dict(start=1.4, end=1.8, text=" evidence", confidence=.95), dict(start=1.8, end=2.5, text=" matters.", confidence=.95)]),
                              dict(start=3.1, end=5.5, text="I agree. Why?", confidence=.95,
                                   words=[dict(start=3.1, end=3.3, text=" I", confidence=.95), dict(start=3.3, end=4.1, text=" agree.", confidence=.95),
                                          dict(start=4.4, end=5.5, text=" Why?", confidence=.95)])])


@pytest.fixture
def service(tmp_path):
    return Instrument(tmp_path, Diarizer, Transcriber)


def add(service, day=1, phase=0, split="development"):
    session = service.ingest(io.BytesIO(recording(phase=phase)), "conversation.wav",
                            dict(recorded_at=f"2026-09-{day:02d}T10:00:00+00:00", consent="documented", context="meeting", split=split))
    service.process_next()
    return session["id"]


def person(service):
    row = dict(id=uid(), user_id="local", label="Test participant", created_at=now(), target_archetype="Builder")
    service.store.insert("profiles", row)
    return row["id"]


def test_pipeline_queryable_exports_and_failure_transparency(service):
    sid = add(service)
    detail = service.detail(sid)
    assert detail["session"]["status"] == "complete"
    assert len(detail["speakers"]) == 2
    assert len(detail["words"]) == 9
    assert all(s["status"] == "complete" for s in detail["stages"])
    assert detail["reports"][0]["baseline"]["status"] == "unavailable"
    assert len(detail["reports"][0]["archetypes"]) >= 3
    ids = {e["id"] for e in detail["evidence"]}
    assert all(set(t["evidence_ids"]) <= ids for r in detail["reports"] for t in r["traits"])
    assert all(f["value"] is None for f in detail["features"] if f["name"] == "topic_control")
    client = create_app(instrument=service, testing=True).test_client()
    for format in ("json", "csv", "rttm", "transcript", "zip"):
        response = client.get(f"/api/instrument/sessions/{sid}/export/{format}")
        assert response.status_code == 200
        assert response.data
    original = service.store.one("SELECT original_path FROM sessions WHERE id=?", (sid,))["original_path"]
    assert open(original, "rb").read() == recording()


def test_no_future_leakage_and_rebuild_after_mapping_and_delete(service):
    profile_id = person(service)
    sessions = []
    for day in (7, 1, 3, 2, 5, 4, 6):
        sid = add(service, day=day, phase=day/10)
        speaker = service.store.one("SELECT * FROM speakers WHERE session_id=? AND label='SPEAKER_01'", (sid,))
        service.map_speaker(speaker["id"], dict(profile_id=profile_id))
        sessions.append((day, sid, speaker))
    current = next(s for day, sid, s in sessions if day == 6)
    report = service.report(current["id"])
    assert report["baseline"]["sample_count"] == 5
    assert report["baseline"]["status"] == "available"
    assert report["target_archetype"] == "Builder"
    future_sid = next(sid for day, sid, s in sessions if day == 7)
    assert future_sid not in report["baseline"]["source_sessions"]
    service.delete(next(sid for day, sid, s in sessions if day == 1))
    assert service.report(current["id"])["baseline"]["sample_count"] == 4
    assert service.profile(profile_id)["recurring_traits"]


@pytest.mark.parametrize("payload", [b"", b"not audio", b"RIFFbroken"])
def test_empty_corrupted_audio(service, payload):
    if not payload:
        with pytest.raises(ValueError, match="empty"):
            service.ingest(io.BytesIO(payload), "x.wav", dict(recorded_at=now(), consent="documented"))
    else:
        sid = service.ingest(io.BytesIO(payload), "x.wav", dict(recorded_at=now(), consent="documented"))["id"]
        service.process_next()
        result = service.detail(sid)
        assert result["session"]["status"] == "failed"
        assert not result["features"] and not result["reports"]


def test_silence_duration_and_short_audio(tmp_path):
    silent = tmp_path/"silent.wav"
    with wave.open(str(silent), "wb") as audio:
        audio.setparams((1, 2, 16000, 32000, "NONE", "NONE"))
        audio.writeframes(bytes(64000))
    with pytest.raises(ValueError, match="silent"):
        preprocess(silent, tmp_path/"normalized.wav")
    long = tmp_path/"long.wav"
    long.write_bytes(recording())
    with pytest.raises(ValueError, match="duration"):
        preprocess(long, tmp_path/"n.wav", max_duration=2)
    short = tmp_path/"short.wav"
    with wave.open(str(short), "wb") as audio:
        audio.setparams((1, 2, 16000, 10, "NONE", "NONE"))
        audio.writeframes(bytes(20))
    with pytest.raises(ValueError, match="one second"):
        preprocess(short, tmp_path/"s.wav")


def test_overlap_not_assigned_or_called_interruption():
    transcript = dict(segments=[dict(start=1., end=2., text="Shared speech", confidence=.9,
                                    words=[dict(start=1., end=2., text="Shared speech", confidence=.9)])])
    rows = [dict(speaker="a", start=0., end=3.), dict(speaker="b", start=.5, end=4.)]
    speakers, turns, utterances, words = attribute("test", rows, transcript, 5., 12)
    assert utterances[0]["speaker_id"] is None
    speech, exclusive, overlaps = time_metrics(turns)
    assert sum(exclusive.values()) == 1.5
    assert all(overlaps[s["id"]] == 2.5 for s in speakers)
    with pytest.raises(ValueError, match="speaker limit"):
        attribute("test", rows, transcript, 5., 1)


def test_one_speaker_and_max_supported():
    transcript = dict(segments=[dict(start=.2, end=.9, text="Single speaker.", confidence=.9)])
    speakers, _, utterances, _ = attribute("test", [dict(speaker="a", start=0., end=1.)], transcript, 2., 12)
    assert len(speakers) == 1 and utterances[0]["speaker_id"]
    rows = [dict(speaker=str(i), start=float(i), end=i+.9) for i in range(12)]
    assert len(attribute("test", rows, transcript, 12., 12)[0]) == 12


def test_duplicate_session_and_mapping_guard(service):
    sid = add(service)
    with pytest.raises(ValueError, match="Duplicate"):
        service.ingest(io.BytesIO(recording()), "same.wav", dict(recorded_at=now(), consent="documented"))
    profile_id = person(service)
    speakers = service.detail(sid)["speakers"]
    service.map_speaker(speakers[0]["id"], dict(profile_id=profile_id))
    with pytest.raises(ValueError, match="one speaker"):
        service.map_speaker(speakers[1]["id"], dict(profile_id=profile_id))


def test_model_failure_and_retry(service):
    class Failed(Diarizer):
        def diarize(self, samples, rate):
            raise RuntimeError("synthetic model failure")
    service.diarizer_factory = Failed
    sid = add(service)
    assert service.detail(sid)["session"]["status"] == "failed"
    assert not service.detail(sid)["reports"]
    service.diarizer_factory = Diarizer
    service.retry(sid)
    service.process_next()
    assert service.detail(sid)["session"]["status"] == "complete"


def test_missing_and_low_confidence_transcription(service):
    class Low(Transcriber):
        def transcribe(self, samples, rate):
            output = super().transcribe(samples, rate)
            for s in output["segments"]:
                for w in s["words"]:
                    w["confidence"] = .1
            return output
    service.transcriber_factory = Low
    sid = add(service)
    detail = service.detail(sid)
    assert detail["utterances"] and not detail["reports"] and not detail["features"]
    class Empty(Transcriber):
        def transcribe(self, samples, rate):
            return dict(segments=[])
    service.transcriber_factory = Empty
    sid = add(service, phase=.1)
    assert service.detail(sid)["session"]["status"] == "failed"


def test_worker_lease_recovery(service):
    row = service.ingest(io.BytesIO(recording()), "x.wav", dict(recorded_at=now(), consent="documented"))
    assert service.store.claim("worker-a") == row["id"]
    assert service.store.claim("worker-b") is None
    service.store.execute("UPDATE sessions SET lease_until=0 WHERE id=?", (row["id"],))
    assert service.store.claim("worker-b") == row["id"]


def test_corpus_reference_and_participant_leakage(service):
    refs = []
    for day in range(1, 4):
        sid = add(service, day=day, phase=day/10, split="reference")
        refs.append(service.detail(sid)["speakers"][0]["id"])
    ref = build_reference(service.store, "Group-derived proposal profile", refs, "Synthetic corpus for tests")
    assert ref["sample_count"] == 3
    assert "exploratory" in ref["status"]
    assert service.report(refs[0])["archetypes"][0]["status"] == "excluded_reference_leakage"
    with pytest.raises(ValueError, match="three"):
        build_reference(service.store, "Too small", refs[:1], "test")


class Provider:
    model = "test-model"
    def digest(self):
        return "synthetic-digest"
    def generate(self, packet, digest):
        speaker = packet["target_speaker_id"]
        own = next(u for u in packet["transcript"] if u["speaker_id"] == speaker)
        return dict(summary="Test report", limitations=["Synthetic test"], claims=[dict(speaker_id=speaker,
                    observation="A proposal marker occurs.", inference="Limited proposal indicator.", evidence_ids=[own["id"]],
                    confidence="low", limitation="Synthetic, not research.", suggestion="Review context.")])


def test_matched_runs_blind_annotations_and_metrics(service):
    sid = add(service)
    speaker_id = service.detail(sid)["speakers"][0]["id"]
    runs = queue_runs(service, speaker_id, provider=Provider())
    inputs = [json.loads(service.store.one("SELECT input FROM llm_runs WHERE id=?", (r["id"],))["input"]) for r in runs]
    assert all(p["transcript"] == inputs[0]["transcript"] for p in inputs)
    assert "session_features" not in inputs[0] and "personal_baseline" not in inputs[1]
    assert "personal_baseline" in inputs[2]
    for _ in runs:
        assert process_run(service, Provider())["status"] == "complete"
    assert all(r["status"] == "Not evaluated yet" for r in evaluation(service.store)["systems"])
    blind_id = runs[0]["blind_id"]
    client = create_app(instrument=service, testing=True).test_client()
    blinded = client.get("/api/instrument/review/"+blind_id).get_json()
    assert "condition" not in blinded and "input" not in blinded and "model" not in blinded
    assert blinded["sources"][0]["text"]
    assert set(blinded["sources"][0]) == {"id", "speaker_id", "start", "end", "text"}
    assert blinded["sources"][0]["id"] in blinded["report"]["claims"][0]["evidence_ids"]
    from backend.instrument.research import CRITERIA
    annotate(service.store, blind_id, dict(reviewer_id="r1", claim_index=0, **{c: 3 for c in CRITERIA}))
    result = evaluation(service.store)
    assert result["systems"][0]["metrics"]["grounding"] == 3
    assert result["systems"][1]["metrics"]["grounding"] is None
    assert result["systems"][0]["unsupported_claim_proportion"] == 0


def test_llm_failure_never_becomes_report(service):
    class Bad(Provider):
        def generate(self, packet, digest):
            out = super().generate(packet, digest)
            out["claims"][0]["evidence_ids"] = ["invented-evidence"]
            return out
    sid = add(service)
    speaker_id = service.detail(sid)["speakers"][0]["id"]
    queue_runs(service, speaker_id, ["C"], Bad())
    assert process_run(service, Bad())["status"] == "failed"


def test_same_origin_and_database_failure(service, monkeypatch):
    client = create_app(instrument=service, testing=True).test_client()
    assert client.post("/api/instrument/profiles", json=dict(label="p")).status_code == 403
    assert client.post("/api/instrument/profiles", json=dict(label="p"), headers={"X-PSYCON-Request": "research-instrument", "Origin": "http://evil.example"}).status_code == 403
    def failure(*args):
        raise sqlite3.OperationalError("test database failure")
    monkeypatch.setattr(service.store, "rows", failure)
    response = client.get("/api/instrument/state")
    assert response.status_code == 503 and "fabricated" in response.get_json()["error"]


def test_reviewed_behavior_has_direction_evidence_and_partial_coverage(service):
    from backend.instrument.annotations import annotate_behavior
    sid = add(service)
    detail = service.detail(sid)
    e = next(e for e in detail["evidence"] if e["feature"] == "utterance")
    target = next(s["id"] for s in detail["speakers"] if s["id"] != e["speaker_id"])
    with pytest.raises(ValueError, match="interrupted speaker"):
        annotate_behavior(service, e["id"], dict(kind="interruption", reviewer_id="r1"))
    result = annotate_behavior(service, e["id"], dict(kind="interruption", reviewer_id="r1", target_speaker_id=target,
                                                     topic="Planning", phase="disagreement", notes="Reviewed synthetic event"))
    assert result["distinct_events"] == 1
    annotate_behavior(service, e["id"], dict(kind="interruption", reviewer_id="r2", target_speaker_id=target))
    report = service.report(e["speaker_id"])
    feature = next(f for f in report["features"] if f["name"] == "reviewed_interruption_rate")
    assert feature["status"] == "reviewed_partial" and feature["value"] == 100
    trait = next(t for t in report["traits"] if t["feature"] == "reviewed_interruption_rate")
    assert trait["evidence_ids"] == [e["id"]]
    assert len(service.store.rows("SELECT * FROM interactions WHERE kind='reviewed_interruption'")) == 1


def test_metadata_edits_rebuild_baseline_and_reference_delete_removes_dependents(service):
    refs = []
    sessions = []
    for day in range(1, 4):
        sid = add(service, day=day, phase=day/10, split="reference")
        sessions.append(sid)
        refs.append(service.detail(sid)["speakers"][0]["id"])
    ref = build_reference(service.store, "A reference", refs, "Test corpus")
    with pytest.raises(ValueError, match="reference profile"):
        service.edit_metadata(sessions[0], dict(split="development"))
    service.delete(sessions[0])
    assert not service.store.rows("SELECT id FROM archetypes WHERE id=?", (ref["id"],))
    sid = add(service, day=8, phase=.8)
    updated = service.edit_metadata(sid, dict(recorded_at="2026-09-07T15:30:00+05:30", context="interview", participant_ids=["P1"]))
    assert updated["recorded_at"].startswith("2026-09-07T10:00:00") and updated["context"] == "interview"
    assert all(e["context"]["session_context"] == "interview" for e in service.detail(sid)["evidence"])


def test_interpretation_invalidation_and_goal_change(service):
    sid = add(service)
    p = person(service)
    speaker = service.detail(sid)["speakers"][0]
    service.map_speaker(speaker["id"], dict(profile_id=p))
    runs = queue_runs(service, speaker["id"], provider=Provider())
    service.store.invalidate()
    assert service.store.one("SELECT status FROM llm_runs WHERE id=?", (runs[2]["id"],))["status"] == "stale"
    client = create_app(instrument=service, testing=True).test_client()
    response = client.patch("/api/instrument/profiles/"+p, json=dict(target_archetype="Negotiator"), headers={"X-PSYCON-Request":"research-instrument"})
    assert response.status_code == 200
    assert all(r["status"] == "stale" for r in service.store.rows("SELECT status FROM llm_runs"))


def test_worker_exclusive_lock_and_missing_references(service):
    from backend.instrument.worker import lock
    with lock(service.store.root):
        with pytest.raises(RuntimeError, match="already running"):
            with lock(service.store.root):
                pass
    sid = add(service)
    service.store.execute("DELETE FROM archetypes")
    assert service.detail(sid)["reports"][0]["archetype_status"] == "missing_reference_data"


def test_workspace_goal_controls_anonymous_reports_and_matched_inputs(service):
    sid = add(service)
    speaker = service.detail(sid)["speakers"][0]
    client = create_app(instrument=service, testing=True).test_client()
    headers = {"X-PSYCON-Request": "research-instrument"}
    response = client.patch("/api/instrument/settings", json={"target_archetype": "Salesperson"}, headers=headers)
    assert response.status_code == 200
    assert client.get("/api/instrument/state").json["target_archetype"] == "Salesperson"
    assert service.report(speaker["id"])["target_archetype"] == "Salesperson"
    runs = queue_runs(service, speaker["id"], provider=Provider())
    for run in runs:
        packet = json.loads(service.store.one("SELECT input FROM llm_runs WHERE id=?", (run["id"],))["input"])
        assert packet["user_selected_goal"] == "Salesperson"
    client.patch("/api/instrument/settings", json={"target_archetype": "Negotiator"}, headers=headers)
    assert all(r["status"] == "stale" for r in service.store.rows("SELECT status FROM llm_runs"))
    assert client.patch("/api/instrument/settings", json={"target_archetype": "Unknown"}, headers=headers).status_code == 400


def test_clipping_withholds_analysis_and_noise_diagnostics(service, tmp_path):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        values = np.where(np.arange(96000) % 2, 32767, -32768).astype(np.int16)
        audio.setparams((1,2,16000,len(values),"NONE","NONE"))
        audio.writeframes(values.tobytes())
    row = service.ingest(io.BytesIO(output.getvalue()), "clipped.wav", dict(recorded_at=now(),consent="documented"))
    service.process_next()
    assert not service.detail(row["id"])["reports"]
    assert "quality" in service.detail(row["id"])["session"]["error"]
    path = tmp_path/"noise.wav"
    with wave.open(str(path),"wb") as audio:
        values = np.random.default_rng(4).integers(-4000,4000,32000,dtype=np.int16)
        audio.setparams((1,2,16000,len(values),"NONE","NONE"))
        audio.writeframes(values.tobytes())
    diagnostics = preprocess(path,tmp_path/"normalized-noise.wav").diagnostics
    assert diagnostics["denoising"] == "disabled" and diagnostics["snr_status"].startswith("estimated")


def test_actual_media_container_audio_extraction(tmp_path):
    import av
    for suffix, container_format in ((".mp3","mp3"),(".m4a","mp4"),(".mp4","mp4"),(".mov","mov")):
        path = tmp_path/("source"+suffix)
        with av.open(str(path),"w",format=container_format) as container:
            stream = container.add_stream("mp3" if suffix==".mp3" else "aac",rate=16000)
            stream.layout="mono"
            values = (np.sin(np.arange(32000)*.1)*.15).astype(np.float32)[None,:]
            frame = av.AudioFrame.from_ndarray(values,format="fltp",layout="mono")
            frame.sample_rate=16000
            for packet in stream.encode(frame):
                container.mux(packet)
            for packet in stream.encode(None):
                container.mux(packet)
        result = preprocess(path,tmp_path/(suffix[1:]+"-normalized.wav"))
        assert result.diagnostics["sample_rate"] == 16000 and result.diagnostics["duration"] >= 1.9
