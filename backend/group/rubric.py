"""Marksheet version 4.0: items A–T scored 0–4 or N/O."""

from __future__ import annotations

from typing import Any


MARKSHEET_VERSION = "4.0"
CONSENT_VERSION = "group-consent-2.0"
PROTOCOL_VERSION = "group-observation-1.0.0"
PIPELINE_VERSION = "group-observation-1.0.0"
MODEL_VERSION = "group-baseline-1.0.0"
SCORING_RULES_VERSION = "group-scoring-1.0.0"

ITEM_LETTERS = tuple("ABCDEFGHIJKLMNOPQRST")
PRESSURE_ITEMS = frozenset("QRST")
ORDINAL_SCORES = frozenset({"0", "1", "2", "3", "4"})
ALLOWED_SCORES = ORDINAL_SCORES | {"N/O"}
NO_SCORE_REASONS = frozenset({"no_opportunity", "poor_recording", "uncertain_speaker_identity"})
MIN_NOTE_LENGTH = 12

# Video features are used only for items that need visible behaviour.
# Speech items use audio and transcript features. Combined items may use both.
ITEM_MODALITY = {
    "A": "transcript",
    "B": "transcript",
    "C": "transcript",
    "D": "transcript",
    "E": "transcript",
    "F": "transcript",
    "G": "transcript",
    "H": "transcript",
    "I": "audio",
    "J": "audio",
    "K": "combined",
    "L": "transcript",
    "M": "combined",
    "N": "combined",
    "O": "combined",
    "P": "transcript",
    "Q": "audio",
    "R": "audio",
    "S": "audio",
    "T": "video",
}

ITEM_ACTION = {
    "A": "a response missed the active discussion thread",
    "B": "a response did not address the preceding point",
    "C": "the contribution stayed with an earlier frame after the discussion changed",
    "D": "spoken information had to be repeated",
    "E": "the idea order was hard to follow",
    "F": "a claim was given without the requested support",
    "G": "the central point stopped before it could be understood",
    "H": "the contribution left the task without a clear link",
    "I": "speech started before a turn was available",
    "J": "overlap continued after another speaker was audible",
    "K": "speaking time continued after a cue to share the floor",
    "L": "a direct peer contribution was not acknowledged",
    "M": "behaviour changed immediately after disagreement",
    "N": "a changed response continued after the exchange moved on",
    "O": "participation fell after a challenge",
    "P": "clear feedback was not addressed",
    "Q": "speaking rate changed after an identifiable event",
    "R": "pauses or hesitations increased after an identifiable event",
    "S": "vocal delivery changed after an identifiable event",
    "T": "movement or participation changed after an identifiable event",
}

SCORE_MEANING = {
    "0": "not observed despite a fair opportunity",
    "1": "one weak or brief occurrence",
    "2": "repeated or noticeable, with limited effect",
    "3": "clear and repeated, or affects the exchange",
    "4": "sustained or strongly affects the exchange",
    "N/O": "no conclusion",
    "insufficient_evidence": "the model abstained",
}


class RubricError(ValueError):
    pass


def _intervals(item: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    found = []
    for interval in item.get("intervals") or []:
        if interval.get("kind") == kind:
            found.append(interval)
    return found


def _check_interval(interval: dict[str, Any], label: str) -> None:
    try:
        start = float(interval["start_s"])
        end = float(interval["end_s"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RubricError(f"{label} needs a start and end time") from exc
    if not (end > start >= 0):
        raise RubricError(f"{label} must have an end time after its start time")


def validate_item(item: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    """Validate one item. Drafts may omit a score; submission may not."""
    letter = str(item.get("item_letter", "")).upper()
    if letter not in ITEM_MODALITY:
        raise RubricError("item letter must be A through T")
    raw_score = item.get("score")
    if raw_score is None or raw_score == "":
        if strict:
            raise RubricError(f"item {letter} needs a score of 0, 1, 2, 3, 4, or N/O")
        return {"item_letter": letter, "score": None, "intervals": list(item.get("intervals") or [])}

    score = str(raw_score).strip().upper()
    if score == "NO":
        score = "N/O"
    if score not in ALLOWED_SCORES:
        raise RubricError(f"item {letter} must be 0, 1, 2, 3, 4, or N/O")
    if score == "N/O":
        # A missing observation is not a zero.
        reason = str(item.get("no_score_reason") or "")
        if reason not in NO_SCORE_REASONS:
            raise RubricError(
                f"item {letter} marked N/O needs a reason: no opportunity, poor recording, or uncertain speaker identity"
            )
        return {
            "item_letter": letter,
            "score": "N/O",
            "no_score_reason": reason,
            "preceding_event": "",
            "observed_response": "",
            "fair_opportunity": False,
            "intervals": [],
        }

    fair = bool(item.get("fair_opportunity"))
    preceding = str(item.get("preceding_event") or "").strip()
    observed = str(item.get("observed_response") or "").strip()
    evidence = _intervals(item, "evidence")
    baseline = _intervals(item, "baseline")
    trigger = _intervals(item, "trigger")
    for interval in evidence + baseline + trigger:
        _check_interval(interval, f"item {letter}")

    if score == "0":
        if not fair:
            raise RubricError(f"item {letter} scored 0 needs a fair opportunity; otherwise use N/O")
        if evidence or (strict and (preceding or observed)):
            pass
        return {
            "item_letter": letter,
            "score": "0",
            "no_score_reason": None,
            "preceding_event": preceding,
            "observed_response": observed,
            "fair_opportunity": True,
            "intervals": evidence,
        }

    if not evidence:
        raise RubricError(f"item {letter} scored above 0 needs at least one timestamped evidence interval")
    if len(preceding) < MIN_NOTE_LENGTH or len(observed) < MIN_NOTE_LENGTH:
        raise RubricError(f"item {letter} needs a short description of the preceding event and the observed response")
    if letter in PRESSURE_ITEMS:
        if not baseline or not trigger:
            raise RubricError(f"item {letter} needs a same-participant baseline interval and an identifiable trigger")
        evidence_start = min(float(interval["start_s"]) for interval in evidence)
        if not any(float(interval["end_s"]) <= evidence_start for interval in baseline):
            raise RubricError(f"item {letter} baseline must come from earlier in the same participant's session")
        if not any(str(interval.get("description") or "").strip() for interval in trigger):
            raise RubricError(f"item {letter} trigger needs a short description")
    kept = evidence + baseline + trigger
    return {
        "item_letter": letter,
        "score": score,
        "no_score_reason": None,
        "preceding_event": preceding,
        "observed_response": observed,
        "fair_opportunity": fair,
        "intervals": kept,
    }


def validate_marksheet(items: list[dict[str, Any]], *, strict: bool) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise RubricError("marksheet items must be a list")
    cleaned = [validate_item(item, strict=strict) for item in items]
    letters = [item["item_letter"] for item in cleaned]
    if len(letters) != len(set(letters)):
        raise RubricError("each item letter can appear only once")
    if strict:
        missing = [letter for letter in ITEM_LETTERS if letter not in letters]
        if missing:
            raise RubricError("submission is missing items " + ", ".join(missing))
        ordered = {item["item_letter"]: item for item in cleaned}
        return [ordered[letter] for letter in ITEM_LETTERS]
    return cleaned
