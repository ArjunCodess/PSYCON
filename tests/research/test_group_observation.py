from __future__ import annotations

from research.group_observation import (
    assign_group_splits,
    associate_turns,
    claim_is_valid,
    evaluate_group_observations,
    interpret_examples,
    playback_fragment,
    predict_examples,
    speaker_mapping_error,
    split_hash,
)


def sessions_for(ids: list[str]) -> list[dict]:
    return [{"group_session_id": session_id, "participant_ids": [session_id]} for session_id in ids]


def example(session: str, score: str, *, participant: str | None = None, item: str = "A") -> dict:
    person = participant or session
    supervised = None if score == "N/O" else score
    return {
        "group_session_id": session,
        "participant_id": person,
        "research_code": person,
        "rater_id": "rater",
        "marksheet_version": "4.0",
        "rating_role": "primary",
        "item_letter": item,
        "score": score,
        "supervised_score": supervised,
        "evidence_start_s": 1.0,
        "evidence_end_s": 4.0,
        "evidence_intervals": [],
        "context_note": "The prior point was restated and the response stayed with it.",
        "baseline_start_s": 0.0 if item in "QRST" else None,
        "baseline_end_s": 1.0 if item in "QRST" else None,
        "trigger_start_s": 1.0 if item in "QRST" else None,
        "trigger_end_s": 1.5 if item in "QRST" else None,
        "quality_state": "usable",
        "source_recording_sha256": "a" * 64,
        "language": "en",
        "topic": "water",
        "features": {
            "speaking_s": 8.0,
            "overlap_s": 0.0,
            "turn_count": 1,
            "pause_count": 0,
            "transcript_tokens": 4,
            "transcript_text": "water policy point",
            "visibility": 1.0,
            "visible_interval": (5.0, 9.0) if item == "T" else None,
        },
        "transcript_text": "water policy point",
        "component": session,
    }


def test_shared_recording_and_repeat_participant_stay_in_one_split() -> None:
    sessions = [
        {"group_session_id": "video-a", "participant_ids": ["RED", "BLUE"]},
        {"group_session_id": "video-b", "participant_ids": ["BLUE", "GREEN"]},
        {"group_session_id": "video-c", "participant_ids": ["YELLOW"]},
        {"group_session_id": "video-d", "participant_ids": ["ORANGE"]},
        {"group_session_id": "video-e", "participant_ids": ["PURPLE"]},
    ]
    assignments = assign_group_splits(sessions, seed=7)
    split_of = {row["group_session_id"]: row["split"] for row in assignments}
    assert split_of["video-a"] == split_of["video-b"]
    people = {}
    for session in sessions:
        for person in session["participant_ids"]:
            people.setdefault(person, set()).add(split_of[session["group_session_id"]])
    assert all(len(splits) == 1 for splits in people.values())


def test_no_score_is_not_zero_and_small_samples_do_not_report_model_metrics() -> None:
    rows = [example("s1", "N/O"), example("s2", "0")]
    assert rows[0]["score"] == "N/O"
    assert rows[0]["supervised_score"] is None
    sessions = sessions_for(["s1", "s2"])
    digest = split_hash(assign_group_splits(sessions, seed=1))
    report = evaluate_group_observations(rows, sessions, frozen_split_hash=digest, seed=1)
    assert report["items"]["A"]["status"] == "unavailable"
    assert report["items"]["A"]["test_metrics"] is None
    assert report["validated_model"] is False
    assert report["items"]["A"]["descriptive"]["score_counts"]["N/O"] == 1
    try:
        evaluate_group_observations(rows, sessions, frozen_split_hash="0" * 64, seed=1)
    except ValueError as exc:
        assert "frozen" in str(exc)
    else:
        raise AssertionError("a changed split hash must be rejected before test metrics")


def test_frequency_baseline_and_cited_interval_when_evidence_is_sufficient() -> None:
    session_ids = [f"s{index}" for index in range(6)]
    rows = [example(session_id, "3") for session_id in session_ids]
    sessions = sessions_for(session_ids)
    digest = split_hash(assign_group_splits(sessions, seed=3))
    report = evaluate_group_observations(rows, sessions, frozen_split_hash=digest, seed=3)
    metrics = report["items"]["A"]["test_metrics"]
    assert report["items"]["A"]["status"] == "evaluated"
    assert metrics["exact_agreement"] == 1
    assert metrics["mean_absolute_error"] == 0
    assert "weighted_kappa" in metrics
    assert "abstention_rate" in metrics
    assert report["split_assignment_sha256"] == digest
    turns = [
        {
            "cluster_label": "cluster-a",
            "start_s": 5.0,
            "end_s": 9.0,
            "confirmed_participant_id": "s0",
            "overlap": False,
            "modality": "audio",
            "text": "water policy point",
        }
    ]
    training = [example(session_id, "3") for session_id in session_ids[1:]]
    predictions = predict_examples([rows[0]], training, turns, seed=3)
    prediction = next(row for row in predictions if row["item_letter"] == "A")
    assert prediction["abstained"] is False
    assert playback_fragment(prediction) == "#t=5.000,9.000"
    forged = dict(prediction, participant_id="someone-else")
    assert claim_is_valid(forged, "s0", turns) is False


def test_unknown_mappings_and_interpretation_rules() -> None:
    turns = associate_turns(
        [{"cluster_label": "cluster-1", "start_s": 0, "end_s": 2, "proposed_participant_id": "P-OTHER"}],
        [
            {"cluster_label": "cluster-1", "participant_id": "P1", "status": "uncertain"},
            {"cluster_label": "cluster-1", "participant_id": "P2", "status": "confirmed"},
        ],
    )
    assert turns[0]["confirmed_participant_id"] is None
    assert speaker_mapping_error(
        [{"proposed_participant_id": "P2", "confirmed_participant_id": "P1"}, {"proposed_participant_id": None, "confirmed_participant_id": "P1"}]
    ) == 1
    patterns = interpret_examples(
        [
            example("s", "0"),
            example("s", "1", item="B"),
            example("s", "2", item="C"),
            example("s", "4", item="D"),
            example("s", "4", item="Q"),
        ]
    )
    letters = {row["item_letter"] for row in patterns["psychologist_session_patterns"]}
    assert letters == {"D", "Q"}
    withheld = example("s", "4", item="Q")
    withheld["baseline_start_s"] = None
    withheld["trigger_start_s"] = None
    assert interpret_examples([withheld])["psychologist_session_patterns"] == []
