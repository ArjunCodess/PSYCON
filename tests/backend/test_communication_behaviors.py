import pytest

from backend.communication.behaviors import DEFINITIONS, OPPORTUNITIES, VERSION, measurements
from backend.communication.llm import validate_events, enabled_event_types
from backend.communication.longitudinal import summarize
from backend.communication.rubrics import ROLE_METRICS, ROLES
from backend.communication.service import CommunicationService
from backend.communication.store import MemoryCommunicationStore
from validation.communication_semantics import evaluate


def exchange():
    return [{"id": "t0", "speaker": "other_1", "start_s": 0, "end_s": 2, "text": "What does this mean?"},
            {"id": "t1", "speaker": "wearer", "start_s": 3, "end_s": 5, "text": "It means we need one more test."}]


@pytest.mark.parametrize("kind", DEFINITIONS)
def test_every_role_behavior_has_validated_evidence_shape(kind):
    refs = ["t0", "t1"] if kind in OPPORTUNITIES else ["t1"]
    evidence = exchange()
    event = {"type": kind, "evidence_ids": refs}
    assert validate_events({"events": [event]}, evidence) == [event]
    dataset = {"analysis_version": VERSION, "model_digest": "pin", "examples": [
        {"id": str(i), "roles": list(ROLES), "evidence": evidence, "expected": [event], "predicted": [event]}
        for i in range(50)]}
    assert enabled_event_types(evaluate(dataset), "pin") == {kind}


@pytest.mark.parametrize("change", ["same_speaker", "reverse", "nonadjacent", "long_gap", "long_rebuttal"])
def test_response_claim_requires_real_consecutive_opportunity(change):
    evidence = exchange()
    kind = "direct_answer"
    if change == "same_speaker":
        evidence[0]["speaker"] = "wearer"
    elif change == "reverse":
        evidence.reverse()
    elif change == "nonadjacent":
        evidence.insert(1, {"id": "extra", "speaker": "other_2", "start_s": 2, "end_s": 3})
    elif change == "long_gap":
        evidence[1]["start_s"] = 60
    else:
        kind = "concise_rebuttal"
        evidence[1]["word_count"] = 100  # Truncated text cannot bypass the original word count.
    with pytest.raises(ValueError):
        validate_events({"events": [{"type": kind, "evidence_ids": ["t0", "t1"]}]}, evidence)


def test_absence_disabled_type_and_missing_opportunity_are_distinct():
    evidence = exchange()
    events = [{"type": "question", "evidence_ids": ["t0"]}]
    metrics, counts = measurements(events, evidence, {"question", "direct_answer"})
    assert metrics == {"direct_answer_per_opportunity": 0}
    assert counts["direct_answer_per_opportunity"]["opportunities"] == 1
    assert measurements(events, evidence, {"question"}) == ({}, {})
    assert measurements([], evidence, {"question", "direct_answer"}) == ({}, {})
    events.append({"type": "direct_answer", "evidence_ids": ["t0", "t1"]})
    assert measurements(events+events, evidence, {"question", "direct_answer"})[0] == {"direct_answer_per_opportunity": 1}


def test_partial_correction_cannot_supply_full_session_rates():
    store = MemoryCommunicationStore()
    service = CommunicationService(store)
    row = {"id": "c", "profile_id": "p", "analysis": {"human_events": [], "metrics": {
        "speaking_share": .5, "acknowledgement_per_turn": .1, "direct_answer_per_opportunity": 1},
        "semantic_counts": {"direct_answer_per_opportunity": {"opportunities": 5}}}}
    store.put("conversation", row)
    assert service.history_rows("p")[0]["analysis"]["metrics"] == {"speaking_share": .5}
    assert service.history_rows("p")[0]["analysis"]["semantic_counts"] == {}


def test_semantic_opportunities_support_prior_only_role_baseline():
    rows = [{"id": str(i), "state": "complete", "occurred_at": f"2026-09-{i+1:02}T12:00:00+00:00",
             "context": {"language": "en", "conversation_type": "discussion", "microphone": "a", "setting": "work"},
             "analysis": {"identity": "verified", "quality": "usable", "usable_speech_s": 400,
                          "metrics": {"direct_answer_per_opportunity": .2 if i < 5 else .8},
                          "semantic_counts": {"direct_answer_per_opportunity": {"observed": 1, "opportunities": 5,
                              "intervals": [{"start_s": 1, "end_s": 2, "excerpt": ""}]}}}} for i in range(8)]
    report = summarize(rows, "law")
    assert report["patterns"][0]["evidence_count"] == 3
    assert report["patterns"][0]["evidence"][0]["opportunities"]["opportunities"] == 5
    rows[-1]["analysis"]["metrics"] = {}  # No question opportunity cannot count as a zero.
    assert summarize(rows, "law")["patterns"] == []
    assert set(ROLE_METRICS) == set(ROLES)


def test_old_prompt_validation_cannot_enable_new_detectors():
    dataset = {"analysis_version": "communication-semantics-1", "model_digest": "pin", "examples": []}
    with pytest.raises(ValueError, match="version"):
        evaluate(dataset)
