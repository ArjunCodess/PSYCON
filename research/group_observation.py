"""Evidence-backed group observation models.

The binary stress comparison in ``research.evaluation`` is a separate path.
This module scores marksheet items A–T as 0–4 or N/O and keeps every person
in a shared recording inside one split.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score

from backend.group.rubric import (
    ITEM_ACTION,
    ITEM_LETTERS,
    ITEM_MODALITY,
    MARKSHEET_VERSION,
    MODEL_VERSION,
    PRESSURE_ITEMS,
    PROTOCOL_VERSION,
    SCORE_MEANING,
    SCORING_RULES_VERSION,
)


MIN_INDEPENDENT_GROUPS = 5
MIN_NONZERO_EXAMPLES = 5
ABSTAIN = "insufficient_evidence"


def associate_turns(turns: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply reviewed mappings. Unknown, uncertain, and conflicts stay unknown."""
    current: dict[str, dict[str, Any]] = {}
    conflicts = set()
    for mapping in mappings:
        label = mapping["cluster_label"]
        if label in current and current[label].get("participant_id") != mapping.get("participant_id"):
            conflicts.add(label)
        current[label] = mapping
    associated = []
    for turn in turns:
        mapping = current.get(turn["cluster_label"])
        confirmed = None
        if mapping and turn["cluster_label"] not in conflicts and mapping.get("status") == "confirmed":
            confirmed = mapping.get("participant_id")
        row = dict(turn)
        row["confirmed_participant_id"] = confirmed
        row["mapping_status"] = None if mapping is None else mapping.get("status")
        associated.append(row)
    return associated


def build_training_examples(
    *,
    group_session_id: str,
    recording_sha256: str,
    quality_state: str,
    participants: list[dict[str, Any]],
    marksheets: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    language: str,
    topic: str,
) -> list[dict[str, Any]]:
    """One example per participant, item, and submitted rating.

    A timestamp supports that rating. It does not create extra labels, and
    N/O is never rewritten as zero.
    """
    by_participant = {participant["id"]: participant for participant in participants if not participant.get("withdrawn_at")}
    examples = []
    for sheet in marksheets:
        participant = by_participant.get(sheet["participant_id"])
        if participant is None or sheet.get("state") != "submitted":
            continue
        if sheet.get("rating_role") not in {"primary", "adjudicated"}:
            continue
        features = _participant_features(participant["id"], turns)
        for item in sheet["items"]:
            score = item.get("score")
            if score is None:
                continue
            if score == "N/O":
                supervised_score = None
            elif score in {"0", "1", "2", "3", "4"}:
                supervised_score = score
            else:
                raise ValueError(f"item {item['item_letter']} has an unsupported score")
            evidence = [interval for interval in item.get("intervals") or [] if interval["kind"] == "evidence"]
            baseline = [interval for interval in item.get("intervals") or [] if interval["kind"] == "baseline"]
            trigger = [interval for interval in item.get("intervals") or [] if interval["kind"] == "trigger"]
            examples.append(
                {
                    "group_session_id": group_session_id,
                    "participant_id": participant["id"],
                    "research_code": participant.get("research_code"),
                    "rater_id": sheet["rater_id"],
                    "marksheet_version": sheet.get("marksheet_version") or MARKSHEET_VERSION,
                    "rating_role": sheet["rating_role"],
                    "item_letter": item["item_letter"],
                    "score": score,
                    "supervised_score": supervised_score,
                    "evidence_start_s": None if not evidence else float(evidence[0]["start_s"]),
                    "evidence_end_s": None if not evidence else float(evidence[0]["end_s"]),
                    "evidence_intervals": evidence,
                    "context_note": _context_note(item),
                    "baseline_start_s": None if not baseline else float(baseline[0]["start_s"]),
                    "baseline_end_s": None if not baseline else float(baseline[0]["end_s"]),
                    "trigger_start_s": None if not trigger else float(trigger[0]["start_s"]),
                    "trigger_end_s": None if not trigger else float(trigger[0]["end_s"]),
                    "quality_state": quality_state,
                    "source_recording_sha256": recording_sha256,
                    "language": language,
                    "topic": topic,
                    "features": features,
                    "transcript_text": features["transcript_text"],
                }
            )
    return examples


