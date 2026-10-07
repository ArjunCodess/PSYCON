"""Durable audio processing and inspectable communication reports."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
from uuid import uuid4

import numpy as np

from .audio import PyannoteAdapter, WhisperAdapter, attribute, preprocess, model_versions
from .features import DICTIONARY, UNAVAILABLE, extract
from .profiles import baseline, compare_archetypes, generate_traits, initialize_archetypes, TRAIT_FEATURES
from .store import Store, encode, uid, now
from . import annotations  # Registers reviewed-event feature definitions.

STAGES = ("preprocessing", "diarization", "transcription", "attribution", "segmentation", "features", "evidence", "profile")
SUPPORTED = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".ogg"}


def configuration():
    device = os.getenv("PSYCON_INSTRUMENT_DEVICE", "auto")
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    model = os.getenv("PSYCON_INSTRUMENT_WHISPER_MODEL", "large-v3")
    return dict(diarization_model=os.getenv("PSYCON_INSTRUMENT_DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1"),
                diarization_revision=os.getenv("PSYCON_COMMUNITY1_REVISION", "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"),
                transcription_model=model,
                transcription_revision=os.getenv("PSYCON_INSTRUMENT_WHISPER_REVISION", "edaa852ec7e145841d8ffdb056a99866b5f0a478" if model == "large-v3" else "") or None,
                device=device, max_speakers=12, max_duration_seconds=14400,
                min_transcript_confidence=.55, min_attribution_fraction=.6,
                max_upload_bytes=512*1024*1024, denoising=False, language="en")


class Instrument:
    def __init__(self, root, diarizer_factory=PyannoteAdapter, transcriber_factory=WhisperAdapter):
        self.store = Store(root)
        self.diarizer_factory = diarizer_factory
        self.transcriber_factory = transcriber_factory
        initialize_archetypes(self.store)

    def ingest(self, stream, filename, metadata, *, allow_unknown_consent=False):
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise ValueError("Upload MP3, WAV, M4A, MP4, MOV, or OGG audio")
        stamp = metadata.get("recorded_at")
        if not stamp:
            raise ValueError("Recording date/time is required for chronological baselines")
        try:
            date = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("Recording time must include a timezone")
            stamp = date.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("Use an ISO recording date/time including timezone") from exc
        split = metadata.get("split", "development")
        if split not in ("development", "validation", "evaluation", "reference"):
            raise ValueError("Invalid dataset split")
        consent = metadata.get("consent", "not documented")
        if consent not in ("documented", "public licensed", "self recording") and not allow_unknown_consent:
            raise ValueError("Document recording consent or the public license before processing")
        participants = metadata.get("participant_ids", [])
        if not isinstance(participants, list) or any(not isinstance(p, str) for p in participants):
            raise ValueError("Participant IDs must be an array of anonymous identifiers")
        for existing in self.store.rows("SELECT participant_ids,split FROM sessions"):
            if ((split == "reference") != (existing["split"] == "reference")) and set(participants) & set(json.loads(existing["participant_ids"])):
                raise ValueError("Reference and analysis participants must be disjoint")
        key = uid()
        folder = self.store.root / "media" / key
        folder.mkdir(parents=True)
        original = folder / ("original"+suffix)
        config = configuration()
        sha, size = hashlib.sha256(), 0
        try:
            with original.open("xb") as target:
                while chunk := stream.read(1024*1024):
                    size += len(chunk)
                    if size > config["max_upload_bytes"]:
                        raise ValueError("Maximum upload size is 512 MiB per recording")
                    sha.update(chunk)
                    target.write(chunk)
            if not size:
                raise ValueError("The uploaded file is empty")
            if self.store.rows("SELECT id FROM sessions WHERE sha256=?", (sha.hexdigest(),)):
                raise ValueError("Duplicate recording: the original session is already stored")
            self.store.insert("sessions", dict(id=key, filename=filename[:512], sha256=sha.hexdigest(), original_path=str(original),
                              recorded_at=stamp, created_at=now(), context=str(metadata.get("context", "meeting"))[:100],
                              topic=str(metadata.get("topic", ""))[:500], dataset=str(metadata.get("dataset", "personal uploads"))[:200],
                              split=split, consent=consent, conditions=str(metadata.get("conditions", "not supplied"))[:1000],
                              participant_ids=encode(participants), status="queued", config=encode(config), versions=encode(model_versions(config))))
            for stage in STAGES:
                self.store.stage(key, stage, "pending")
        except Exception:
            shutil.rmtree(folder)
            raise
        return self.store.session(key)

    def retry(self, session_id):
        session = self.store.session(session_id)
        if session["status"] not in ("failed", "blocked"):
            raise ValueError("Only failed or blocked sessions can be retried")
        self.store.execute("UPDATE sessions SET status='queued', error=NULL, lease_until=NULL,worker_id=NULL WHERE id=?", (session_id,))

    def edit_metadata(self, session_id, body):
        session = self.store.session(session_id)
        if session["status"] == "processing":
            raise ValueError("Wait for processing to finish before changing session metadata")
        values = {k: str(body.get(k, session[k])).strip() for k in ("context", "topic", "conditions", "dataset", "consent")}
        if not values["context"] or not values["dataset"]:
            raise ValueError("Conversation context and dataset name are required")
        stamp = body.get("recorded_at", session["recorded_at"])
        try:
            recorded = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if recorded.tzinfo is None:
                raise ValueError("timezone missing")
            stamp = recorded.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Recording date/time requires an ISO timestamp and timezone") from exc
        participants = body.get("participant_ids", session["participant_ids"])
        if not isinstance(participants, list) or any(not isinstance(p, str) for p in participants):
            raise ValueError("Participant IDs must be an array of strings")
        split = body.get("split", session["split"])
        if split not in ("development", "validation", "evaluation", "reference"):
            raise ValueError("Invalid dataset split")
        others = self.store.rows("SELECT participant_ids,split FROM sessions WHERE id!=?", (session_id,))
        if any((split == "reference") != (r["split"] == "reference") and set(participants) & set(json.loads(r["participant_ids"])) for r in others):
            raise ValueError("Reference and analysis participants must be disjoint")
        source = self.store.rows("SELECT af.distribution FROM archetype_features af WHERE af.distribution IS NOT NULL")
        if split != "reference" and any(session_id in {s["session_id"] for s in json.loads(r["distribution"])["sources"]} for r in source):
            raise ValueError("This session is used by a reference profile; keep its reference split or remove the dependent reference first")
        linked = self.store.rows("SELECT s.split FROM sessions s JOIN speakers p ON p.session_id=s.id WHERE s.id!=? "
                                 "AND p.profile_id IN (SELECT profile_id FROM speakers WHERE session_id=? AND profile_id IS NOT NULL)", (session_id, session_id))
        if any((r["split"] == "reference") != (split == "reference") for r in linked):
            raise ValueError("Known personal identities cannot cross reference and analysis splits")
        if values["consent"] not in ("documented", "public licensed", "self recording", "not documented"):
            raise ValueError("Invalid consent status")
        with self.store.connect() as db:
            db.execute("UPDATE sessions SET recorded_at=?,context=?,topic=?,conditions=?,dataset=?,consent=?,split=?,participant_ids=? WHERE id=?",
                       (stamp, *(values[k] for k in ("context", "topic", "conditions", "dataset", "consent")), split, encode(participants), session_id))
            for row in db.execute("SELECT id,context FROM evidence WHERE session_id=?", (session_id,)).fetchall():
                context = json.loads(row["context"])
                context.update(session_context=values["context"])
                if not context.get("annotation_reviewer"):
                    context["topic"] = values["topic"] or "not annotated"
                db.execute("UPDATE evidence SET context=? WHERE id=?", (encode(context), row["id"]))
            db.execute("UPDATE llm_runs SET status='stale',error='Session metadata changed; queue a new run' WHERE session_id=? AND status IN ('complete','queued','running')", (session_id,))
        self.store.invalidate()
        return self.store.session(session_id)

    def process_next(self):
        worker_id = str(uuid4())
        session_id = self.store.claim(worker_id)
        if session_id is None:
            return None
        finished = threading.Event()
        def heartbeat():
            while not finished.wait(20):
                self.store.heartbeat(session_id, worker_id)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        stage = "preprocessing"
        try:
            session = self.store.session(session_id)
            config = session["config"]
            original = Path(self.store.one("SELECT original_path FROM sessions WHERE id=?", (session_id,))["original_path"])
            self.store.stage(session_id, stage, "running")
            audio = preprocess(original, original.parent/"normalized.wav", config["max_duration_seconds"])
            self.store.stage(session_id, stage, "complete", audio.diagnostics)
            self.store.execute("UPDATE sessions SET duration=?,sample_rate=?,channels=? WHERE id=?",
                               (audio.diagnostics["duration"], audio.diagnostics["original_sample_rate"], audio.diagnostics["original_channels"], session_id))
            session = self.store.session(session_id)
            def model_stage(name, action):
                old = self.store.one("SELECT * FROM stages WHERE session_id=? AND name=?", (session_id, name))
                if old["status"] == "complete" and old["output"]:
                    return json.loads(old["output"])
                self.store.stage(session_id, name, "running")
                result = action()
                self.store.stage(session_id, name, "complete", result)
                return result
            stage = "diarization"
            raw_turns = model_stage(stage, lambda: self.diarizer_factory(config).diarize(audio.samples, 16000))
            stage = "transcription"
            transcript = model_stage(stage, lambda: self.transcriber_factory(config).transcribe(audio.samples, 16000))
            stage = "attribution"
            self.store.stage(session_id, stage, "running")
            speakers, turns, utterances, words = attribute(session_id, raw_turns, transcript, session["duration"], config["max_speakers"])
            # Keep reviewed mappings and identifiers on retry.
            old = {s["label"]: s for s in self.store.rows("SELECT * FROM speakers WHERE session_id=?", (session_id,))}
            for speaker in speakers:
                if speaker["label"] in old:
                    previous = old[speaker["label"]]
                    new_id = speaker["id"]
                    speaker.update(id=previous["id"], display_name=previous["display_name"], profile_id=previous["profile_id"])
                    for row in (*turns, *utterances):
                        if row["speaker_id"] == new_id:
                            row["speaker_id"] = speaker["id"]
            attributed = sum(len(u["text"].split()) for u in utterances if u["speaker_id"])
            total = sum(len(u["text"].split()) for u in utterances)
            fraction = attributed/max(total, 1)
            confidence = sum(u["confidence"] for u in utterances)/len(utterances)
            with self.store.connect() as db:
                db.execute("DELETE FROM speakers WHERE session_id=?", (session_id,))
                for table, rows in (("speakers", speakers), ("turns", turns), ("utterances", utterances), ("words", words)):
                    for row in rows:
                        self.store.insert(table, row, db)
            self.store.stage(session_id, stage, "complete", dict(attributed_word_fraction=fraction, mean_transcript_confidence=confidence,
                                                                confidence_note="Model confidence is an estimate, not calibrated accuracy",
                                                                ambiguous_utterances=sum(u["speaker_id"] is None for u in utterances)))
            if fraction < config["min_attribution_fraction"]:
                raise ValueError("Speaker attribution could not be reliably completed. Transcript retained; communication profile withheld.")
            if confidence < config["min_transcript_confidence"] or audio.diagnostics["quality"] == "poor":
                raise ValueError("Analysis confidence reduced because transcription or signal quality is below threshold. Transcript retained; profile withheld.")
            stage = "segmentation"
            self.store.stage(session_id, stage, "complete", dict(turns=len(turns), utterances=len(utterances),
                             method="speaker changes, sentence punctuation, and >1s gaps; adjacent exchanges retained",
                             topic=session["topic"] or "not annotated", topic_boundaries="not validated", phases="not annotated"))
            stage = "features"
            self.store.stage(session_id, stage, "running")
            features, evidence, interactions = extract(session, speakers, turns, utterances)
            with self.store.connect() as db:
                for table, rows in (("features", features), ("evidence", evidence), ("interactions", interactions)):
                    for row in rows:
                        self.store.insert(table, row, db)
            self.store.stage(session_id, stage, "complete", dict(count=len(features), dictionary=DICTIONARY, unavailable=UNAVAILABLE))
            stage = "evidence"
            self.store.stage(session_id, stage, "complete", dict(count=len(evidence), interactions=len(interactions),
                                                               lineage="session → speaker → turn/utterance → feature event → trait"))
            stage = "profile"
            for speaker in speakers:
                generate_traits(self.store, session, speaker, [f for f in features if f["speaker_id"] == speaker["id"]],
                                [e for e in evidence if e["speaker_id"] == speaker["id"]])
            self.store.stage(session_id, stage, "complete", dict(status="observable indicators ready",
                                                               interpretation="Request evidence-grounded LLM analysis per speaker",
                                                               validation="not independently validated"))
            self.store.execute("UPDATE sessions SET status='complete',lease_until=NULL,worker_id=NULL WHERE id=?", (session_id,))
        except Exception as exc:
            # Never convert model/runtime failure into plausible fabricated features.
            message = str(exc)[:1500]
            self.store.stage(session_id, stage, "failed", error=message)
            self.store.execute("UPDATE sessions SET status='failed',error=?,lease_until=NULL,worker_id=NULL WHERE id=?", (message, session_id))
        finally:
            finished.set()
            thread.join(timeout=1)
        return self.store.session(session_id)

    def detail(self, session_id):
        session = self.store.session(session_id)
        stages = self.store.rows("SELECT * FROM stages WHERE session_id=?", (session_id,))
        stages.sort(key=lambda row: STAGES.index(row["name"]) if row["name"] in STAGES else len(STAGES))
        for row in stages:
            row["output"] = json.loads(row["output"]) if row["output"] else None
        result = dict(session=session, stages=stages)
        for table in ("speakers", "turns", "utterances", "features", "evidence", "interactions"):
            result[table] = self.store.rows(f"SELECT * FROM {table} WHERE session_id=?", (session_id,))
        for row in result["evidence"]:
            row["context"] = json.loads(row["context"])
        result["words"] = self.store.rows("SELECT w.* FROM words w JOIN utterances u ON u.id=w.utterance_id WHERE u.session_id=? ORDER BY w.start", (session_id,))
        result["reports"] = [self.report(s["id"]) for s in result["speakers"]] if session["status"] == "complete" else []
        return result

    def report(self, speaker_id):
        speaker = self.store.one("SELECT * FROM speakers WHERE id=?", (speaker_id,))
        session = self.store.session(speaker["session_id"])
        if session["status"] != "complete":
            raise ValueError("Analysis unavailable while processing is incomplete or failed")
        features = self.store.rows("SELECT * FROM features WHERE speaker_id=?", (speaker_id,))
        traits = self.store.rows("SELECT s.*,t.name,t.feature FROM session_traits s JOIN traits t ON t.id=s.trait_id WHERE s.speaker_id=?", (speaker_id,))
        for trait in traits:
            trait["evidence_ids"] = [r["evidence_id"] for r in self.store.rows("SELECT evidence_id FROM trait_evidence WHERE session_trait_id=?", (trait["id"],))]
        comparisons = compare_archetypes(self.store, session, speaker, features)
        with self.store.connect() as db:
            db.execute("DELETE FROM comparisons WHERE speaker_id=?", (speaker_id,))
            for result in comparisons:
                self.store.insert("comparisons", dict(id=uid(), session_id=session["id"], speaker_id=speaker_id,
                             archetype_id=result["archetype"]["id"], similarity=result["similarity"], method=result["method"],
                             dimensions=encode(result["dimensions"]), status=result["status"]), db)
        personal = baseline(self.store, session, speaker)
        changes = [dict(feature=k, **v) for k, v in personal["statistics"].items() if v["substantial_descriptive_deviation"]]
        evidence = self.store.rows("SELECT * FROM evidence WHERE speaker_id=?", (speaker_id,))
        suggestions = {
            "interruption_candidate_rate": "If the overlap was an unwanted interruption, let the other speaker finish before offering the counterargument. Review the audio first; overlap does not establish intent.",
            "question_ratio": "If your goal is to invite more perspectives, ask an open clarification question before the next proposal.",
            "question_rate": "If your goal is to invite more perspectives, ask an open clarification question before the next proposal.",
            "acknowledgement_ratio": "If useful in this setting, explicitly acknowledge the preceding point before presenting an alternative.",
            "proposal_rate": "If proposals are crowding discussion, pause for a response before introducing the next alternative.",
            "hedging_ratio": "When presenting a proposal, distinguish what you know from what remains uncertain, rather than changing hedging without regard to evidence.",
        }
        coaching = []
        for r in changes:
            kind = TRAIT_FEATURES.get(r["feature"], ("", "utterance"))[1]
            refs = [e["id"] for e in evidence if e["feature"] == kind]
            if refs:
                coaching.append(dict(feature=r["feature"], observation=f"Current {r['current']:.3g}; historical median {r['median']:.3g} across {r['sample_count']} earlier sessions. Deviation is not inherently good or bad.",
                                     suggestion=suggestions.get(r["feature"], "Review the conversational examples and choose a specific adjustment appropriate to this setting."),
                                     confidence=r["confidence"], evidence_ids=refs))
        target = self.store.one("SELECT target_archetype FROM profiles WHERE id=?", (speaker["profile_id"],))["target_archetype"] if speaker["profile_id"] else self.store.one("SELECT value FROM workspace_settings WHERE name='target_archetype'")["value"]
        archetype_coaching = []
        for comparison in comparisons:
            if comparison["status"] != "available" or not comparison["archetype"]["name"].startswith(target):
                continue
            for d in sorted(comparison["dimensions"], key=lambda d: d["delta"])[:2]:
                if d["delta"] >= 0:
                    continue
                from .profiles import DIMENSIONS
                feature = DIMENSIONS[d["name"]][0]
                kind = TRAIT_FEATURES.get(feature, ("", "utterance"))[1]
                refs = [e["id"] for e in evidence if e["feature"] == kind]
                if refs:
                    archetype_coaching.append(dict(dimension=d["name"], person=d["person"], reference=d["reference"],
                                 observation=f"Your {d['name'].replace('_', ' ')} dimension is below the exploratory {target} reference in the selected feature space.",
                                 suggestion=suggestions.get(feature, "Practice stating one proposal and its supporting reason, then invite a response. Treat this as a goal-specific experiment, not a personality change."),
                                 confidence="low", evidence_ids=refs, reference_id=comparison["archetype"]["id"]))
        return dict(speaker=speaker, session_id=session["id"], features=features, traits=traits,
                    baseline=personal, global_baseline=baseline(self.store, session, speaker, False), deviations=changes,
                    archetypes=comparisons, coaching=coaching, archetype_coaching=archetype_coaching,
                    archetype_status="available" if comparisons else "missing_reference_data",
                    target_archetype=target,
                    status="measured and estimated indicators; interpretation is separate",
                    llm_runs=self.store.rows("SELECT id,condition,status,model,error FROM llm_runs WHERE speaker_id=? ORDER BY created_at DESC", (speaker_id,)))

    def map_speaker(self, speaker_id, body):
        speaker = self.store.one("SELECT * FROM speakers WHERE id=?", (speaker_id,))
        session = self.store.session(speaker["session_id"])
        if session["status"] == "processing":
            raise ValueError("Wait for processing to finish before editing mappings")
        profile_id = body.get("profile_id") or None
        if profile_id:
            self.store.one("SELECT * FROM profiles WHERE id=?", (profile_id,))
            conflicting = self.store.rows("SELECT s.split FROM sessions s JOIN speakers p ON p.session_id=s.id WHERE p.profile_id=?", (profile_id,))
            if any((s["split"] == "reference") != (session["split"] == "reference") for s in conflicting):
                raise ValueError("A reference participant cannot also be an analysis participant")
        name = str(body.get("display_name", speaker["display_name"])).strip()
        if not name or len(name) > 100:
            raise ValueError("Speaker display name must contain 1–100 characters")
        try:
            self.store.execute("UPDATE speakers SET display_name=?,profile_id=? WHERE id=?", (name, profile_id, speaker_id))
        except sqlite3.IntegrityError as exc:
            raise ValueError("A person can map to only one speaker cluster in each session; review diarization first") from exc
        self.store.invalidate()
        return self.store.one("SELECT * FROM speakers WHERE id=?", (speaker_id,))

    def delete(self, session_id):
        row = self.store.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        if row["status"] == "processing":
            raise ValueError("Wait for processing to finish before deleting")
        folder = Path(row["original_path"]).parent.resolve()
        expected = (self.store.root / "media" / session_id).resolve()
        if folder != expected or not folder.is_relative_to(self.store.root / "media"):
            raise ValueError("Media path is outside the session directory")
        # Media first: a failure remains visible and can be retried, never silently orphaned.
        if folder.exists():
            shutil.rmtree(folder)
        references = self.store.rows("SELECT archetype_id,distribution FROM archetype_features WHERE distribution IS NOT NULL")
        dependent = {r["archetype_id"] for r in references if session_id in {s["session_id"] for s in json.loads(r["distribution"])["sources"]}}
        with self.store.connect() as db:
            for archetype_id in dependent:
                db.execute("DELETE FROM comparisons WHERE archetype_id=?", (archetype_id,))
                db.execute("DELETE FROM archetypes WHERE id=?", (archetype_id,))
        self.store.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.store.invalidate()

    def profile(self, profile_id):
        person = self.store.one("SELECT * FROM profiles WHERE id=?", (profile_id,))
        speakers = self.store.rows("SELECT p.*,s.recorded_at,s.context,s.filename FROM speakers p JOIN sessions s ON s.id=p.session_id "
                                   "WHERE p.profile_id=? AND s.status='complete' AND s.split!='reference' ORDER BY s.recorded_at,s.created_at", (profile_id,))
        series = [dict(speaker=s, report=self.report(s["id"])) for s in speakers]
        recurring = []
        for feature, (name, kind) in TRAIT_FEATURES.items():
            sessions = []
            refs = []
            for entry in series:
                matches = [t for t in entry["report"]["traits"] if t["feature"] == feature]
                if matches:
                    sessions.append(entry["speaker"]["session_id"])
                    refs.extend(matches[0]["evidence_ids"])
            if len(set(sessions)) >= 3:
                recurring.append(dict(name=name, feature=feature, sessions=sessions, evidence_ids=refs, confidence="low",
                                      interpretation="Indicator appears in at least three independent recordings; magnitude and context must be reviewed."))
        return dict(person=person, series=series, recurring_traits=recurring, session_count=len(speakers),
                    maturity="limited history" if len(speakers) < 5 else "baseline eligible; validation pending")
