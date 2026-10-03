from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
from cryptography.fernet import Fernet

from backend.auth import create_token, hash_token
from ml.src.audio_recording import decode_audio
from ml.src.speaker_analysis import VoiceProfile, SpeechBrainEmbedder, enroll_wearer
from .analysis import analyze_upload, redact
from .llm import EVENTS, LocalInterpreter
from .longitudinal import cohort, eligible, summarize
from .rubrics import ROLES


def now():
    return datetime.now(timezone.utc).isoformat()


def source_time(value):
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("occurred_at must be a timezone-aware timestamp")
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise ValueError("occurred_at must include a timezone and cannot be in the future")
    return timestamp.astimezone(timezone.utc).isoformat()


def context_value(body):
    keys = ("language", "conversation_type", "microphone", "setting", "topic", "counterpart_relationship", "objective")
    if not isinstance(body, dict):
        raise ValueError("context must be an object")
    result = {key: str(body.get(key, "unknown")).strip()[:200] for key in keys}
    if any(not result[key] or result[key] == "unknown" for key in ("language", "conversation_type", "microphone", "setting")):
        raise ValueError("language, conversation_type, microphone and setting are required")
    return result


class Enrollment:
    def __init__(self, service, profile):
        self.service, self.profile = service, profile

    def save(self, value):
        body = {"embedding": value.embedding.tolist(), "engine": value.engine,
                "enrolled_clips": value.enrolled_clips, "usable_duration_s": value.usable_duration_s}
        self.profile["enrollment"] = self.service.cipher().encrypt(json.dumps(body).encode()).decode()
        self.service.store.put("profile", self.profile)


