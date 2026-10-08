"""Causal history, exploratory role frameworks, and empirical reference construction."""
from __future__ import annotations

import hashlib
import json
import math
import statistics

import numpy as np

from .store import decode, encode, uid, now

MIN_BASELINE_SESSIONS = 5
# The scales are explicit prototype bounds, not population percentiles.
DIMENSIONS = {
    "proposal_directness": ("unhedged_proposal_ratio", 1.0),
    "question_orientation": ("question_ratio", 1.0),
    "acknowledgement": ("acknowledgement_ratio", 1.0),
    "hedging": ("hedging_ratio", 1.0),
    "proposal_generation": ("proposal_rate", 2.0),
    "reasoning_markers": ("reasoning_ratio", 1.0),
    "experimentation_markers": ("experimentation_ratio", 1.0),
    "concession_markers": ("concession_ratio", 1.0),
}
ROLE_FRAMEWORKS = {
    "Executive": dict(proposal_directness=.8, question_orientation=.3, acknowledgement=.3, hedging=.2, proposal_generation=.5, reasoning_markers=.6),
    "Builder": dict(proposal_directness=.6, question_orientation=.3, acknowledgement=.4, hedging=.4, proposal_generation=.7, reasoning_markers=.6, experimentation_markers=.6),
    "Salesperson": dict(proposal_directness=.5, question_orientation=.6, acknowledgement=.6, hedging=.3, proposal_generation=.3),
    "Negotiator": dict(proposal_directness=.6, question_orientation=.5, acknowledgement=.6, hedging=.4, proposal_generation=.5, concession_markers=.5),
}
METHOD = "100 * (1 - sqrt(sum(weight*(person-reference)^2)/sum(weight))); normalized dimensions clipped to [0,1]"


