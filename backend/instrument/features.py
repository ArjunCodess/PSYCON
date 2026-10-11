"""Versioned observable feature definitions. Linguistic rules are unvalidated indicators."""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict

from .store import uid, encode

SCHEMA_VERSION = "1.0.0"


def definition(description, unit, calculation, source, valid_range, confidence="moderate"):
    return dict(description=description, unit=unit, calculation=calculation, source=source,
                valid_range=valid_range, confidence=confidence, schema_version=SCHEMA_VERSION)


DICTIONARY = {
    "speaking_time": definition("Union of this speaker's diarized intervals including overlap", "seconds", "interval union duration", "diarization", [0, None]),
    "speaking_share": definition("Share of total uniquely attributed non-overlapping speaking time", "proportion", "exclusive speaker duration / all exclusive speaker duration", "diarization", [0, 1]),
    "turn_count": definition("Diarized turns after merging same-speaker intervals separated by <=0.3s", "turns", "count merged intervals", "diarization", [0, None]),
    "mean_turn_duration": definition("Average diarized turn duration", "seconds", "arithmetic mean of end-start", "diarization", [0, None]),
    "median_turn_duration": definition("Median diarized turn duration", "seconds", "median of end-start", "diarization", [0, None]),
    "longest_turn": definition("Longest diarized turn", "seconds", "maximum of end-start", "diarization", [0, None]),
    "shortest_turn": definition("Shortest diarized turn", "seconds", "minimum of end-start", "diarization", [0, None]),
    "word_count": definition("Lexical words with unambiguous speaker attribution", "words", "count Unicode lexical word tokens in attributed utterances", "transcript+alignment", [0, None]),
    "words_per_minute": definition("Attributed words per minute of this speaker's diarized time", "words/min", "word_count / speaking_time * 60", "transcript+diarization", [0, None]),
    "response_latency": definition("Mean nonnegative gap before a turn following another speaker", "seconds", "mean(start - previous end), excluding overlaps", "turns", [0, None]),
    "overlap_time": definition("Speaker time with at least one other active speaker", "seconds", "union duration where active speaker count > 1", "diarization", [0, None]),
    "interruption_candidate_rate": definition("Overlap entries lasting >=0.5s with >=0.2s remaining in another speaker's turn; intention is unknown", "events/10min", "candidate overlap entries / session duration * 600", "diarization+turns", [0, None], "low"),
    "question_rate": definition("Question punctuation indicators per minute of conversational exposure", "events/min", "utterances containing ? / session duration * 60", "transcript-rule", [0, None], "low"),
    "question_ratio": definition("Fraction of attributed utterances containing question punctuation", "proportion", "question utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "hedging_ratio": definition("Fraction of utterances containing documented hedging markers", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "assertion_ratio": definition("Fraction of utterances containing definitely, certainly, must, or obviously", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "acknowledgement_ratio": definition("Fraction of utterances with acknowledgement markers, independent of sincerity", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "proposal_rate": definition("Utterances with explicit proposal markers per minute of exposure", "events/min", "proposal marker utterances / session duration * 60", "transcript-rule", [0, None], "low"),
    "unhedged_proposal_ratio": definition("Proposal-marker utterances without hedging markers; proxy for proposal directness", "proportion", "unhedged proposals / proposal-marker utterances", "transcript-rule", [0, 1], "low"),
    "disagreement_rate": definition("Explicit disagreement-marker utterances per minute; not a measure of hostility", "events/min", "disagreement marker utterances / duration * 60", "transcript-rule", [0, None], "low"),
    "reasoning_ratio": definition("Utterances with because, since, evidence, or data shows markers", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "experimentation_ratio": definition("Utterances with test, experiment, prototype, iterate, or try markers", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "concession_ratio": definition("Utterances with explicit concession markers", "proportion", "marker-positive utterances / attributed utterances", "transcript-rule", [0, 1], "low"),
    "open_question_ratio": definition("WH-initial question indicators among punctuated questions", "proportion", "WH-initial questions / question indicators", "transcript-rule", [0, 1], "low"),
    "backchannel_candidate_rate": definition("Short acknowledgement turns <=1.5s; intent remains unverified", "events/min", "short acknowledgement turns / duration * 60", "transcript-rule+turns", [0, None], "low"),
}
UNAVAILABLE = {
    "topic_control": "Requires independently reviewed topic boundaries and control annotations",
    "topic_initiation": "Requires independently reviewed topic boundaries",
    "turn_yielding": "Prosody and intent classifier not validated",
    "turn_holding": "Prosody and intent classifier not validated",
    "interruption_rate": "Overlap is measurable; interruption intent needs human annotation",
    "paraphrasing": "Semantic annotation not validated",
    "objection_handling": "Semantic annotation not validated",
    "strategic_framing": "Semantic annotation not validated",
    "delegation": "Semantic annotation not validated",
}
PATTERNS = {
    "hedging": r"\b(i think|maybe|probably|i guess|perhaps|might|possibly)\b",
    "assertion": r"\b(definitely|certainly|must|obviously)\b",
    "acknowledgement": r"\b(i agree|agreed|i understand|good point|that makes sense|yes|right|okay|ok)\b",
    "proposal": r"\b(we should|let['’]s|i propose|i suggest|we could|how about)\b",
    "disagreement": r"\b(i disagree|i don['’]t agree|but i|however|not necessarily)\b",
    "reasoning": r"\b(because|since|evidence|data shows)\b",
    "experimentation": r"\b(test|experiment|prototype|iterate|try)\b",
    "concession": r"\b(you['’]re right|you are right|fair point|i concede|i accept)\b",
}
TOKEN = re.compile(r"\b\w+(?:['’]\w+)*\b")


def merge_turns(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["speaker"]].append(row)
    result = []
    for speaker, turns in groups.items():
        merged = []
        for row in sorted(turns, key=lambda r: r["start"]):
            if merged and row["start"] <= merged[-1]["end"] + .3:
                merged[-1]["end"] = max(merged[-1]["end"], row["end"])
            else:
                merged.append(dict(row))
        result.extend(merged)
    return sorted(result, key=lambda r: (r["start"], r["speaker"]))


def time_metrics(turns):
    points = sorted({t[k] for t in turns for k in ("start", "end")})
    speech, exclusive, overlap = Counter(), Counter(), Counter()
    for left, right in zip(points, points[1:]):
        active = {t["speaker_id"] for t in turns if t["start"] < right and t["end"] > left}
        for speaker in active:
            speech[speaker] += right-left
            (exclusive if len(active) == 1 else overlap)[speaker] += right-left
    return speech, exclusive, overlap


def extract(session, speakers, turns, utterances):
    """Each metric and candidate event remains tied to its speaker and source time."""
    duration = session["duration"]
    speech, exclusive, overlaps = time_metrics(turns)
    total_exclusive = sum(exclusive.values())
    features, evidence, interactions = [], [], []
    ordered = sorted(utterances, key=lambda r: (r["start"], r["end"]))
    evidence_by_utterance = {}
    for index, utterance in enumerate(ordered):
        if not utterance["speaker_id"]:
            continue
        context = {
            "topic": session["topic"] or "not annotated", "phase": "not annotated",
            "session_context": session["context"],
            "preceding": ordered[index-1] if index else None,
            "following": ordered[index+1] if index+1 < len(ordered) else None,
            "overlap": any(t["speaker_id"] != utterance["speaker_id"] and
                           t["start"] < utterance["end"] and t["end"] > utterance["start"] for t in turns),
            "disagreement": "candidate" if re.search(PATTERNS["disagreement"], utterance["text"], re.I) else "not annotated",
        }
        kinds = ["utterance"] + [k for k, pattern in PATTERNS.items() if re.search(pattern, utterance["text"], re.I)]
        if "?" in utterance["text"]:
            kinds.append("question")
        for kind in kinds:
            row = dict(id=uid(), session_id=session["id"], speaker_id=utterance["speaker_id"],
                       utterance_id=utterance["id"], feature=kind, start=utterance["start"], end=utterance["end"],
                       text=utterance["text"], context=encode(context), level="measured" if kind == "utterance" else "estimated",
                       confidence="moderate" if kind == "utterance" else "low")
            evidence.append(row)
            if kind == "utterance":
                evidence_by_utterance[utterance["id"]] = row["id"]
        if index and ordered[index-1]["speaker_id"] and ordered[index-1]["speaker_id"] != utterance["speaker_id"]:
            previous = ordered[index-1]
            if utterance["start"]-previous["end"] <= 30:
                kinds = ["response"]
                if "question" in [e["feature"] for e in evidence if e["utterance_id"] == previous["id"]]:
                    kinds.append("question_response_candidate")
                kinds.extend(k for k in ("acknowledgement", "disagreement") if k in
                             [e["feature"] for e in evidence if e["utterance_id"] == utterance["id"]])
                for kind in kinds:
                    interactions.append(dict(id=uid(), session_id=session["id"], source=utterance["speaker_id"],
                                             target=previous["speaker_id"], kind=kind, start=utterance["start"],
                                             evidence_id=evidence_by_utterance[utterance["id"]], status="estimated"))
    for speaker in speakers:
        sid = speaker["id"]
        own = [t for t in turns if t["speaker_id"] == sid]
        own_utterances = [u for u in utterances if u["speaker_id"] == sid]
        counts = Counter(e["feature"] for e in evidence if e["speaker_id"] == sid)
        lengths = [t["end"]-t["start"] for t in own]
        n = len(own_utterances)
        words = sum(len(TOKEN.findall(u["text"])) for u in own_utterances)
        gaps, candidates = [], 0
        for index, t in enumerate(turns):
            if t["speaker_id"] != sid:
                continue
            if index and turns[index-1]["speaker_id"] != sid and t["start"] >= turns[index-1]["end"]:
                gaps.append(t["start"]-turns[index-1]["end"])
            targets = [o for o in turns if o["speaker_id"] != sid and o["start"] < t["start"] < o["end"]-.2]
            if targets and t["end"]-t["start"] >= .5:
                candidates += 1
                for target in targets:
                    row = dict(id=uid(), session_id=session["id"], speaker_id=sid, utterance_id=None,
                               feature="overlap_entry", start=t["start"], end=min(t["end"], target["end"]),
                               text="Overlap entry; interruption intent is not established.",
                               context=encode({"target": target["speaker_id"], "session_context": session["context"]}),
                               level="estimated", confidence="low")
                    evidence.append(row)
                    interactions.append(dict(id=uid(), session_id=session["id"], source=sid, target=target["speaker_id"],
                                             kind="interruption_candidate", start=t["start"], evidence_id=row["id"], status="estimated"))
        unhedged = sum(bool(re.search(PATTERNS["proposal"], u["text"], re.I)) and
                       not re.search(PATTERNS["hedging"], u["text"], re.I) for u in own_utterances)
        values = {
            "speaking_time": speech[sid], "speaking_share": exclusive[sid]/total_exclusive if total_exclusive else None,
            "turn_count": len(own), "mean_turn_duration": statistics.mean(lengths) if lengths else None,
            "median_turn_duration": statistics.median(lengths) if lengths else None,
            "longest_turn": max(lengths) if lengths else None, "shortest_turn": min(lengths) if lengths else None,
            "word_count": words if n else None, "words_per_minute": words/speech[sid]*60 if n and speech[sid] else None,
            "response_latency": statistics.mean(gaps) if gaps else None,
            "overlap_time": overlaps[sid], "interruption_candidate_rate": candidates/duration*600,
            "question_rate": counts["question"]/duration*60 if n else None,
            "question_ratio": counts["question"]/n if n else None,
            "proposal_rate": counts["proposal"]/duration*60 if n else None,
            "disagreement_rate": counts["disagreement"]/duration*60 if n else None,
            "unhedged_proposal_ratio": unhedged/counts["proposal"] if counts["proposal"] else None,
            "open_question_ratio": sum("?" in u["text"] and bool(re.match(r"\s*(who|what|when|where|why|how)\b", u["text"], re.I))
                                       for u in own_utterances)/counts["question"] if counts["question"] else None,
            "backchannel_candidate_rate": sum(u["end"]-u["start"] <= 1.5 and bool(re.search(PATTERNS["acknowledgement"], u["text"], re.I))
                                               for u in own_utterances)/duration*60 if n else None,
        }
        for kind in ("hedging", "assertion", "acknowledgement", "reasoning", "experimentation", "concession"):
            values[kind+"_ratio"] = counts[kind]/n if n else None
        for name, value in values.items():
            spec = DICTIONARY[name]
            features.append(dict(session_id=session["id"], speaker_id=sid, name=name, value=value,
                                 unit=spec["unit"], source=spec["source"], confidence=spec["confidence"],
                                 status="unavailable" if value is None else "estimated" if "rule" in spec["source"] or "candidate" in name else "measured",
                                 denominator=duration if "rate" in name else n if "ratio" in name else None))
        for name, reason in UNAVAILABLE.items():
            features.append(dict(session_id=session["id"], speaker_id=sid, name=name, value=None, unit="not defined",
                                 source=reason, confidence="low", status="not_validated", denominator=None))
    return features, evidence, interactions