class CommunicationService:
    def __init__(self, store, *, spool=None, analyzer=None, interpreter=None, sources=None):
        self.store = store
        self.spool = Path(spool or os.getenv("PSYCON_COMMUNICATION_SPOOL", ".psycon-private-spool"))
        self.analyzer = analyzer or analyze_upload
        self.interpreter = interpreter or LocalInterpreter()
        self.sources = sources

    def link_source(self, pid, source, context):
        profile = self.store.get("profile", pid)
        if not profile or not profile["consent"]:
            raise ValueError("wearer consent is required")
        if source["type"] == "device_reference" and not profile.get("enrollment"):
            raise ValueError("device recordings require wearer enrollment")
        cid = hashlib.sha256((pid+source["fingerprint"]).encode()).hexdigest()
        with self.store.lock(pid):
            if self.store.get("conversation", cid):
                return self.public_conversation(self.store.get("conversation", cid))
            stamp = source_time(source["occurred_at"])
            row = {"id": cid, "profile_id": pid, "source_sha256": source["recording_sha256"], "filename": "source.wav",
                   "context": context_value(context), "occurred_at": stamp, "created_at": now(), "revision": 0,
                   "state": "queued", "source": source, "raw_state": "research_source_retained"}
            self.store.put("link", {"id": cid, "profile_id": pid, "source": source, "confirmed_at": now()})
            self.store.put("conversation", row)
            self.audit(pid, "source_link_confirmed", cid)
            return self.public_conversation(row)

    def cipher(self):
        secret = os.getenv("PSYCON_PROFILE_KEY", "")
        if len(secret) < 32:
            raise ValueError("PSYCON_PROFILE_KEY must contain at least 32 characters")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))

    def provision(self, role, label):
        if not isinstance(role, str) or role not in ROLES or not isinstance(label, str) or not label.strip():
            raise ValueError("valid role and wearer label required")
        token, pid = create_token(), str(uuid4())
        self.store.put("profile", {"id": pid, "profile_id": pid, "label": label[:80], "role": role,
                                  "token_hash": hash_token(token), "created_at": now(), "consent": False, "revision": 0})
        return {"id": pid, "token": token}

    def authenticate(self, token):
        if not token:
            return None
        digest = hash_token(token)
        for profile in self.store.rows("profile"):
            if profile.get("token_hash") == digest and not profile.get("revoked"):
                return {"profile_id": profile["id"], "scope": "owner"}
        for grant in self.store.rows("grant"):
            profile = self.store.get("profile", grant["profile_id"])
            if (grant["token_hash"] == digest and not grant.get("revoked") and grant["expires_at"] > now()
                    and profile and not profile.get("revoked")):
                return {"profile_id": grant["profile_id"], "scope": grant["scope"]}
        return None

    def profile(self, pid):
        row = self.store.get("profile", pid)
        if not row:
            raise LookupError("profile not found")
        return {k:v for k,v in row.items() if k not in {"token_hash", "enrollment"}} | {"enrolled": bool(row.get("enrollment"))}

    def update_profile(self, pid, body):
        with self.store.lock(pid):
            row = self.store.get("profile", pid)
            if "role" in body:
                if body["role"] not in ROLES:
                    raise ValueError("unsupported role")
                row["role"] = body["role"]
            if "consent" in body:
                if not isinstance(body["consent"], bool):
                    raise ValueError("consent must be boolean")
                row["consent"] = body["consent"]
            row["revision"] += 1
            self.store.put("profile", row)
            self.invalidate(pid)
        return self.profile(pid)

    def enroll(self, pid, files):
        if len(files) != 3:
            raise ValueError("three enrollment recordings are required")
        with self.store.lock(pid):
            profile = self.store.get("profile", pid)
            if not profile["consent"]:
                raise ValueError("recording consent required")
            self.spool.mkdir(parents=True, exist_ok=True)
            job = {"id": "enrollment-"+str(uuid4()), "profile_id": pid, "created_at": now(), "state": "queued"}
            profile["enrollment_generation"] = profile.get("enrollment_generation", 0)+1
            profile["enrollment_status"] = "queued"
            job["generation"] = profile["enrollment_generation"]
            payload = json.dumps([base64.b64encode(raw).decode() for raw in files]).encode()
            (self.spool/(job["id"]+".encrypted")).write_bytes(self.cipher().encrypt(payload))
            self.store.put("profile", profile)
            self.store.put("enrollment", job)
        return {"state": "queued", "message": "Voice enrollment will run on the local processing worker."}

    def process_enrollment(self):
        for job in self.store.rows("enrollment"):
            pid = job["profile_id"]
            with self.store.lock(pid):
                profile = self.store.get("profile", pid)
                expired = datetime.fromisoformat(job["created_at"])+timedelta(hours=24) < datetime.now(timezone.utc)
                cancel = not profile or not profile.get("consent") or profile.get("revoked") or job["generation"] != profile.get("enrollment_generation")
                if job["state"] in {"delete_pending", "complete"} or expired or cancel:
                    try:
                        (self.spool/(job["id"]+".encrypted")).unlink(missing_ok=True)
                        self.store.delete("enrollment", job["id"])
                        self.audit(pid, "enrollment_raw_deleted", job["id"])
                    except OSError:
                        job["state"] = "delete_pending"
                        self.store.put("enrollment", job)
                    return True
                if job["state"] == "failed":
                    continue
                job["state"] = "processing"
                self.store.put("enrollment", job)
            try:
                payload = self.cipher().decrypt((self.spool/(job["id"]+".encrypted")).read_bytes())
                clips = [decode_audio(base64.b64decode(raw)) for raw in json.loads(payload)]
                del payload
                embedder = SpeechBrainEmbedder()
                # Commit only if enrollment wasn't revoked while the model loaded.
                class PendingEnrollment:
                    value = None
                    def save(self, value):
                        self.value = value
                pending = PendingEnrollment()
                enroll_wearer([(c.samples,c.sample_rate_hz) for c in clips], embedder, pending)
                del clips, embedder
                import gc
                gc.collect()
                with self.store.lock(pid):
                    profile = self.store.get("profile", pid)
                    if profile and not profile.get("revoked") and profile.get("consent") and job["generation"] == profile.get("enrollment_generation"):
                        profile["enrollment_status"] = "complete"
                        Enrollment(self, profile).save(pending.value)
                    job["state"] = "complete"
                    self.store.put("enrollment", job)
                    try:
                        (self.spool/(job["id"]+".encrypted")).unlink(missing_ok=True)
                        self.store.delete("enrollment", job["id"])
                    except OSError:
                        pass
            except Exception as exc:
                job.update(state="failed", error=type(exc).__name__)
                self.store.put("enrollment", job)
                with self.store.lock(pid):
                    profile = self.store.get("profile", pid)
                    if profile and job["generation"] == profile.get("enrollment_generation"):
                        profile["enrollment_status"] = "failed"
                        self.store.put("profile", profile)
            return True
        return False

    def voice(self, pid):
        row = self.store.get("profile", pid)
        if not row.get("enrollment"):
            return None
        value = json.loads(self.cipher().decrypt(row["enrollment"].encode()))
        return VoiceProfile(np.array(value["embedding"], dtype=np.float32), value["engine"], value["enrolled_clips"], value["usable_duration_s"])

    def upload(self, pid, raw, filename, context, occurred_at, *, source=None):
        profile = self.store.get("profile", pid)
        if not profile["consent"] or not profile.get("enrollment"):
            raise ValueError("consent and voice enrollment are required")
        timestamp = source_time(occurred_at)
        context = context_value(context)
        digest = hashlib.sha256(raw).hexdigest()
        cid = hashlib.sha256((pid+digest).encode()).hexdigest()
        with self.store.lock(pid):
            existing = self.store.get("conversation", cid)
            if existing:
                return self.public_conversation(existing)
            self.spool.mkdir(parents=True, exist_ok=True)
            path = self.spool / (cid+".encrypted")
            encrypted = self.cipher().encrypt(raw)
            # Exclusive create; an orphan from a interrupted upload can be safely replaced.
            temporary = self.spool / (cid+".tmp")
            temporary.write_bytes(encrypted)
            temporary.replace(path)
            row = {"id": cid, "profile_id": pid, "source_sha256": digest, "filename": Path(filename).name,
                   "context": context, "occurred_at": timestamp, "created_at": now(),
                   "state": "queued", "revision": 0, "source": source or {"type": "audio_upload"}, "raw_state": "pending"}
            self.store.put("conversation", row)
            return self.public_conversation(row)

    def public_conversation(self, row):
        # Private semantic proposals and full transient text are never API output.
        result = dict(row)
        analysis = dict(result.get("analysis", {}))
        analysis.pop("semantic_candidates", None)
        result["analysis"] = analysis
        return result

    def conversations(self, pid):
        return [self.public_conversation(r) for r in sorted(self.store.rows("conversation", pid), key=lambda r:r["occurred_at"], reverse=True) if r["state"] != "delete_pending"]

    def invalidate(self, pid):
        for row in self.store.rows("baseline", pid):
            self.store.delete("baseline", row["id"])
        # A correction changes the reference meaning, so don't silently rewrite a goal's frozen reference.
        for goal in self.store.rows("goal", pid):
            goal["state"] = "reference_invalidated"
            self.store.put("goal", goal)

    def history(self, pid):
        with self.store.lock(pid):
            profile = self.store.get("profile", pid)
            if not profile or profile.get("revoked"):
                raise LookupError("profile not found")
            report = summarize(self.history_rows(pid), profile["role"])
            report.update(profile_revision=profile["revision"], generated_at=now())
            self.store.put("baseline", {"id": pid, "profile_id": pid, "report": report})
            return report

    def history_rows(self, pid):
        rows = self.store.rows("conversation", pid)
        for row in rows:
            analysis = row.get("analysis", {})
            evidence = {e["id"]:e for e in analysis.get("evidence", [])}
            if "human_events" in analysis:
                events = [{"type":e["type"], "evidence_ids":[e["evidence_id"]]} for e in analysis["human_events"]]
            elif analysis.get("semantic_status") == "validated":
                events = analysis.get("events", [])
            else:
                continue
            own_turns = sum(t["speaker"] == "wearer" for t in analysis.get("turns", []))
            if own_turns:
                for event_type, metric in (("acknowledgement", "acknowledgement_per_turn"), ("clarification", "clarification_per_turn")):
                    intervals = {tuple(e["evidence_ids"]) for e in events if e["type"] == event_type and
                                 any(evidence[key].get("speaker") == "wearer" for key in e["evidence_ids"] if key in evidence)}
                    analysis["metrics"][metric] = len(intervals)/own_turns
        return rows

    def correct(self, pid, cid, body):
        with self.store.lock(pid):
            row = self.store.get("conversation", cid)
            if not row or row["profile_id"] != pid:
                raise LookupError("conversation not found")
            if row["state"] != "complete":
                raise ValueError("only completed conversations can be corrected")
            if "context" in body:
                row["context"] = context_value(body["context"])
            if "events" in body:
                ids = {e["id"] for e in row["analysis"].get("evidence", [])}
                events = body["events"]
                if not isinstance(events, list) or len(events) > 50:
                    raise ValueError("invalid events")
                for event in events:
                    if not isinstance(event, dict) or event.get("type") not in EVENTS or event.get("evidence_id") not in ids:
                        raise ValueError("event needs a supported type and retained evidence ID")
                row["analysis"]["human_events"] = [{"type": e["type"], "evidence_id": e["evidence_id"], "source": "wearer_correction"} for e in events]
            row["revision"] += 1
            self.store.put("conversation", row)
            self.invalidate(pid)
            self.audit(pid, "conversation_corrected", cid)
        return self.public_conversation(row)

    def delete_conversation(self, pid, cid):
        with self.store.lock(pid):
            row = self.store.get("conversation", cid)
            if not row or row["profile_id"] != pid:
                raise LookupError("conversation not found")
            row.update(state="delete_pending", revision=row["revision"]+1)
            row.pop("analysis", None)
            self.store.put("conversation", row)
            self.invalidate(pid)
            self.cleanup(row)

    def cleanup(self, row):
        try:
            for suffix in (".encrypted", ".tmp"):
                (self.spool/(row["id"]+suffix)).unlink(missing_ok=True)
        except OSError:
            return False
        if row["state"] == "delete_pending":
            self.store.delete("conversation", row["id"])
        else:
            row["raw_state"] = "research_source_retained" if row["source"]["type"] in {"group_reference", "device_reference"} else "deleted"
            self.store.put("conversation", row)
        self.audit(row["profile_id"], "raw_deleted", row["id"])
        return True

    def audit(self, pid, action, resource):
        self.store.put("audit", {"id": str(uuid4()), "profile_id": pid, "action": action, "resource_id": resource, "at": now()})

    def process_one(self):
        # All communication worker processes serialize GPU jobs and cleanup.
        with self.store.lock("communication-gpu-worker"):
            if self.process_enrollment():
                return True
            for row in sorted(self.store.rows("conversation"), key=lambda r:r["created_at"]):
                pid, cid = row["profile_id"], row["id"]
                if row["state"] == "delete_pending" or (row.get("raw_state") == "pending" and row["state"] == "complete"):
                    with self.store.lock(pid):
                        current = self.store.get("conversation", cid)
                        if current:
                            self.cleanup(current)
                    return True
                if row["state"] == "failed" and row.get("raw_state") == "pending" and datetime.fromisoformat(row["created_at"])+timedelta(hours=24) < datetime.now(timezone.utc):
                    with self.store.lock(pid):
                        current = self.store.get("conversation", cid)
                        if current and current["state"] == "failed":
                            self.cleanup(current)
                    continue
                if row["state"] not in {"queued", "processing"}:
                    continue
                # A prior process can only leave 'processing' after releasing this advisory lock.
                profile = self.store.get("profile", pid)
                if not profile or not profile.get("consent") or profile.get("revoked"):
                    with self.store.lock(pid):
                        row["state"] = "delete_pending"
                        self.store.put("conversation", row)
                        self.cleanup(row)
                    return True
                with self.store.lock(pid):
                    current = self.store.get("conversation", cid)
                    if not current or current["state"] not in {"queued", "processing"}:
                        continue
                    row = current
                    row["state"] = "processing"
                    self.store.put("conversation", row)
                    revision = row["revision"]
                try:
                    if row["source"]["type"] == "group_reference":
                        analysis = self.sources.group_analysis(row["source"])
                    else:
                        raw = (self.sources.device_audio(row["source"]) if row["source"]["type"] == "device_reference" else
                               self.cipher().decrypt((self.spool/(cid+".encrypted")).read_bytes()))
                        analysis = self.analyzer(raw, row["filename"], row["source_sha256"], self.voice(pid))
                        del raw
                    transient = analysis.pop("_transient", [])
                    semantic = self.interpreter.interpret(transient) if analysis.get("language") == "en" else {"state": "unsupported_language", "events": []}
                    analysis["events"] = []
                    if semantic["state"] == "validated":
                        evidence = {e["id"]: e for e in transient}
                        for event in semantic["events"][:12]:
                            refs = []
                            for key in event["evidence_ids"][:2]:
                                item = evidence[key]
                                ref = "semantic-"+key
                                if not any(e["id"] == ref for e in analysis["evidence"]):
                                    analysis["evidence"].append({"id": ref, "start_s": item["start_s"], "end_s": item["end_s"],
                                                                 "speaker": item["speaker"], "excerpt": item["text"][:200]})
                                refs.append(ref)
                            analysis["events"].append({"type": event["type"], "evidence_ids": refs, "source": "validated_local_model"})
                    # Full transcripts end here; only bounded, cited excerpts survive.
                    del transient
                    analysis["semantic_status"] = semantic["state"]
                    analysis["semantic_model"] = {key:semantic.get(key) for key in ("model", "digest", "reason")}
                    analysis["source_sha256"] = row["source_sha256"]
                    with self.store.lock(pid):
                        current = self.store.get("conversation", cid)
                        active = self.store.get("profile", pid)
                        if current and current["revision"] == revision and current["state"] == "processing" and active.get("consent") and not active.get("revoked"):
                            current.update(state="complete", analysis=analysis, completed_at=now())
                            if analysis.get("language") != current["context"]["language"]:
                                current["analysis"]["quality"] = "language_mismatch"
                            self.store.put("conversation", current)
                            self.cleanup(current)
                            self.history(pid)
                except Exception as exc:
                    with self.store.lock(pid):
                        current = self.store.get("conversation", cid)
                        if current and current["revision"] == revision and current["state"] == "processing":
                            current.update(state="failed", error=type(exc).__name__)
                            self.store.put("conversation", current)
                return True
            # Crash-orphaned encrypted files are not allowed to live indefinitely.
            if self.spool.exists():
                cutoff = datetime.now(timezone.utc).timestamp()-86400
                for path in self.spool.iterdir():
                    if (path.suffix in {".tmp", ".encrypted"} and path.stat().st_mtime < cutoff
                            and not self.store.get("conversation", path.stem) and not self.store.get("enrollment", path.stem)):
                        path.unlink(missing_ok=True)
        return False

    def grant(self, pid, scope):
        if scope not in {"reviewer", "context"}:
            raise ValueError("scope must be reviewer or context")
        token = create_token()
        row = {"id": str(uuid4()), "profile_id": pid, "scope": scope, "token_hash": hash_token(token),
               "expires_at": (datetime.now(timezone.utc)+timedelta(days=7)).isoformat()}
        self.store.put("grant", row)
        return {key:row[key] for key in ("id", "scope", "expires_at")} | {"token": token}

    def goal(self, pid, metric, direction):
        from .longitudinal import METRICS
        if metric not in METRICS or direction not in {"increase", "decrease"}:
            raise ValueError("choose a supported metric and increase/decrease")
        report = self.history(pid)
        from .longitudinal import MIN_CONVERSATIONS
        references = [b for b in report["baselines"] if b["current"]["state"] == "ready"
                      and b["current"]["metrics"].get(metric, {}).get("n", 0) >= MIN_CONVERSATIONS]
        if not references:
            raise ValueError("a ready baseline is required for this goal")
        row = {"id": str(uuid4()), "profile_id": pid, "metric": metric, "direction": direction,
               "created_at": now(), "state": "active", "reference": references}
        self.store.put("goal", row)
        return row

    def goals(self, pid):
        rows = self.history_rows(pid)
        goals = self.store.rows("goal", pid)
        for goal in goals:
            comparisons = []
            if goal["state"] == "active":
                for reference in goal["reference"]:
                    later = [r for r in rows if eligible(r) and r["occurred_at"] > goal["created_at"] and list(cohort(r)) == reference["cohort"] and goal["metric"] in r["analysis"]["metrics"]]
                    if len(later) >= 3:
                        values = sorted(r["analysis"]["metrics"][goal["metric"]] for r in later)
                        import statistics
                        comparisons.append({"cohort": reference["cohort"], "baseline_median": reference["current"]["metrics"][goal["metric"]]["median"],
                                            "later_median": statistics.median(values), "conversations": len(later), "interpretation": "Measured change; does not establish that coaching caused it."})
            goal["comparisons"] = comparisons
        return goals

    def export_context(self, pid):
        report = self.history(pid)
        patterns = [{k:p[k] for k in ("observation", "context", "evidence_count", "uncertainty", "suggested_adjustment")} | {
            "observation_dates": [e["occurred_at"] for e in p["evidence"]]} for p in report["patterns"]]
        latest = next((r["context"] for r in self.conversations(pid) if r["state"] == "complete"), None)
        safe_context = {key:redact(latest[key]) for key in ("language", "conversation_type", "setting", "objective")} if latest else None
        return {"schema_version": "psycon-context-1", "generated_at": now(), "role": report["role"], "patterns": patterns,
                "goals": [{k:g[k] for k in ("metric", "direction", "state")} for g in self.goals(pid)],
                "current_session_context": safe_context,
                "limitations": "Communication observations only. No diagnosis or fixed personality assessment."}
