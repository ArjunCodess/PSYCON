"""Evaluate independently reviewed semantic exchanges before enabling event types."""
import argparse
import hashlib
import json
from pathlib import Path
from backend.communication.llm import EVENTS, validate_events

REQUIRED_ROLES = {"general", "leadership", "sales", "teaching", "law", "debate", "negotiation", "medicine", "student", "presentation"}


def evaluate(dataset):
    examples = dataset["examples"]
    if not isinstance(examples, list) or len({e["id"] for e in examples}) != len(examples):
        raise ValueError("independent exchanges need unique IDs")
    counts = {event: {"tp": 0, "fp": 0, "fn": 0} for event in EVENTS}
    roles = set()
    for example in examples:
        roles.update(example.get("roles", []))
        expected = validate_events({"events": example["expected"]}, example["evidence"])
        predicted = validate_events({"events": example["predicted"]}, example["evidence"])
        truth = {(e["type"], tuple(sorted(e["evidence_ids"]))) for e in expected}
        claims = {(e["type"], tuple(sorted(e["evidence_ids"]))) for e in predicted}
        for kind, _ in truth & claims:
            counts[kind]["tp"] += 1
        for kind, _ in claims-truth:
            counts[kind]["fp"] += 1
        for kind, _ in truth-claims:
            counts[kind]["fn"] += 1
    ready = len(examples) >= 50 and REQUIRED_ROLES <= roles
    metrics, enabled = {}, []
    for kind, value in counts.items():
        predictions = value["tp"]+value["fp"]
        precision = value["tp"]/predictions if predictions else None
        metrics[kind] = value | {"precision": precision, "predictions": predictions}
        if ready and predictions >= 10 and precision >= .9:
            enabled.append(kind)
    return {"version": "communication-semantic-validation-1", "model_digest": dataset["model_digest"],
            "dataset_sha256": hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest(),
            "exchanges": len(examples), "roles": sorted(roles), "enabled_types": enabled, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(evaluate(json.loads(args.dataset.read_text())), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
