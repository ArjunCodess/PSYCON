"""Observable role behaviors and opportunity denominators, without trait inference."""
VERSION = "communication-semantics-2"
VALIDATION_VERSION = "communication-semantic-validation-2"
DEFINITIONS = {
    "disagreement": "Explicitly challenges a preceding position.",
    "criticism": "Explicitly identifies a problem with an action or proposal.",
    "objection": "Raises a concrete barrier or reservation about a proposal.",
    "acknowledgement": "Explicitly recognizes another person's point or concern.",
    "clarification": "Asks for missing meaning or detail rather than assuming it.",
    "question": "Asks another person for information or an answer.",
    "confusion": "Explicitly says an explanation was unclear or not understood.",
    "concern": "Expresses a concrete worry, symptom, need, or constraint.",
    "clear_instruction": "States a concrete action and who should perform it.",
    "structured_explanation": "States a main point and a supporting reason or example in the cited turn.",
    "unexplained_jargon": "Uses a domain-specific term without explaining it in the supplied window; abstain when audience familiarity is unknown.",
    "discovery_question": "Asks about the other person's needs, priorities, or constraints.",
    "supported_reasoning": "Connects a claim to an explicit reason or evidence; this does not establish truth.",
    "cross_question": "Asks a specific question testing another person's stated claim.",
    "concession": "Explicitly accepts part of another person's argument or narrows the speaker's position.",
    "direct_answer": "Answers the preceding question directly before elaborating.",
    "adaptation": "Responds to explicit confusion with a simpler explanation or different example.",
    "counterargument_acknowledgement": "Recognizes the preceding counterargument before responding.",
    "concise_rebuttal": "Responds to the preceding counterargument with an explicit rebuttal of at most 40 words.",
    "defensive_response": "Responds to explicit criticism by shifting blame or evading the concrete issue; no personality inference.",
    "objection_response": "Addresses the preceding concrete objection rather than merely repeating the proposal.",
    "concern_acknowledgement": "Explicitly recognizes the preceding concern before giving advice.",
}
# Paired events must cite the other person's turn first and the wearer's next turn second.
OPPORTUNITIES = {
    "direct_answer": "question",
    "adaptation": "confusion",
    "counterargument_acknowledgement": "disagreement",
    "concise_rebuttal": "disagreement",
    "defensive_response": "criticism",
    "objection_response": "objection",
    "concern_acknowledgement": "concern",
}
TURN_BEHAVIORS = {"acknowledgement", "clarification", "clear_instruction", "structured_explanation",
                  "unexplained_jargon", "discovery_question", "supported_reasoning", "cross_question", "concession"}
SEMANTIC_METRICS = {kind+"_per_turn" for kind in TURN_BEHAVIORS} | {kind+"_per_opportunity" for kind in OPPORTUNITIES}


def measurements(events, evidence, enabled):
    """Only a complete classifier pass can supply zeros; missing opportunities stay missing."""
    by_id = {e["id"]: e for e in evidence}
    positions = {e["id"]: i for i, e in enumerate(evidence)}
    own = {e["id"] for e in evidence if e.get("speaker") == "wearer" and e.get("text", "").strip()}
    metrics, counts = {}, {}
    for kind in TURN_BEHAVIORS & set(enabled):
        if not own:
            continue
        positives = {key for e in events if e["type"] == kind for key in e["evidence_ids"] if key in own}
        name = kind+"_per_turn"
        metrics[name] = len(positives)/len(own)
        counts[name] = {"observed": len(positives), "opportunities": len(own),
                        "intervals": intervals(positives or own, by_id)}
    for response, trigger in OPPORTUNITIES.items():
        if not {response, trigger} <= set(enabled):
            continue
        pairs = set()
        for event in events:
            if event["type"] != trigger:
                continue
            for key in event["evidence_ids"]:
                pos = positions[key]
                source = by_id[key]
                if source.get("speaker", "").startswith("other") and pos+1 < len(evidence):
                    following = evidence[pos+1]
                    gap = following["start_s"]-source["end_s"]
                    if following["id"] in own and 0 <= gap <= 30:
                        pairs.add((key, following["id"]))
        if not pairs:
            continue
        positives = {tuple(e["evidence_ids"]) for e in events if e["type"] == response} & pairs
        name = response+"_per_opportunity"
        metrics[name] = len(positives)/len(pairs)
        counts[name] = {"observed": len(positives), "opportunities": len(pairs),
                        "intervals": intervals({key for pair in (positives or pairs) for key in pair}, by_id)}
    return metrics, counts


def intervals(keys, evidence):
    """Retain bounded original-time references without another copy of transcript text."""
    rows = sorted((evidence[key] for key in keys), key=lambda e: (e["start_s"], e["id"]))[:3]
    return [{"id": "semantic-"+e["id"], "start_s": e["start_s"], "end_s": e["end_s"], "speaker": e["speaker"],
             "excerpt": ""} for e in rows]
