"""Import retained group-discussion observations without treating A–T scores as role labels."""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from .audio import preprocess
from .features import extract
from .profiles import build_reference, vector, ROLE_FRAMEWORKS
from .store import decode, encode, uid


def import_group(instrument, directory, source_video, recorded_at, consent):
    directory = Path(directory).resolve()
    detail_path = directory/"psycon-recovered-detail.json"
    if not detail_path.exists():
        detail_path = directory/"psycon-detail.json"
    payload = decode(detail_path.read_text(encoding="utf-8"))
    if payload.get("summary", {}).get("status") != "complete":
        raise ValueError("Only completed saved group analysis can be imported")
    shared = directory/"shared-16khz.wav"
    ready = [p for p in payload["profiles"] if p["status"] == "ready" and
             p.get("metrics", {}).get("transcription", {}).get("status") == "complete"]
    if not ready:
        raise ValueError("Saved analysis has no usable attributed transcript profiles")
    with shared.open("rb") as stream:
        session = instrument.ingest(stream, Path(source_video).stem+".wav", dict(recorded_at=recorded_at,
                                    consent=consent, split="reference", dataset="Existing group discussion analysis",
                                    context="group discussion", participant_ids=[], topic="Original group discussion; topic not annotated",
                                    conditions="Imported guarded intervals and partial word transcripts; anonymous source slots are recording-specific"), allow_unknown_consent=True)
    sid = session["id"]
    instrument.store.execute("UPDATE jobs SET status='canceled',finished_at=now(),error='Explicit one-time retained-corpus import' WHERE subject_id=%s AND kind='speech' AND status='queued'",(sid,))
    source_path = Path(instrument.store.one("SELECT original_path FROM sessions WHERE id=%s", (sid,))["original_path"])
    try:
        audio = preprocess(source_path, source_path.parent/"normalized.wav")
        instrument.store.execute("UPDATE sessions SET duration=%s,sample_rate=%s,channels=%s,status='processing' WHERE id=%s",
                                 (audio.diagnostics["duration"], 16000, 1, sid))
        session = instrument.store.session(sid)
        speakers, turns, utterances, words = [], [], [], []
        for profile in ready:
            slot = profile["slot_number"]
            speaker = dict(id=uid(), session_id=sid, label=f"GROUP_SLOT_{slot:02d}", display_name=f"Participant {slot}", profile_id=None)
            speakers.append(speaker)
            own_rows = [r for r in payload["rows"] if r.get("slot_number") == slot and r.get("status") == "assigned" and not r.get("overlap_refused_s")]
            for row in own_rows:
                if not 0 <= row["start_s"] < row["end_s"] <= session["duration"]+.1:
                    raise ValueError("Saved corpus contains invalid interval timestamps")
                turns.append(dict(id=uid(), session_id=sid, speaker_id=speaker["id"], start=row["start_s"], end=row["end_s"], confidence=None))
            source_words = profile["metrics"]["transcription"].get("words", [])
            for turn in [t for t in turns if t["speaker_id"] == speaker["id"]]:
                own_words = [w for w in source_words if turn["start"]-.01 <= w["start_s"] and w["end_s"] <= turn["end"]+.01]
                groups, group = [], []
                for w in own_words:
                    if group and (w["start_s"]-group[-1]["end_s"] > 1 or group[-1]["text"].endswith((".", "?", "!"))):
                        groups.append(group)
                        group = []
                    group.append(w)
                if group:
                    groups.append(group)
                for group in groups:
                    key = uid()
                    utterances.append(dict(id=key, session_id=sid, speaker_id=speaker["id"], turn_id=turn["id"],
                                           start=group[0]["start_s"], end=group[-1]["end_s"], text=" ".join(w["text"].strip() for w in group),
                                           confidence=None, attribution="imported_guarded_partial"))
                    words.extend(dict(id=uid(), utterance_id=key, start=w["start_s"], end=w["end_s"], text=w["text"], confidence=None) for w in group)
        turns.sort(key=lambda t: t["start"])
        features, evidence, interactions = extract(session, speakers, turns, utterances)
        for f in features:
            if f["name"] in ("overlap_time", "interruption_candidate_rate"):
                f.update(value=None, status="unavailable", source="Saved guarded intervals excluded overlap; complete diarization not imported")
            else:
                f["source"] += "; imported partial guarded corpus"
                f["confidence"] = "low"
        provenance = dict(source="existing guarded group discussion analysis", artifact=detail_path.name,
                          artifact_sha256=hashlib.sha256(detail_path.read_bytes()).hexdigest(),
                          original_video=Path(source_video).name, source_diarization="pyannote Community-1",
                          source_transcription=sorted({p["metrics"]["transcription"].get("engine", "unknown") for p in ready}),
                          validation="Model-supported assignments; independently unvalidated", transcript="Partial retained attributed speech only",
                          confidence="Source word confidence not stored; remains null")
        with instrument.store.connect() as db:
            from .assets import register
            original=register(instrument.store,source_video,'media',root=Path(source_video).resolve().parent,db=db)
            db.execute('INSERT INTO session_assets VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(sid,original['id'],'original group discussion video'))
            for table, rows in (("speakers", speakers), ("turns", turns), ("utterances", utterances), ("words", words),
                                ("features", features), ("evidence", evidence), ("interactions", interactions)):
                for row in rows:
                    instrument.store.insert(table, row, db)
            db.execute("UPDATE sessions SET status='complete',versions=%s,worker_id=NULL,lease_until=NULL WHERE id=%s", (encode(provenance), sid))
        for stage in ("diarization", "transcription", "attribution", "segmentation", "features", "evidence", "profile"):
            instrument.store.stage(sid, stage, "complete", dict(imported=True, provenance=provenance,
                                   warning="Existing guarded partial observations, not a new full recording pipeline run"))
        instrument.store.stage(sid, "preprocessing", "complete", audio.diagnostics)
        from .profiles import generate_traits
        for speaker in speakers:
            generate_traits(instrument.store, session, speaker, [f for f in features if f["speaker_id"] == speaker["id"]],
                            [e for e in evidence if e["speaker_id"] == speaker["id"]])
    except Exception as exc:
        instrument.store.execute("UPDATE sessions SET status='failed',error=%s WHERE id=%s", (str(exc)[:1000], sid))
        raise
    return instrument.store.session(sid)


def build_group_lenses(instrument):
    """Corpus centers come from observable behavioral subsets, not inferred occupations."""
    store = instrument.store
    candidates = store.rows("SELECT p.* FROM speakers p JOIN sessions s ON s.id=p.session_id WHERE s.split='reference' AND s.status='complete' "
                            "AND s.dataset='Existing group discussion analysis'")
    by_session = {}
    for speaker in candidates:
        features = vector(store.rows("SELECT * FROM features WHERE speaker_id=%s", (speaker["id"],)))
        by_session.setdefault(speaker["session_id"], []).append((speaker, features))
    if len(by_session) < 3:
        raise ValueError("At least three independent reference recordings are required")
    result = []
    for name, framework in ROLE_FRAMEWORKS.items():
        chosen = []
        for speakers in by_session.values():
            scores = []
            for speaker, features in speakers:
                common = features.keys() & framework.keys()
                if len(common) >= 3:
                    distance = statistics.mean((features[k]-framework[k])**2 for k in common)
                    scores.append((distance, speaker["id"]))
            if scores:
                chosen.append(min(scores)[1])
        if len(chosen) < 3:
            continue
        archetype = build_reference(store, name+" · group-derived lens", chosen,
                                   "Group discussion corpus; select one closest speaker per recording to project-defined role framework using mean squared distance on shared dimensions. These are behavioral subsets, not occupational labels.")
        result.append(archetype)
    if not result:
        raise ValueError("Reference corpus has insufficient comparable dimensions")
    return result