def interpret_examples(examples: list[dict[str, Any]]) -> dict[str, Any]:
    human = []
    for example in examples:
        if example["rating_role"] != "primary":
            continue
        decision = _interpret_score(example)
        if decision == "session_pattern":
            human.append(
                {
                    "participant_id": example["participant_id"],
                    "item_letter": example["item_letter"],
                    "score": example["score"],
                    "evidence_start_s": example["evidence_start_s"],
                    "evidence_end_s": example["evidence_end_s"],
                    "decision": decision,
                }
            )
    return {"psychologist_session_patterns": human, "model_session_patterns": []}


def assign_group_splits(
    sessions: list[dict[str, Any]],
    *,
    seed: int = 42,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> list[dict[str, str]]:
    """Assign connected session groups so a shared video cannot leak across splits."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a non-empty test split")
    grouped = _components(sessions)
    roots = sorted(grouped, key=lambda root: min(grouped[root]))
    rng = np.random.default_rng(seed)
    order = np.array(roots, dtype=object)
    rng.shuffle(order)
    train_count = max(1, int(np.floor(len(order) * train_fraction))) if len(order) >= 3 else len(order)
    validation_count = max(1, int(np.floor(len(order) * validation_fraction))) if len(order) >= 3 else 0
    if len(order) >= 3 and train_count + validation_count >= len(order):
        validation_count = 1
        train_count = len(order) - 2
    assignments = []
    for index, root in enumerate(order):
        if len(order) < 3 or index < train_count:
            split = "train"
        elif index < train_count + validation_count:
            split = "validation"
        else:
            split = "test"
        for session_id in sorted(grouped[root]):
            assignments.append({"group_session_id": session_id, "split": split, "component": root})
    _assert_no_leakage(sessions, assignments)
    return assignments


def split_hash(assignments: list[dict[str, str]]) -> str:
    canonical = [{"group_session_id": row["group_session_id"], "split": row["split"]} for row in assignments]
    canonical.sort(key=lambda row: row["group_session_id"])
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_group_observations(
    examples: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    *,
    frozen_split_hash: str,
    seed: int = 42,
    code_revision: str = "unknown",
    consent_version: str = "group-consent-2.0",
) -> dict[str, Any]:
    """Score held-out groups only after the caller supplies the frozen split hash."""
    assignments = assign_group_splits(sessions, seed=seed)
    digest = split_hash(assignments)
    if digest != frozen_split_hash:
        raise ValueError("split hash does not match the frozen assignment")
    by_session = {row["group_session_id"]: row["split"] for row in assignments}
    prepared = []
    for example in examples:
        if example["group_session_id"] not in by_session:
            raise ValueError("every rated session needs a split assignment")
        row = dict(example)
        row["split"] = by_session[example["group_session_id"]]
        row["component"] = next(item["component"] for item in assignments if item["group_session_id"] == example["group_session_id"])
        prepared.append(row)
    items = {}
    for letter in ITEM_LETTERS:
        rows = [row for row in prepared if row["item_letter"] == letter and row["rating_role"] == "primary"]
        items[letter] = _evaluate_item(letter, rows, seed=seed)
    recording_hashes = sorted({row["source_recording_sha256"] for row in prepared})
    return {
        "protocol_version": PROTOCOL_VERSION,
        "marksheet_version": MARKSHEET_VERSION,
        "model_version": MODEL_VERSION,
        "scoring_rules_version": SCORING_RULES_VERSION,
        "consent_version": consent_version,
        "code_revision": code_revision,
        "split_assignment_sha256": digest,
        "recording_hashes": recording_hashes,
        "dataset_manifest_sha256": _manifest_hash(prepared, digest),
        "validated_model": any(item["status"] == "evaluated" for item in items.values()),
        "items": items,
    }


def predict_examples(
    target_examples: list[dict[str, Any]],
    training_examples: list[dict[str, Any]],
    turns: list[dict[str, Any]],
    *,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Predict ordinal scores without writing over psychologist ratings."""
    predictions = []
    for letter in ITEM_LETTERS:
        targets = [row for row in target_examples if row["item_letter"] == letter and row["rating_role"] == "primary"]
        training = [row for row in training_examples if row["item_letter"] == letter and row["supervised_score"] is not None]
        gate = _gate(training + targets)
        model = None if gate is not None else _fit_baselines(training, letter, seed)
        for example in targets:
            prediction = _predict_one(example, turns, model, gate)
            if not claim_is_valid(prediction, example["participant_id"], turns):
                prediction = _abstain(example, "prediction_failed_identity_check")
            predictions.append(prediction)
    return predictions


def claim_is_valid(prediction: dict[str, Any], participant_id: str, turns: list[dict[str, Any]]) -> bool:
    if prediction["participant_id"] != participant_id:
        return False
    if prediction["abstained"]:
        return prediction["evidence_start_s"] is None and prediction["evidence_end_s"] is None
    start = prediction["evidence_start_s"]
    end = prediction["evidence_end_s"]
    if start is None or end is None or not (end > start):
        return False
    if prediction["item_letter"] == "T":
        return prediction.get("evidence_source") == "seat_visibility"
    return any(
        turn.get("confirmed_participant_id") == participant_id and turn["start_s"] == start and turn["end_s"] == end
        for turn in turns
    )


def playback_fragment(prediction: dict[str, Any]) -> str | None:
    if prediction.get("abstained") or prediction.get("evidence_start_s") is None or prediction.get("evidence_end_s") is None:
        return None
    return f"#t={prediction['evidence_start_s']:.3f},{prediction['evidence_end_s']:.3f}"


def speaker_mapping_error(turns: list[dict[str, Any]]) -> float | None:
    comparable = [
        turn
        for turn in turns
        if turn.get("proposed_participant_id") and turn.get("confirmed_participant_id")
    ]
    if not comparable:
        return None
    mistakes = sum(turn["proposed_participant_id"] != turn["confirmed_participant_id"] for turn in comparable)
    return mistakes / len(comparable)


def _predict_one(example: dict[str, Any], turns: list[dict[str, Any]], model: dict[str, Any] | None, gate: str | None) -> dict[str, Any]:
    if gate is not None or model is None:
        return _abstain(example, gate or "model_unavailable")
    if _must_abstain(example):
        return _abstain(example, "insufficient_recording_evidence")
    interval = _supporting_interval(example, turns)
    if interval is None:
        return _abstain(example, "no_verified_interval")
    label, confidence, family = _choose_prediction(example, model)
    if label == ABSTAIN:
        return _abstain(example, "low_confidence")
    account = render_account(
        item_letter=example["item_letter"],
        score=label,
        start_s=interval["start_s"],
        end_s=interval["end_s"],
        confidence=confidence,
    )
    return _prediction_row(
        example,
        label=label,
        abstained=False,
        confidence=confidence,
        account=account,
        start_s=interval["start_s"],
        end_s=interval["end_s"],
        source=interval["source"],
        family=family,
        reason=None,
    )


def render_account(*, item_letter: str, score: str, start_s: float, end_s: float, confidence: float) -> str:
    if score not in SCORE_MEANING or score == "N/O":
        raise ValueError("the account template only reports verified ordinal scores")
    action = ITEM_ACTION[item_letter]
    meaning = SCORE_MEANING[score]
    return (
        f"Item {item_letter} is scored {score} ({meaning}). "
        f"The cited moment is {start_s:.2f}s to {end_s:.2f}s. "
        f"Observed action: {action}. Confidence {confidence:.2f}."
    )


def _abstain(example: dict[str, Any], reason: str) -> dict[str, Any]:
    account = f"Item {example['item_letter']} was not scored because evidence was insufficient ({reason})."
    return _prediction_row(
        example,
        label=ABSTAIN,
        abstained=True,
        confidence=0.0,
        account=account,
        start_s=None,
        end_s=None,
        source=None,
        family=None,
        reason=reason,
    )


def _prediction_row(example, *, label, abstained, confidence, account, start_s, end_s, source, family, reason) -> dict[str, Any]:
    return {
        "group_session_id": example["group_session_id"],
        "participant_id": example["participant_id"],
        "rater_id": example["rater_id"],
        "item_letter": example["item_letter"],
        "predicted_label": label,
        "abstained": abstained,
        "confidence": confidence,
        "account": account,
        "evidence_start_s": start_s,
        "evidence_end_s": end_s,
        "evidence_source": source,
        "model_version": MODEL_VERSION,
        "model_family": family,
        "reason": reason,
        "source_recording_sha256": example["source_recording_sha256"],
        "psychologist_score": example["score"],
    }


def _supporting_interval(example: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any] | None:
    modality = ITEM_MODALITY[example["item_letter"]]
    if modality == "video":
        visibility = example["features"].get("visible_interval")
        if not visibility:
            return None
        return {"start_s": visibility[0], "end_s": visibility[1], "source": "seat_visibility"}
    owned = [
        turn
        for turn in turns
        if turn.get("confirmed_participant_id") == example["participant_id"] and turn["end_s"] > turn["start_s"]
    ]
    if not owned:
        return None
    chosen = max(owned, key=lambda turn: turn["end_s"] - turn["start_s"])
    return {"start_s": chosen["start_s"], "end_s": chosen["end_s"], "source": "confirmed_turn"}


def _must_abstain(example: dict[str, Any]) -> bool:
    modality = ITEM_MODALITY[example["item_letter"]]
    quality = example.get("quality_state")
    if modality in {"audio", "transcript", "combined"} and quality == "poor_audio":
        return True
    if modality == "video" and not example["features"].get("visible_interval"):
        return True
    if modality != "video" and example["features"].get("turn_count", 0) <= 0:
        return True
    return False


def _choose_prediction(example: dict[str, Any], model: dict[str, Any]) -> tuple[str, float, str]:
    votes = []
    frequency = model["frequency"]
    votes.append((frequency["label"], frequency["confidence"], "frequency"))
    feature = _feature_vote(example, model.get("feature"))
    if feature is not None:
        votes.append((*feature, "feature"))
    text = _text_vote(example, model.get("text"))
    if text is not None:
        votes.append((*text, "text"))
    best = max(votes, key=lambda vote: (vote[1], vote[0] == frequency["label"]))
    if best[1] < 0.34:
        return ABSTAIN, best[1], best[2]
    return best


def _feature_vote(example: dict[str, Any], feature_model: dict[str, Any] | None) -> tuple[str, float] | None:
    if feature_model is None:
        return None
    vector = np.asarray([_vector(example)], dtype=float)
    probabilities = feature_model["estimator"].predict_proba(vector)[0]
    index = int(np.argmax(probabilities))
    return feature_model["classes"][index], float(probabilities[index])


def _text_vote(example: dict[str, Any], text_model: dict[str, Any] | None) -> tuple[str, float] | None:
    if text_model is None:
        return None
    tokens = set(_tokens(example.get("transcript_text") or ""))
    if not tokens:
        return None
    scores = []
    for label, model_tokens in text_model["tokens"].items():
        overlap = len(tokens & model_tokens)
        scores.append((overlap, label))
    overlap, label = max(scores)
    if overlap <= 0:
        return None
    return label, min(0.99, overlap / max(1, len(tokens)))


def _fit_baselines(rows: list[dict[str, Any]], letter: str, seed: int) -> dict[str, Any]:
    labels = [row["supervised_score"] for row in rows]
    counts = Counter(labels)
    label, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    model: dict[str, Any] = {"frequency": {"label": label, "confidence": count / len(labels)}}
    classes = sorted(counts)
    if len(classes) >= 2 and min(counts.values()) >= 1 and len(rows) >= len(classes):
        estimator = LogisticRegression(max_iter=200, random_state=seed)
        vectors = np.asarray([_vector(row) for row in rows], dtype=float)
        try:
            estimator.fit(vectors, labels)
        except ValueError:
            estimator = None
        if estimator is not None:
            model["feature"] = {"estimator": estimator, "classes": list(estimator.classes_)}
    token_sets: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        token_sets[row["supervised_score"]].update(_tokens(row.get("transcript_text") or ""))
    if any(token_sets.values()):
        model["text"] = {"tokens": token_sets, "modality": ITEM_MODALITY[letter]}
    return model


def _vector(example: dict[str, Any]) -> list[float]:
    features = example["features"]
    modality = ITEM_MODALITY[example["item_letter"]]
    speaking = float(features.get("speaking_s") or 0)
    overlap = float(features.get("overlap_s") or 0)
    turns = float(features.get("turn_count") or 0)
    pauses = float(features.get("pause_count") or 0)
    tokens = float(features.get("transcript_tokens") or 0)
    visibility = float(features.get("visibility") or 0)
    if modality == "video":
        return [visibility, speaking]
    if modality == "audio":
        return [speaking, overlap, pauses, turns]
    if modality == "transcript":
        return [tokens, turns, speaking]
    return [speaking, overlap, turns, tokens, visibility]


def _evaluate_item(letter: str, rows: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    descriptive = _descriptive(rows)
    gate = _gate([row for row in rows if row["supervised_score"] is not None or row["score"] == "N/O"])
    supervised = [row for row in rows if row["supervised_score"] is not None]
    if gate is not None or len({row["split"] for row in supervised}) < 3:
        return {"status": "unavailable", "reason": gate or "splits_incomplete", "descriptive": descriptive, "test_metrics": None}
    train = [row for row in supervised if row["split"] == "train"]
    validation = [row for row in supervised if row["split"] == "validation"]
    test = [row for row in supervised if row["split"] == "test"]
    if not train or not test:
        return {"status": "unavailable", "reason": "empty_split", "descriptive": descriptive, "test_metrics": None}
    families = {}
    for name, predictor in (
        ("frequency", _predict_frequency),
        ("feature", _predict_feature),
        ("text", _predict_text),
    ):
        fitted = predictor(train, letter, seed)
        if validation:
            families[name] = (_mean_absolute_error(validation, _apply(fitted, validation)), fitted)
        else:
            families[name] = (0.0, fitted)
    selected_name = min(families, key=lambda name: (families[name][0], name))
    development = train + validation
    selected = {
        "frequency": _predict_frequency,
        "feature": _predict_feature,
        "text": _predict_text,
    }[selected_name](development, letter, seed)
    metrics = _score_split(test, _apply(selected, test))
    metrics["selected_family"] = selected_name
    metrics["error_slices"] = _error_slices(test, _apply(selected, test))
    return {"status": "evaluated", "reason": None, "descriptive": descriptive, "test_metrics": metrics}


def _predict_frequency(rows: list[dict[str, Any]], letter: str, seed: int):
    model = _fit_baselines(rows, letter, seed)
    label = model["frequency"]["label"]

    def predict(example: dict[str, Any]) -> str:
        if _must_abstain(example):
            return ABSTAIN
        return label

    return predict


def _predict_feature(rows: list[dict[str, Any]], letter: str, seed: int):
    model = _fit_baselines(rows, letter, seed)

    def predict(example: dict[str, Any]) -> str:
        if _must_abstain(example):
            return ABSTAIN
        vote = _feature_vote(example, model.get("feature"))
        if vote is None or vote[1] < 0.34:
            return model["frequency"]["label"] if vote is None else ABSTAIN
        return vote[0]

    return predict


def _predict_text(rows: list[dict[str, Any]], letter: str, seed: int):
    model = _fit_baselines(rows, letter, seed)

    def predict(example: dict[str, Any]) -> str:
        if _must_abstain(example):
            return ABSTAIN
        vote = _text_vote(example, model.get("text"))
        if vote is None:
            return model["frequency"]["label"]
        return vote[0]

    return predict


def _apply(predictor, rows: list[dict[str, Any]]) -> list[str]:
    return [predictor(row) for row in rows]


def _score_split(rows: list[dict[str, Any]], predicted: list[str]) -> dict[str, Any]:
    paired = [(row["supervised_score"], label) for row, label in zip(rows, predicted)]
    abstained = [label for label in predicted if label == ABSTAIN]
    judged = [(truth, label) for truth, label in paired if label != ABSTAIN]
    exact = [truth == label for truth, label in judged]
    within = [abs(int(truth) - int(label)) <= 1 for truth, label in judged]
    kappa = None
    if len(judged) > 1 and len({truth for truth, _ in judged}) > 1 and len({label for _, label in judged}) > 1:
        kappa = float(cohen_kappa_score([int(truth) for truth, _ in judged], [int(label) for _, label in judged], weights="quadratic"))
    return {
        "coverage": len(rows) / max(1, len(rows)),
        "exact_agreement": None if not exact else float(np.mean(exact)),
        "within_one_agreement": None if not within else float(np.mean(within)),
        "mean_absolute_error": _mean_absolute_error(rows, predicted),
        "weighted_kappa": kappa,
        "abstention_rate": len(abstained) / max(1, len(predicted)),
        "evidence_interval_accuracy": None,
        "speaker_mapping_error": None,
    }


def _mean_absolute_error(rows: list[dict[str, Any]], predicted: list[str]) -> float | None:
    gaps = [abs(int(row["supervised_score"]) - int(label)) for row, label in zip(rows, predicted) if label in {"0", "1", "2", "3", "4"}]
    if not gaps:
        return None
    return float(np.mean(gaps))


def _error_slices(rows: list[dict[str, Any]], predicted: list[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row, label in zip(rows, predicted):
        if label == ABSTAIN:
            continue
        correct = row["supervised_score"] == label
        facets = {
            "language": row.get("language") or "unknown",
            "topic": row.get("topic") or "unknown",
            "overlap": "overlap" if float(row["features"].get("overlap_s") or 0) > 0 else "clean",
            "seat_visibility": "visible" if float(row["features"].get("visibility") or 0) >= 0.5 else "limited",
            "recording_quality": row.get("quality_state") or "unknown",
            "speaking_opportunity": "limited" if float(row["features"].get("speaking_s") or 0) < 5 else "adequate",
        }
        for facet, value in facets.items():
            buckets[(facet, value)].append(correct)
    return [
        {"facet": facet, "value": value, "count": len(flags), "exact_agreement": float(np.mean(flags))}
        for (facet, value), flags in sorted(buckets.items())
    ]


def _gate(rows: list[dict[str, Any]]) -> str | None:
    groups = {_independence_key(row) for row in rows if row.get("supervised_score") is not None}
    nonzero = [row for row in rows if row.get("supervised_score") in {"1", "2", "3", "4"}]
    nonzero_groups = {_independence_key(row) for row in nonzero}
    if len(groups) < MIN_INDEPENDENT_GROUPS or len(nonzero) < MIN_NONZERO_EXAMPLES or len(nonzero_groups) < MIN_INDEPENDENT_GROUPS:
        return "insufficient_independent_evidence"
    return None


def _descriptive(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["score"] for row in rows)
    return {
        "ratings": len(rows),
        "score_counts": {score: counts.get(score, 0) for score in ("0", "1", "2", "3", "4", "N/O")},
        "nonzero_ratings": sum(counts.get(score, 0) for score in ("1", "2", "3", "4")),
    }


def _participant_features(participant_id: str, turns: list[dict[str, Any]]) -> dict[str, Any]:
    owned = [turn for turn in turns if turn.get("confirmed_participant_id") == participant_id and turn.get("modality") != "video"]
    speaking = sum(turn["end_s"] - turn["start_s"] for turn in owned)
    overlap = sum(turn["end_s"] - turn["start_s"] for turn in owned if turn.get("overlap"))
    text = " ".join(turn.get("text") or "" for turn in owned)
    video_turns = [
        turn
        for turn in turns
        if turn.get("modality") == "video" and turn.get("confirmed_participant_id") == participant_id and turn["end_s"] > turn["start_s"]
    ]
    visible_interval = None
    if video_turns:
        visible_interval = (min(turn["start_s"] for turn in video_turns), max(turn["end_s"] for turn in video_turns))
    return {
        "speaking_s": speaking,
        "overlap_s": overlap,
        "turn_count": len(owned),
        "pause_count": max(0, len(owned) - 1),
        "transcript_tokens": len(_tokens(text)),
        "transcript_text": text,
        "visibility": 1.0 if visible_interval is not None else 0.0,
        "visible_interval": visible_interval,
    }


def _context_note(item: dict[str, Any]) -> str:
    preceding = str(item.get("preceding_event") or "").strip()
    observed = str(item.get("observed_response") or "").strip()
    if preceding and observed:
        return f"{preceding} {observed}"
    return preceding or observed


def _interpret_score(example: dict[str, Any]) -> str:
    score = example["score"]
    if score == "N/O":
        return "no_conclusion"
    if score in {"0", "1"}:
        return "no_session_pattern"
    if example["item_letter"] in PRESSURE_ITEMS and (example["baseline_start_s"] is None or example["trigger_start_s"] is None):
        return "not_interpretable"
    if score == "2":
        return "needs_more_evidence"
    if example["evidence_start_s"] is None or example["evidence_end_s"] is None:
        return "withheld_without_citation"
    return "session_pattern"


def _components(sessions: list[dict[str, Any]]) -> dict[str, set[str]]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for session in sessions:
        session_key = f"session:{session['group_session_id']}"
        find(session_key)
        for person in session.get("participant_ids") or []:
            union(session_key, f"person:{person}")
    grouped: dict[str, set[str]] = defaultdict(set)
    for session in sessions:
        grouped[find(f"session:{session['group_session_id']}")].add(session["group_session_id"])
    return grouped


def _assert_no_leakage(sessions: list[dict[str, Any]], assignments: list[dict[str, str]]) -> None:
    split_of = {row["group_session_id"]: row["split"] for row in assignments}
    for root, members in _components(sessions).items():
        splits = {split_of[session_id] for session_id in members}
        if len(splits) != 1:
            raise ValueError(f"connected group {root} crosses splits")
    person_splits: dict[str, set[str]] = defaultdict(set)
    session_people = {session["group_session_id"]: set(session.get("participant_ids") or []) for session in sessions}
    for session_id, people in session_people.items():
        for person in people:
            person_splits[person].add(split_of[session_id])
    if any(len(splits) != 1 for splits in person_splits.values()):
        raise ValueError("a repeat participant crosses splits")


def _independence_key(row: dict[str, Any]) -> str:
    return str(row.get("component") or row["group_session_id"])


def _tokens(text: str) -> list[str]:
    return [token for token in "".join(character.lower() if character.isalnum() else " " for character in text).split() if token]


def _manifest_hash(rows: list[dict[str, Any]], split_digest: str) -> str:
    body = {
        "split": split_digest,
        "rows": [
            {
                "group_session_id": row["group_session_id"],
                "participant_id": row["participant_id"],
                "item_letter": row["item_letter"],
                "score": row["score"],
                "source_recording_sha256": row["source_recording_sha256"],
            }
            for row in sorted(rows, key=lambda item: (item["group_session_id"], item["participant_id"], item["item_letter"], item["rater_id"]))
        ],
    }
    return hashlib.sha256(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
