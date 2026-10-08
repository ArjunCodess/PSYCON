"""Durable audio processing and inspectable communication reports."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import psycopg
import threading
from uuid import uuid4

import numpy as np

from .audio import PyannoteAdapter, WhisperAdapter, attribute, preprocess, model_versions
from .features import DICTIONARY, UNAVAILABLE, extract
from .profiles import baseline, compare_archetypes, generate_traits, initialize_archetypes, TRAIT_FEATURES
from .store import decode, Store, encode, uid, now
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
                transcription_model=model, transcription_compute_type=os.getenv("PSYCON_WHISPER_COMPUTE_TYPE", "int8_float16" if device=="cuda" else "int8"),
                transcription_revision=os.getenv("PSYCON_INSTRUMENT_WHISPER_REVISION", "edaa852ec7e145841d8ffdb056a99866b5f0a478" if model == "large-v3" else "") or None,
                device=device, max_speakers=12, max_duration_seconds=14400,
                min_transcript_confidence=.55, min_attribution_fraction=.6,
                max_upload_bytes=8*1024*1024*1024, denoising=False, language="en")


class Instrument:
    def __init__(self, root, diarizer_factory=PyannoteAdapter, transcriber_factory=WhisperAdapter):
        self.store = Store(root)
        self.diarizer_factory = diarizer_factory
        self.transcriber_factory = transcriber_factory
        # Definitions and archetypes are installed by the explicit migration command.

    def ingest(self, stream, filename, metadata, *, allow_unknown_consent=False):
        if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename or len(filename)>255:
            raise ValueError('Use an original basename without directory components')
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
            if ((split == "reference") != (existing["split"] == "reference")) and set(participants) & set(decode(existing["participant_ids"])):
                raise ValueError("Reference and analysis participants must be disjoint")
        key = uid()
        folder = self.store.root / "media" / key
        folder.mkdir(parents=True)
        original = folder / filename
        config = configuration()
        sha, size = hashlib.sha256(), 0
        try:
            with original.open("xb") as target:
                while chunk := stream.read(1024*1024):
                    size += len(chunk)
                    if size > config["max_upload_bytes"]:
                        raise ValueError("Maximum upload size is 8 GiB per recording")
                    sha.update(chunk)
                    target.write(chunk)
            if not size:
                raise ValueError("The uploaded file is empty")
            if self.store.rows("SELECT id FROM sessions WHERE sha256=%s", (sha.hexdigest(),)):
                raise ValueError("Duplicate recording: the original session is already stored")
            from .assets import register
            with self.store.connect() as db:
                asset=register(self.store, original, 'media', root=folder, db=db, digest=sha.hexdigest())
                self.store.insert("sessions", dict(id=key, filename=filename[:512], sha256=sha.hexdigest(), original_path=str(original),
                              recorded_at=stamp, created_at=now(), context=str(metadata.get("context", "meeting"))[:100],
                              topic=str(metadata.get("topic", ""))[:500], dataset=str(metadata.get("dataset", "personal uploads"))[:200],
                              split=split, consent=consent, conditions=str(metadata.get("conditions", "not supplied"))[:1000],
                              participant_ids=encode(participants), status="queued", config=encode(config), versions=encode(model_versions(config)), asset_id=asset["id"]), db)
                self.store.insert('session_assets',dict(session_id=key,asset_id=asset['id'],purpose='input'),db)
                for stage in STAGES:
                    self.store.insert('stages', dict(session_id=key,name=stage,status='pending'),db)
                from .jobs import enqueue
                enqueue(self.store,'speech',key,1,db=db)
        except Exception:
            shutil.rmtree(folder)
            raise
        return self.store.session(key)

    def retry(self, session_id):
        session = self.store.session(session_id)
        if session["status"] not in ("failed", "blocked"):
            raise ValueError("Only failed or blocked sessions can be retried")
        with self.store.connect() as db:
            row=db.execute("UPDATE sessions SET status='queued',error=NULL,input_revision=input_revision+1 WHERE id=%s RETURNING input_revision",(session_id,)).fetchone()
            from .jobs import enqueue
            enqueue(self.store,'speech',session_id,row['input_revision'],db=db)

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
        others = self.store.rows("SELECT participant_ids,split FROM sessions WHERE id!=%s", (session_id,))
        if any((split == "reference") != (r["split"] == "reference") and set(participants) & set(decode(r["participant_ids"])) for r in others):
            raise ValueError("Reference and analysis participants must be disjoint")
        source = self.store.rows("SELECT af.distribution FROM archetype_features af WHERE af.distribution IS NOT NULL")
        if split != "reference" and any(session_id in {s["session_id"] for s in decode(r["distribution"])["sources"]} for r in source):
            raise ValueError("This session is used by a reference profile; keep its reference split or remove the dependent reference first")
        linked = self.store.rows("SELECT s.split FROM sessions s JOIN speakers p ON p.session_id=s.id WHERE s.id!=%s "
                                 "AND p.profile_id IN (SELECT profile_id FROM speakers WHERE session_id=%s AND profile_id IS NOT NULL)", (session_id, session_id))
        if any((r["split"] == "reference") != (split == "reference") for r in linked):
            raise ValueError("Known personal identities cannot cross reference and analysis splits")
        if values["consent"] not in ("documented", "public licensed", "self recording", "not documented"):
            raise ValueError("Invalid consent status")
        with self.store.connect() as db:
            db.execute("UPDATE sessions SET recorded_at=%s,context=%s,topic=%s,conditions=%s,dataset=%s,consent=%s,split=%s,participant_ids=%s,input_revision=input_revision+1 WHERE id=%s",
                       (stamp, *(values[k] for k in ("context", "topic", "conditions", "dataset", "consent")), split, encode(participants), session_id))
            for row in db.execute("SELECT id,context FROM evidence WHERE session_id=%s", (session_id,)).fetchall():
                context = decode(row["context"])
                context.update(session_context=values["context"])
                if not context.get("annotation_reviewer"):
                    context["topic"] = values["topic"] or "not annotated"
                db.execute("UPDATE evidence SET context=%s WHERE id=%s", (encode(context), row["id"]))
            db.execute("UPDATE llm_runs SET status='stale',error='Session metadata changed; queue a new run' WHERE session_id=%s AND status IN ('complete','queued','running')", (session_id,))
            from .answers import invalidate_participant
            for participant in db.execute('SELECT id FROM session_participants WHERE session_id=%s',(session_id,)).fetchall():
                invalidate_participant(self.store,str(participant['id']),'Session context or dataset role changed',db)
            db.execute("UPDATE jobs SET status='canceled',finished_at=now() WHERE subject_id=%s AND status IN ('queued','running')",(session_id,))
            if session['status']=='queued':
                from .jobs import enqueue
                revision=db.execute('SELECT input_revision FROM sessions WHERE id=%s',(session_id,)).fetchone()['input_revision']
                enqueue(self.store,'speech',session_id,revision,db=db)
        self.store.invalidate()
        return self.store.session(session_id)

    def process_next(self):
        from .jobs import claim, lease, finish
        from .store import StaleJob
        job=claim(self.store,'speech')
        if job is None:
            return None
        session_id=job['subject_id']
        try:
            with lease(self.store,job,gpu=True):
                session=self.store.session(session_id)
                if session['input_revision'] != job['input_revision']:
                    raise StaleJob('Session changed since this job was queued')
                self.store.execute("UPDATE sessions SET status='processing',worker_id=%s WHERE id=%s",(job['owner'],session_id))
                result=self._process_claimed(session_id,job['owner'])
                finish(self.store,job,result={'session_id':session_id},error=result.get('error') if result['status']=='failed' else None,retry=result.get('retryable',False))
                return result
        except StaleJob:
            return None

    def _process_claimed(self, session_id, worker_id):
        stage = "preprocessing"
        try:
            session = self.store.session(session_id)
            config = session["config"]
            original = self.store.local_path(self.store.one("SELECT original_path FROM sessions WHERE id=%s", (session_id,))["original_path"])
            self.store.stage(session_id, stage, "running")
            derived=self.store.root/"media"/session_id/"derived"
            derived.mkdir(parents=True,exist_ok=True)
            audio = preprocess(original, derived/"normalized.wav", config["max_duration_seconds"])
            from .assets import register
            with self.store.connect() as db:
                asset=register(self.store,derived/'normalized.wav','media',root=derived,db=db)
                db.execute('INSERT INTO session_assets VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(session_id,asset['id'],'normalized playback'))
            self.store.stage(session_id, stage, "complete", audio.diagnostics)
            self.store.execute("UPDATE sessions SET duration=%s,sample_rate=%s,channels=%s WHERE id=%s",
                               (audio.diagnostics["duration"], audio.diagnostics["original_sample_rate"], audio.diagnostics["original_channels"], session_id))
            session = self.store.session(session_id)
            def model_stage(name, action):
                old = self.store.one("SELECT * FROM stages WHERE session_id=%s AND name=%s", (session_id, name))
                if old["status"] == "complete" and old["output"]:
                    return decode(old["output"])
                self.store.stage(session_id, name, "running")
                try:
                    result = action()
                finally:
                    if config['device']=='cuda':
                        # Torch's caching allocator otherwise retains diarization
                        # VRAM that CTranslate2 needs for the next model.
                        import gc,torch
                        gc.collect()
                        torch.cuda.empty_cache()
                self.store.stage(session_id, name, "complete", result)
                return result
            stage = "diarization"
            raw_turns = model_stage(stage, lambda: config.get("reviewed_diarization") or self.diarizer_factory(config).diarize(audio.samples, 16000))
            stage = "transcription"
            transcript = model_stage(stage, lambda: self.transcriber_factory(config).transcribe(audio.samples, 16000))
            stage = "attribution"
            self.store.stage(session_id, stage, "running")
            speakers, turns, utterances, words = attribute(session_id, raw_turns, transcript, session["duration"], config["max_speakers"])
            # Keep reviewed mappings and identifiers on retry.
            old = {s["label"]: s for s in self.store.rows("SELECT * FROM speakers WHERE session_id=%s", (session_id,))}
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
            if old:
                retained_turns=self.store.rows('SELECT * FROM turns WHERE session_id=%s',(session_id,))
                retained_utterances=self.store.rows('SELECT * FROM utterances WHERE session_id=%s',(session_id,))
                def signatures(rows,fields):
                    return sorted((tuple(row[field] for field in fields) for row in rows),key=repr)
                if (signatures(turns,('speaker_id','start','end')) != signatures(retained_turns,('speaker_id','start','end')) or
                    signatures(utterances,('speaker_id','start','end','text')) != signatures(retained_utterances,('speaker_id','start','end','text'))):
                    raise ValueError('Retry changed retained speaker evidence; create a separate analysis and review its mapping')
                # Cached speech output must retain the identities cited by human answers and reports.
                speakers=list(old.values());turns=retained_turns;utterances=retained_utterances
            else:
                with self.store.connect() as db:
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
            features=self.store.rows('SELECT * FROM features WHERE session_id=%s',(session_id,))
            if features:
                evidence=self.store.rows('SELECT * FROM evidence WHERE session_id=%s',(session_id,))
                interactions=self.store.rows('SELECT * FROM interactions WHERE session_id=%s',(session_id,))
            else:
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
            self.store.execute("UPDATE sessions SET status='complete',lease_until=NULL,worker_id=NULL WHERE id=%s", (session_id,))
            from .training import predict
            for speaker in speakers:
                predict(self.store,speaker['id'])
        except __import__("backend.instrument.store", fromlist=["StaleJob"]).StaleJob:
            raise
        except Exception as exc:
            # Never convert model/runtime failure into plausible fabricated features.
            message = str(exc)[:1500]
            self.store.stage(session_id, stage, "failed", error=message)
            self.store.execute("UPDATE sessions SET status='failed',error=%s,lease_until=NULL,worker_id=NULL WHERE id=%s", (message, session_id))
            from .jobs import retryable
            return dict(self.store.session(session_id),retryable=retryable(exc))
        return self.store.session(session_id)

    def detail(self, session_id):
        session = self.store.session(session_id)
        stages = self.store.rows("SELECT * FROM stages WHERE session_id=%s", (session_id,))
        stages.sort(key=lambda row: STAGES.index(row["name"]) if row["name"] in STAGES else len(STAGES))
        for row in stages:
            row["output"] = decode(row["output"]) if row["output"] else None
        result = dict(session=session, stages=stages)
        for table in ("speakers", "turns", "utterances", "features", "evidence", "interactions"):
            result[table] = self.store.rows(f"SELECT * FROM {table} WHERE session_id=%s", (session_id,))
        for row in result["evidence"]:
            row["context"] = decode(row["context"])
        result["words"] = self.store.rows("SELECT w.* FROM words w JOIN utterances u ON u.id=w.utterance_id WHERE u.session_id=%s ORDER BY w.start_s", (session_id,))
        result['reports']=[]
        if session['status']=='complete':
            context=self._report_context(session,result)
            result['reports']=[self.report(s['id'],context=context,persist=False) for s in result['speakers']]
            self._save_comparisons(result['reports'])
        return result

    def _report_context(self,session,detail=None):
        """Session-wide reads avoid a remote database round trip for every speaker."""
        context=dict(detail or {},session=session)
        sid=session['id']
        for table in ('speakers','features','evidence'):
            if table not in context:
                context[table]=self.store.rows(f'SELECT * FROM {table} WHERE session_id=%s',(sid,))
        context['traits']=self.store.rows('SELECT st.*,t.name,t.feature FROM session_traits st JOIN traits t ON t.id=st.trait_id JOIN speakers p ON p.id=st.speaker_id WHERE p.session_id=%s',(sid,))
        links=self.store.rows('SELECT r.session_trait_id,r.evidence_id FROM trait_evidence r JOIN session_traits st ON st.id=r.session_trait_id JOIN speakers p ON p.id=st.speaker_id WHERE p.session_id=%s',(sid,))
        evidence_ids={}
        for link in links:evidence_ids.setdefault(link['session_trait_id'],[]).append(link['evidence_id'])
        for trait in context['traits']:trait['evidence_ids']=evidence_ids.get(trait['id'],[])
        from .profiles import reference_context
        context['references']=reference_context(self.store)
        context['targets']={p['id']:p['target_archetype'] for p in self.store.rows("SELECT id,target_archetype FROM profiles WHERE user_id='local'")}
        context['default_target']=self.store.one("SELECT value FROM workspace_settings WHERE name='target_archetype'")['value']
        context['predictions']=self.store.rows("SELECT DISTINCT ON (p.speaker_id,m.family,m.target) p.*,m.family,m.target,m.evaluation_status FROM model_predictions p JOIN model_versions m ON m.id=p.model_id JOIN speakers sp ON sp.id=p.speaker_id WHERE sp.session_id=%s AND p.input_revision=%s AND m.status='active' ORDER BY p.speaker_id,m.family,m.target,p.created_at DESC",(sid,session['input_revision']))
        if context['predictions']:
            links=self.store.rows('SELECT r.prediction_id,r.evidence_id FROM prediction_evidence r JOIN model_predictions p ON p.id=r.prediction_id JOIN speakers sp ON sp.id=p.speaker_id WHERE sp.session_id=%s',(sid,))
            evidence_ids={}
            for link in links:evidence_ids.setdefault(link['prediction_id'],[]).append(link['evidence_id'])
            for prediction in context['predictions']:prediction['evidence_ids']=evidence_ids.get(prediction['id'],[])
        context['runs']=self.store.rows('SELECT id,speaker_id,condition,status,model,error FROM llm_runs WHERE session_id=%s ORDER BY created_at DESC',(sid,))
        return context

    def _save_comparisons(self,reports):
        if not reports:return
        from psycopg.types.json import Jsonb
        rows=[(uid(),report['session_id'],report['speaker']['id'],result['archetype']['id'],result['similarity'],result['method'],Jsonb(result['dimensions']),result['status']) for report in reports for result in report['archetypes']]
        with self.store.connect() as db:
            db.execute('DELETE FROM comparisons WHERE speaker_id=ANY(%s)',([report['speaker']['id'] for report in reports],))
            if rows:
                with db.cursor() as cursor:
                    cursor.executemany('INSERT INTO comparisons(id,session_id,speaker_id,archetype_id,similarity,method,dimensions,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',rows)

    def report(self, speaker_id, *, context=None, persist=True):
        if context is None:
            speaker=self.store.one('SELECT * FROM speakers WHERE id=%s',(speaker_id,))
            context=self._report_context(self.store.session(speaker['session_id']))
        speaker=next(s for s in context['speakers'] if s['id']==speaker_id)
        session=context['session']
        if session['status']!='complete':
            raise ValueError('Analysis unavailable while processing is incomplete or failed')
        features=[r for r in context['features'] if r['speaker_id']==speaker_id]
        traits=[r for r in context['traits'] if r['speaker_id']==speaker_id]
        comparisons=compare_archetypes(self.store,session,speaker,features,context['references'])
        personal = baseline(self.store, session, speaker)
        changes = [dict(feature=k, **v) for k, v in personal["statistics"].items() if v["substantial_descriptive_deviation"]]
        evidence = [r for r in context['evidence'] if r['speaker_id']==speaker_id]
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
        target = context['targets'][speaker['profile_id']] if speaker['profile_id'] else context['default_target']
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
        predictions=[r for r in context['predictions'] if r['speaker_id']==speaker_id]
        result=dict(speaker=speaker, session_id=session["id"], features=features, traits=traits, supervised_predictions=predictions,
                    baseline=personal, global_baseline=baseline(self.store, session, speaker, False), deviations=changes,
                    archetypes=comparisons, coaching=coaching, archetype_coaching=archetype_coaching,
                    archetype_status="available" if comparisons else "missing_reference_data",
                    target_archetype=target,
                    status="measured and estimated indicators; interpretation is separate",
                    llm_runs=[{k:v for k,v in r.items() if k!='speaker_id'} for r in context['runs'] if r['speaker_id']==speaker_id])
        if persist:self._save_comparisons([result])
        return result

    def map_speaker(self, speaker_id, body):
        speaker = self.store.one("SELECT * FROM speakers WHERE id=%s", (speaker_id,))
        session = self.store.session(speaker["session_id"])
        if session["status"] == "processing":
            raise ValueError("Wait for processing to finish before editing mappings")
        profile_id = body.get("profile_id") or None
        reviewer=str(body.get('reviewer_id','')).strip()
        if profile_id!=speaker['profile_id'] and not reviewer:
            raise ValueError('Changing personal history requires a reviewed participant mapping and reviewer code')
        if profile_id:
            self.store.one("SELECT * FROM profiles WHERE id=%s", (profile_id,))
            if self.store.rows('SELECT id FROM speakers WHERE session_id=%s AND profile_id=%s AND id<>%s',(session['id'],profile_id,speaker_id)):
                raise ValueError('A person can map to only one speaker cluster per session; use participant review to correct the association')
            conflicting = self.store.rows("SELECT s.split FROM sessions s JOIN speakers p ON p.session_id=s.id WHERE p.profile_id=%s", (profile_id,))
            if any((s["split"] == "reference") != (session["split"] == "reference") for s in conflicting):
                raise ValueError("A reference participant cannot also be an analysis participant")
        name = str(body.get("display_name", speaker["display_name"])).strip()
        if not name or len(name) > 100:
            raise ValueError("Speaker display name must contain 1–100 characters")
        try:
            if profile_id!=speaker['profile_id']:
                from .answers import add_participant,map_participant
                with self.store.connect() as db:
                    if profile_id:
                        profile=db.execute('SELECT label FROM profiles WHERE id=%s',(profile_id,)).fetchone()
                        db.execute("INSERT INTO people(id,owner_id,code) VALUES (%s,'local',%s) ON CONFLICT(id) DO NOTHING",(profile_id,profile['label']))
                participants=self.store.rows('SELECT p.* FROM session_participants p WHERE session_id=%s AND person_id=%s',(session['id'],profile_id)) if profile_id else []
                if not profile_id:
                    participants=self.store.rows('SELECT p.* FROM session_participants p JOIN speaker_mappings m ON m.participant_id=p.id WHERE m.speaker_id=%s AND m.revision=(SELECT max(revision) FROM speaker_mappings x WHERE x.participant_id=p.id)',(speaker_id,))
                participant=participants[0] if participants else add_participant(self.store,session['id'],dict(code='history-'+profile_id,person_id=profile_id)) if profile_id else None
                if participant:
                    map_participant(self.store,session['id'],participant['id'],dict(speaker_id=speaker_id if profile_id else None,status='confirmed' if profile_id else 'unmapped',reviewer_id=reviewer,reason=str(body.get('reason','Reviewed personal history association'))))
            self.store.execute("UPDATE speakers SET display_name=%s,profile_id=%s WHERE id=%s", (name, profile_id, speaker_id))
        except psycopg.IntegrityError as exc:
            raise ValueError("A person can map to only one speaker cluster in each session; review diarization first") from exc
        self.store.invalidate()
        return self.store.one("SELECT * FROM speakers WHERE id=%s", (speaker_id,))

    def delete(self, session_id):
        row = self.store.one("SELECT * FROM sessions WHERE id=%s", (session_id,))
        if row["status"] == "processing":
            raise ValueError("Wait for processing to finish before deleting")
        folder = self.store.local_path(row["original_path"]).parent
        expected = (self.store.root / "media" / session_id).resolve()
        managed=folder==expected and folder.is_relative_to(self.store.root / 'media')
        if not managed:
            from .assets import resolve
            if not row['asset_id'] or resolve(self.store,row['asset_id'])!=self.store.local_path(row['original_path']):
                raise ValueError('External source is not registered; deletion cannot resolve its retention scope')
        self.store.execute("UPDATE jobs SET status='canceled',finished_at=now() WHERE subject_id=%s AND status IN ('queued','running')",(session_id,))
        from .deletion import delete_participant
        for participant in self.store.rows('SELECT id FROM session_participants WHERE session_id=%s',(session_id,)):
            delete_participant(self.store,session_id,participant['id'])
        # Media first: a failure remains visible and can be retried, never silently orphaned.
        shared=self.store.rows('SELECT session_id FROM session_assets WHERE asset_id=%s AND session_id<>%s',(row['asset_id'],session_id))
        if managed and folder.exists() and not shared:
            shutil.rmtree(folder)
        else:
            generated=self.store.root/'media'/session_id/'derived'
            if generated.exists():shutil.rmtree(generated)
        references = self.store.rows("SELECT archetype_id,distribution FROM archetype_features WHERE distribution IS NOT NULL")
        dependent = {r["archetype_id"] for r in references if session_id in {s["session_id"] for s in decode(r["distribution"])["sources"]}}
        with self.store.connect() as db:
            db.execute("UPDATE assets SET state='deleted',retention='generated session audio deleted' WHERE id IN (SELECT asset_id FROM session_assets WHERE session_id=%s AND purpose='normalized playback') AND NOT EXISTS (SELECT 1 FROM session_assets other WHERE other.asset_id=assets.id AND other.session_id<>%s)",(session_id,session_id))
            if managed and row['asset_id'] and not shared:
                db.execute("UPDATE assets SET state='deleted',retention='session deleted' WHERE id=%s",(row['asset_id'],))
            for archetype_id in dependent:
                db.execute("DELETE FROM comparisons WHERE archetype_id=%s", (archetype_id,))
                db.execute("DELETE FROM archetypes WHERE id=%s", (archetype_id,))
            db.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
            db.execute('INSERT INTO deletion_tombstones(id,subject_hash,kind,backup_policy) VALUES (%s,%s,%s,%s)',(uid(),hashlib.sha256(session_id.encode()).hexdigest(),'session','Purge affected backup generations; do not replay older SQLite sources'))
        self.store.invalidate()

    def profile(self, profile_id):
        person = self.store.one("SELECT * FROM profiles WHERE id=%s", (profile_id,))
        speakers = self.store.rows("SELECT p.*,s.recorded_at,s.context,s.filename FROM speakers p JOIN sessions s ON s.id=p.session_id "
                                   "WHERE p.profile_id=%s AND s.status='complete' AND s.split!='reference' ORDER BY s.recorded_at,s.created_at", (profile_id,))
        series = [dict(speaker=s, report=self.report(s["id"])) for s in speakers]
        from .provenance import source_groups
        components=source_groups(self.store)
        recording_count=len({components[s["session_id"]] for s in speakers})
        recurring = []
        for feature, (name, kind) in TRAIT_FEATURES.items():
            sessions = []
            refs = []
            for entry in series:
                matches = [t for t in entry["report"]["traits"] if t["feature"] == feature]
                if matches:
                    sessions.append(entry["speaker"]["session_id"])
                    refs.extend(matches[0]["evidence_ids"])
            if len({components[sid] for sid in sessions}) >= 3:
                recurring.append(dict(name=name, feature=feature, sessions=sessions, evidence_ids=refs, confidence="low",
                                      interpretation="Indicator appears in at least three independent recordings; magnitude and context must be reviewed."))
        return dict(person=person, series=series, recurring_traits=recurring, session_count=len(speakers), independent_recording_count=recording_count,
                    maturity="limited history" if recording_count < 5 else "baseline eligible; validation pending")
