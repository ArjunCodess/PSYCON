"""Reviewed conversational events extend the feature layer without an LLM extractor."""
import json

from .features import DICTIONARY, definition
from .profiles import generate_traits, TRAIT_FEATURES
from .store import uid, now, encode

EVENTS = ("interruption", "backchannel", "turn_yielding", "turn_holding", "open_question", "closed_question",
          "agreement", "partial_agreement", "disagreement", "clarification", "paraphrasing", "building_on_idea",
          "topic_initiation", "topic_continuation", "topic_shift", "topic_return", "topic_control",
          "claim", "reason", "evidence", "counterargument", "rebuttal", "concession", "proposal", "rejection", "alternative_proposal")
for event in EVENTS:
    DICTIONARY["reviewed_"+event+"_rate"] = definition(
        f"Distinct manually annotated {event.replace('_', ' ')} events per 10 minutes; annotation coverage may be partial",
        "annotated events/10min", "distinct supporting evidence IDs / original session duration * 600",
        "human event annotation", [0, None], "low")
    TRAIT_FEATURES["reviewed_"+event+"_rate"] = ("Reviewed "+event.replace("_", " ")+" indicators", "reviewed:"+event)


def annotate_behavior(instrument, evidence_id, body):
    store = instrument.store
    row = store.one("SELECT * FROM evidence WHERE id=?", (evidence_id,))
    kind = body.get("kind")
    reviewer = str(body.get("reviewer_id", "")).strip()
    target = body.get("target_speaker_id") or None
    if kind not in EVENTS or not reviewer:
        raise ValueError("Choose a defined observable behavior and provide a reviewer ID")
    session = store.session(row["session_id"])
    if session["status"] != "complete":
        raise ValueError("Behavior review requires a complete session")
    if target:
        speaker = store.one("SELECT * FROM speakers WHERE id=?", (target,))
        if speaker["session_id"] != row["session_id"] or target == row["speaker_id"]:
            raise ValueError("Interaction target must be a different speaker in the same session")
    if kind == "interruption" and not target:
        raise ValueError("A reviewed interruption must identify the interrupted speaker")
    # Multiple marker records from the same utterance represent one observed event.
    if row["utterance_id"]:
        canonical = store.rows("SELECT * FROM evidence WHERE utterance_id=? AND feature='utterance'", (row["utterance_id"],))
        if canonical:
            row = canonical[0]
    with store.connect() as db:
        db.execute("DELETE FROM behavior_annotations WHERE evidence_id=? AND kind=? AND reviewer_id=?", (row["id"], kind, reviewer))
        store.insert("behavior_annotations", dict(id=uid(), evidence_id=row["id"], kind=kind, reviewer_id=reviewer,
                     target_speaker_id=target, topic=str(body.get("topic", "not annotated"))[:300],
                     phase=str(body.get("phase", "not annotated"))[:100], notes=str(body.get("notes", ""))[:2000], created_at=now()), db)
    annotations = store.rows("SELECT a.*,e.session_id,e.speaker_id,e.start,e.end,e.text,e.context,e.utterance_id FROM behavior_annotations a "
                             "JOIN evidence e ON e.id=a.evidence_id WHERE e.speaker_id=?", (row["speaker_id"],))
    feature_name = "reviewed_"+kind+"_rate"
    event_ids = {a["evidence_id"] for a in annotations if a["kind"] == kind}
    with store.connect() as db:
        db.execute("DELETE FROM features WHERE speaker_id=? AND name=?", (row["speaker_id"], feature_name))
        store.insert("features", dict(session_id=row["session_id"], speaker_id=row["speaker_id"], name=feature_name,
                     value=len(event_ids)/session["duration"]*600, unit="annotated events/10min", source="human annotation; partial coverage, not population truth",
                     confidence="low", status="reviewed_partial", denominator=session["duration"]), db)
        for annotation in annotations:
            if annotation["kind"] != kind:
                continue
            context = json.loads(annotation["context"])
            context.update(topic=annotation["topic"], phase=annotation["phase"], annotation_reviewer=annotation["reviewer_id"],
                           interaction_type=kind, target=annotation["target_speaker_id"], annotation_notes=annotation["notes"])
            db.execute("UPDATE evidence SET context=? WHERE id=?", (encode(context), annotation["evidence_id"]))
        if target:
            duplicate = db.execute("SELECT id FROM interactions WHERE evidence_id=? AND kind=? AND target=?", (row["id"], "reviewed_"+kind, target)).fetchone()
            if not duplicate:
                store.insert("interactions", dict(id=uid(), session_id=row["session_id"], source=row["speaker_id"], target=target,
                             kind="reviewed_"+kind, start=row["start"], evidence_id=row["id"], status="reviewed_partial"), db)
    store.invalidate()
    speaker = store.one("SELECT * FROM speakers WHERE id=?", (row["speaker_id"],))
    generate_traits(store, session, speaker, store.rows("SELECT * FROM features WHERE speaker_id=?", (speaker["id"],)),
                    store.rows("SELECT * FROM evidence WHERE speaker_id=?", (speaker["id"],)))
    return dict(status="saved", feature=feature_name, distinct_events=len(event_ids), coverage="Partial manual annotations; no exhaustive-rate claim")
