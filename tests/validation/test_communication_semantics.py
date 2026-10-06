import pytest
from validation.communication_semantics import evaluate, REQUIRED_ROLES
from backend.communication.llm import enabled_event_types
from backend.communication.behaviors import VERSION


def dataset(count=50):
    return {"model_digest": "pinned-model", "analysis_version": VERSION, "examples": [
        {"id": str(i), "roles": list(REQUIRED_ROLES), "evidence": [{"id": "t0"}],
         "expected": [{"type": "objection", "evidence_ids": ["t0"]}],
         "predicted": [{"type": "objection", "evidence_ids": ["t0"]}]} for i in range(count)]}


def test_semantic_gate_requires_fifty_reviewed_exchanges_and_role_coverage():
    assert evaluate(dataset(49))["enabled_types"] == []
    value = dataset()
    assert evaluate(value)["enabled_types"] == ["objection"]
    gate = evaluate(value)
    assert enabled_event_types(gate, "pinned-model") == {"objection"}
    assert enabled_event_types(gate, "different-model") == set()
    gate["metrics"]["objection"].update(tp=8, fp=2)
    assert enabled_event_types(gate, "pinned-model") == set()
    for example in value["examples"]:
        example["roles"] = ["sales"]
    assert evaluate(value)["enabled_types"] == []


def test_false_positive_precision_controls_enabled_event_types():
    value = dataset()
    for example in value["examples"][:6]:
        example["expected"] = []
    assert evaluate(value)["metrics"]["objection"]["precision"] == .88
    assert evaluate(value)["enabled_types"] == []


def test_duplicate_exchanges_and_invented_evidence_are_rejected():
    value = dataset()
    value["examples"][1]["id"] = "0"
    with pytest.raises(ValueError):
        evaluate(value)
    value = dataset()
    value["examples"][0]["predicted"][0]["evidence_ids"] = ["invented"]
    with pytest.raises(ValueError):
        evaluate(value)