def initialize_archetypes(store):
    with store.connect() as db:
        for name, centers in ROLE_FRAMEWORKS.items():
            key = "prototype-"+name.lower()
            db.execute("INSERT INTO archetypes VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                       (key, name, "Project-defined exploratory communication framework", "PSYCON framework v1; not expert-validated",
                        None, 0, "1.0.0", "exploratory prototype", "Targets are design assumptions, not scientific ground truth. Limited to observable marker proxies. Topic control and persuasion are not measured."))
            for feature, center in centers.items():
                db.execute("INSERT INTO archetype_features VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (key, feature, center, 1., None))


def vector(features):
    values = {r["name"]: r["value"] for r in features if r["value"] is not None}
    return {name: min(1., max(0., values[feature]/scale)) for name, (feature, scale) in DIMENSIONS.items() if feature in values}


def baseline(store, session, speaker, context_specific=True):
    if not speaker["profile_id"]:
        return dict(status="unavailable", reason="Map this speaker to a person to establish history", sample_count=0, statistics={}, source_sessions=[])
    allowed = {"development": ("development",), "validation": ("development", "validation"),
               "evaluation": ("development", "validation", "evaluation"), "reference": ()}[session["split"]]
    if not allowed:
        return dict(status="unavailable", reason="Reference corpus is excluded from personal history", sample_count=0, statistics={}, source_sessions=[])
    rows = store.rows(
        "SELECT s.id,s.context,s.created_at,f.name,f.value FROM sessions s JOIN speakers p ON p.session_id=s.id "
        "JOIN features f ON f.speaker_id=p.id WHERE p.profile_id=%s AND s.recorded_at < %s "
        "AND s.status='complete' AND s.id != %s AND s.split IN ("+','.join('%s' for _ in allowed)+") AND f.value IS NOT NULL",
        (speaker["profile_id"], session["recorded_at"], session["id"], *allowed))
    if context_specific:
        rows = [r for r in rows if r["context"] == session["context"]]
    from .provenance import source_groups
    components=source_groups(store)
    rows=[r for r in rows if components[r['id']]!=components[session['id']]]
    preferred={}
    for row in sorted(rows,key=lambda r:(r['created_at'],r['id'])):preferred[components[row['id']]]=row['id']
    rows=[r for r in rows if preferred[components[r['id']]]==r['id']]
    sessions = sorted({r["id"] for r in rows})
    grouped = {}
    for r in rows:
        grouped.setdefault(r["name"], []).append(r["value"])
    statistics_out = {}
    current = {r["name"]: r["value"] for r in store.rows("SELECT * FROM features WHERE speaker_id=%s", (speaker["id"],))}
    for name, values in grouped.items():
        n = len(values)
        median = statistics.median(values)
        std = statistics.stdev(values) if n > 1 else None
        actual = current.get(name)
        percentile = sum(v <= actual for v in values)/n*100 if actual is not None else None
        deviation = None
        if n >= MIN_BASELINE_SESSIONS and actual is not None:
            # Descriptive threshold only. No significance or causal claim.
            deviation = abs(actual-statistics.mean(values)) > 2*std if std else actual != median
        statistics_out[name] = dict(mean=statistics.mean(values), median=median,
                                    variance=statistics.variance(values) if n > 1 else None, standard_deviation=std,
                                    p10=float(np.quantile(values, .1)), p90=float(np.quantile(values, .9)),
                                    sample_count=n, current=actual, empirical_percentile=percentile,
                                    ratio=actual/median if actual is not None and median else None,
                                    substantial_descriptive_deviation=deviation,
                                    confidence="low" if n < 10 else "moderate")
    result = dict(status="available" if len(sessions) >= MIN_BASELINE_SESSIONS else "insufficient_history",
                  reason=f"At least {MIN_BASELINE_SESSIONS} comparable previous sessions are required. These statistics describe observed history, not a definitive personal trait.",
                  sample_count=len(sessions), statistics=statistics_out, source_sessions=sessions,
                  context=session["context"] if context_specific else "global", cutoff=session["recorded_at"],
                  method="Strictly earlier eligible sources; latest eligible analysis per connected original/excerpt source; >2 sample SD is a descriptive flag")
    snapshot = hashlib.sha256(encode([speaker["profile_id"], session["id"], result]).encode()).hexdigest()
    store.execute("INSERT INTO baseline_profiles VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                  (snapshot, speaker["profile_id"], session["id"], result["context"], now(), result["status"], encode(sessions), encode(statistics_out)))
    with store.connect() as db:
        for name, value in statistics_out.items():
            columns = ("mean", "median", "variance", "standard_deviation", "p10", "p90", "sample_count", "empirical_percentile", "confidence")
            db.execute("INSERT INTO baseline_features VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                       (snapshot, name, *(value[k] for k in columns)))
        for source_id in sessions:
            db.execute("INSERT INTO baseline_sessions VALUES (%s,%s) ON CONFLICT DO NOTHING", (snapshot, source_id))
    return result


def compare_archetypes(store, session, speaker, features):
    person = vector(features)
    results = []
    from .provenance import source_groups
    components=source_groups(store)
    references = store.rows("SELECT * FROM archetypes ORDER BY sample_count DESC,name")
    empirical_roles = {r["name"].split(" Â· ")[0] for r in references if r["sample_count"] > 0}
    for archetype in references:
        if archetype["id"].startswith("prototype-") and archetype["name"] in empirical_roles:
            continue
        reference = store.rows("SELECT * FROM archetype_features WHERE archetype_id=%s", (archetype["id"],))
        # Never compare to a corpus containing this session or person.
        provenance = []
        for r in reference:
            if r["distribution"]:
                provenance.extend(decode(r["distribution"]).get("sources", []))
        leakage = any(components.get(p["session_id"],p["session_id"]) == components[session["id"]] or (speaker["profile_id"] and p.get("profile_id") == speaker["profile_id"])
                      or set(p.get("participant_ids", [])) & set(session["participant_ids"]) for p in provenance)
        dims = [dict(name=r["name"], person=person[r["name"]], reference=r["center"], weight=r["weight"],
                     delta=person[r["name"]]-r["center"]) for r in reference if r["name"] in person]
        available = len(dims) >= 3 and not leakage
        similarity = (100*(1-math.sqrt(sum(d["weight"]*d["delta"]**2 for d in dims)/sum(d["weight"] for d in dims)))) if available else None
        result = dict(archetype=archetype, similarity=similarity, dimensions=dims,
                      selected_dimension_count=len(dims), reference_dimension_count=len(reference),
                      method=METHOD, status="excluded_reference_leakage" if leakage else "available" if available else "insufficient_dimensions",
                      normalization=DIMENSIONS, strongest_overlap=sorted(dims, key=lambda d: abs(d["delta"]))[:3])
        results.append(result)
    return results


def build_reference(store, name, speaker_ids, source, role_labeled=False):
    if not isinstance(speaker_ids, list) or any(not isinstance(sid, str) for sid in speaker_ids):
        raise ValueError("Reference speaker IDs must be an array of strings")
    if not name.strip() or not source.strip() or len(set(speaker_ids)) < 3:
        raise ValueError("A reference needs a name, source, and at least three distinct reference speakers")
    samples, provenance = [], []
    for sid in sorted(set(speaker_ids)):
        speaker = store.one("SELECT * FROM speakers WHERE id=%s", (sid,))
        session = store.session(speaker["session_id"])
        if session["split"] != "reference" or session["status"] != "complete":
            raise ValueError("Only complete sessions assigned to the reference corpus can construct an archetype")
        samples.append(vector(store.rows("SELECT * FROM features WHERE speaker_id=%s", (sid,))))
        provenance.append(dict(session_id=session["id"], speaker_id=sid, profile_id=speaker["profile_id"], participant_ids=session["participant_ids"]))
    from .provenance import source_groups
    components=source_groups(store)
    sessions = {components[p["session_id"]] for p in provenance}
    if len(sessions) < 3:
        raise ValueError("At least three independent reference recordings are required")
    common = set.intersection(*(set(s) for s in samples))
    if len(common) < 3:
        raise ValueError("Reference requires at least three shared measured dimensions")
    existing = store.rows("SELECT * FROM archetypes WHERE name=%s AND source=%s", (name, source))
    for row in existing:
        previous = store.rows("SELECT distribution FROM archetype_features WHERE archetype_id=%s LIMIT 1", (row["id"],))
        if previous and previous[0]["distribution"]:
            source_ids = {s["speaker_id"] for s in decode(previous[0]["distribution"])["sources"]}
            if source_ids == set(speaker_ids):
                return row
    key = uid()
    with store.connect() as db:
        store.insert("archetypes", dict(id=key, name=name, description="Communication reference derived from group discussion features",
                     source=source, dataset="group discussions", sample_count=len(sessions), version="corpus-1.0.0",
                     status="empirical exploratory role reference" if role_labeled else "empirical exploratory communication cluster",
                     limitations="Small corpus; marker extraction not independently validated. Group discussions do not establish occupational identity."), db)
        for dim in sorted(common):
            # First average within recording, then across recordings, so group size does not inflate N.
            per_session = {}
            for sample, p in zip(samples, provenance):
                per_session.setdefault(components[p["session_id"]], []).append(sample[dim])
            values = [statistics.mean(v) for v in per_session.values()]
            store.insert("archetype_features", dict(archetype_id=key, name=dim, center=statistics.mean(values), weight=1.,
                         distribution=encode(dict(values=values, standard_deviation=statistics.stdev(values), sources=provenance))), db)
    store.invalidate()
    return store.one("SELECT * FROM archetypes WHERE id=%s", (key,))


TRAIT_FEATURES = {
    "proposal_rate": ("Proposal generation", "proposal"),
    "unhedged_proposal_ratio": ("Proposal directness indicators", "proposal"),
    "question_ratio": ("Question orientation", "question"),
    "hedging_ratio": ("Hedging indicators", "hedging"),
    "acknowledgement_ratio": ("Acknowledgement indicators", "acknowledgement"),
    "reasoning_ratio": ("Reasoning language indicators", "reasoning"),
    "experimentation_ratio": ("Experimentation language indicators", "experimentation"),
    "interruption_candidate_rate": ("Overlap entry pattern", "overlap_entry"),
}


def generate_traits(store, session, speaker, features, evidence):
    results = []
    with store.connect() as db:
        db.execute("DELETE FROM session_traits WHERE speaker_id=%s", (speaker["id"],))
        for f in features:
            if f["name"] not in TRAIT_FEATURES or f["value"] is None:
                continue
            title, kind = TRAIT_FEATURES[f["name"]]
            if kind.startswith("reviewed:"):
                ids = {r["evidence_id"] for r in db.execute("SELECT a.evidence_id FROM behavior_annotations a JOIN evidence e ON e.id=a.evidence_id "
                           "WHERE e.speaker_id=%s AND a.kind=%s", (speaker["id"], kind.split(":", 1)[1])).fetchall()}
                refs = [e for e in evidence if e["id"] in ids]
            else:
                refs = [e for e in evidence if e["feature"] == kind]
            if not refs:
                continue
            observation = f"{f['value']:.3g} {f['unit']} in this session; {len(refs)} supporting events."
            inference = "Evidence-supported communication inference based on observable indicators. Context and extraction errors may affect this pattern."
            if kind == "overlap_entry":
                inference = "Simultaneous speech does not establish interruption intent, aggression, or a psychological state."
            db.execute("INSERT INTO traits VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (f["name"], title, f["name"], inference))
            key = uid()
            store.insert("session_traits", dict(id=key, session_id=session["id"], speaker_id=speaker["id"], trait_id=f["name"],
                         observation=observation, inference=inference, confidence=f["confidence"]), db)
            for e in refs:
                db.execute("INSERT INTO trait_evidence VALUES (%s,%s)", (key, e["id"]))
            results.append(dict(id=key, name=title, feature=f["name"], metric=f, observation=observation,
                                inference=inference, confidence=f["confidence"], evidence_ids=[e["id"] for e in refs], sessions=[session["id"]]))
    return results
