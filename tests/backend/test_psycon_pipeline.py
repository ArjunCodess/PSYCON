from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from backend.group import psycon, talknet
from backend.group.voice import assigned_audio_for_slot
from backend.group.memory import MemoryGroupStore
from backend.group.service import GroupError, GroupObservationService, _local_video
from ml.src.speaker_analysis import SpeakerTurn
from ml.src.speaker_analysis import DiarizationResult
from ml.src.transcription import TranscriptionResult, TranscriptionStatus
from tests.backend.test_group_workflow import MemoryStorage


def test_large_video_is_streamed_to_temporary_file() -> None:
    class Storage:
        def download_to(self, key, path):
            assert key == "recording"
            path.write_bytes(b"video")

        def get(self, _key):
            raise AssertionError("large video must not be loaded into memory")

    with _local_video(Storage(), "recording") as path:
        assert path.read_bytes() == b"video"
    assert not path.exists()


def test_4k_video_uses_synchronized_visual_scale(monkeypatch) -> None:
    class Storage:
        def download_to(self, _key, path):
            path.write_bytes(b"4k-video")

    commands = []
    def transcode(command, *, check):
        assert check
        commands.append(command)
        __import__("pathlib").Path(command[-1]).write_bytes(b"1920-video")
    monkeypatch.setattr("backend.group.service.subprocess.run", transcode)
    with _local_video(Storage(), "recording", width=3840, height=2160) as path:
        assert path.read_bytes() == b"1920-video"
    assert "scale=1920:1080:flags=fast_bilinear,fps=25" in commands[0]


def test_anonymous_turns_overlap_quality_and_short_speech() -> None:
    turns = [SpeakerTurn(0, 2, "speaker_08"), SpeakerTurn(1, 1.5, "speaker_02"),
             SpeakerTurn(3, 3.5, "speaker_08")]
    rows = psycon.clean_windows(turns, 4, [{"start_s": .6, "end_s": .9, "status": "rejected"}])
    assert all(row["slot_number"] is None for row in rows)
    assert any(row["overlap_refused_s"] == pytest.approx(.5) for row in rows)
    assert all(row["cluster_label"] is None for row in rows if row["overlap_refused_s"])
    assert all(not (row["start_s"] < .9 and row["end_s"] > .6)
               for row in rows if not row["overlap_refused_s"])
    assert all(row["cluster_label"] != "speaker_02" for row in rows if not row["overlap_refused_s"])


def test_playback_includes_original_mixed_overlap_without_training_on_it() -> None:
    turns = [SpeakerTurn(0, 2, "A"), SpeakerTurn(1, 3, "B"),
             SpeakerTurn(4, 6, "A"), SpeakerTurn(7, 9, "B")]
    rows = psycon.clean_windows(turns, 9)
    clean = [row for row in rows if row["cluster_label"]]
    for row in clean:
        row.update(status="assigned", slot_number=1 if row["cluster_label"] == "A" else 2)
        row["evidence"]["source_segments"] = ["turn-one", "turn-two"]
    samples = np.arange(9 * 16000, dtype=np.int32).astype(np.int16)
    a, a_intervals, a_mixed = psycon.playback_audio_for_slot(samples, rows, 1)
    b, b_intervals, b_mixed = psycon.playback_audio_for_slot(samples, rows, 2)
    assert a_mixed == pytest.approx(1)
    assert b_mixed == pytest.approx(1)
    assert (1., 2.) in a_intervals and (1., 2.) in b_intervals
    a_offset = round((a_intervals[0][1]-a_intervals[0][0])*16000)
    assert np.array_equal(a[a_offset:a_offset+16000], samples[16000:32000])
    assert np.array_equal(b[:16000], samples[16000:32000])
    assert sum(row["end_s"]-row["start_s"] for row in clean if row["slot_number"] == 1) < len(a)/16000
    assert len(b) > sum(row["end_s"]-row["start_s"] for row in clean if row["slot_number"] == 2)*16000
    for row in clean:
        if row["cluster_label"] == "A":
            row.update(status="unknown", slot_number=None)
    assert psycon.playback_intervals(rows, 1)[1] == 0


def test_split_cluster_uses_only_nearby_clean_turn_for_mixed_playback() -> None:
    rows = [{"id": "early", "start_s": 0., "end_s": 1.8, "cluster_label": "merged",
             "slot_number": 1, "status": "assigned", "overlap_refused_s": 0.,
             "evidence": {"source_segments": ["early"]}},
            {"id": "mixed", "start_s": 1.9, "end_s": 2.1, "cluster_label": None,
             "slot_number": None, "status": "unknown", "overlap_refused_s": .2,
             "evidence": {"clusters": ["merged", "other"]}},
            {"id": "late", "start_s": 20., "end_s": 22., "cluster_label": "merged",
             "slot_number": 2, "status": "assigned", "overlap_refused_s": 0.,
             "evidence": {"source_segments": ["late"]}}]
    assert psycon.playback_intervals(rows, 1)[1] == pytest.approx(.2)
    assert psycon.playback_intervals(rows, 2)[1] == 0
    assert rows[1]["evidence"]["playback_overlap_sources"] == [
        {"slot_number": 1, "cluster_label": "merged", "source_segment_id": "early",
         "reason": "nearby_clean_turn", "distance_s": .1}]


def test_identity_needs_repeated_video_and_consistent_voice() -> None:
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, "speaker_08")
                                for start in (0, 4, 8)], 10)
    observations = [{"cluster_label": "speaker_08", "slot_number": 2,
                     "start_s": row["start_s"], "end_s": row["end_s"],
                     "source_segment_id": row["id"], "reliable": True}
                    for row in rows[:2]]
    embeddings = {row["id"]: np.array([1., 0.]) for row in rows}
    assert psycon.link_faces(rows, observations, embeddings, {1, 2}) == {"speaker_08": 2}
    assert all(row["slot_number"] == 2 for row in rows)
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, "speaker_08")
                                for start in (0, 4, 8)], 10)
    observations = [{**item, "source_segment_id": row["id"]}
                    for item, row in zip(observations, rows)]
    embeddings = {row["id"]: np.array([1., 0.]) for row in rows}
    embeddings[rows[-1]["id"]] = np.array([0., 1.])
    psycon.link_faces(rows, observations, embeddings, {1, 2})
    assert rows[-1]["status"] == "unknown"
    assert rows[-1]["evidence"]["reason"] == "voice_inconsistent"
    observations.append({**observations[-1], "slot_number": 1})
    assert psycon.link_faces(rows, observations, embeddings, {1, 2}) == {}
    split_rows = psycon.clean_windows([
        SpeakerTurn(start, start+2, cluster)
        for cluster, starts in (("voice-A", (0, 4)), ("voice-B", (8, 12)))
        for start in starts], 14)
    split_observations = [{"cluster_label": row["cluster_label"], "slot_number":
                           1 if row["cluster_label"] == "voice-A" else 2,
                           "start_s": row["start_s"], "end_s": row["end_s"],
                           "source_segment_id": row["id"], "reliable": True} for row in split_rows]
    assert psycon.link_faces(split_rows, split_observations,
                             {row["id"]: [1., 0.] for row in split_rows}, {1, 2}) == {}


def test_consistent_video_voice_majority_excludes_one_bad_voice_sample() -> None:
    turns = [SpeakerTurn(start, start+2, "anonymous") for start in (0, 4, 8, 12, 16, 20)]
    turns.append(SpeakerTurn(25, 25.7, "anonymous"))
    rows = psycon.clean_windows(turns, 26)
    observations = [{"cluster_label": "anonymous", "slot_number": 3,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "reliable": True} for row in rows]
    embeddings = {row["id"]: np.array([1., 0.]) for row in rows[1:6]}
    embeddings[rows[0]["id"]] = np.array([0., 1.])
    assert psycon.link_faces(rows, observations, embeddings, {3}) == {"anonymous": 3}
    assert rows[0]["status"] == "unknown"
    assert rows[0]["evidence"]["reason"] == "voice_inconsistent"
    assert all(row["slot_number"] == 3 for row in rows[1:])
    assert all(rows[0]["id"] not in row["evidence"].get("source_segments", [])
               for row in rows[1:])


def test_second_pass_recovers_repeated_moderate_visual_voice_evidence() -> None:
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, "anonymous")
                                for start in (0, 4, 8)], 10)
    observations = [{"cluster_label": "anonymous", "slot_number": 4,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "score": .66, "competing_score": .35,
                     "track_continuity": .95, "face_identity_verified": True,
                     "reliable": False} for row in rows[:2]]
    embeddings = {row["id"]: np.array([1., 0.]) for row in rows}
    assert psycon.link_faces(rows, observations, embeddings, {4}) == {}
    assert psycon.recover_supported_faces(rows, observations, embeddings, {4}) == 3
    assert all(row["slot_number"] == 4 for row in rows)
    assert all(row["evidence"]["reason"] == "second_pass_visual_voice_consistent"
               for row in rows)
    assert all(len(row["evidence"]["source_segments"]) == 2 for row in rows)


def test_second_pass_preserves_conflicts_and_requires_separate_turns() -> None:
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, "anonymous")
                                for start in (0, 4, 8)], 10)
    observations = [{"cluster_label": "anonymous", "slot_number": 4,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "score": .66, "competing_score": .35,
                     "track_continuity": .95, "face_identity_verified": True,
                     "reliable": False} for row in rows[:2]]
    observations.append({**observations[0], "source_segment_id": rows[2]["id"],
                         "slot_number": 2})
    embeddings = {row["id"]: np.array([1., 0.]) for row in rows}
    rows[2].update(status="assigned", slot_number=2)
    assert psycon.recover_supported_faces(rows, observations, embeddings, {2, 4}) == 2
    assert rows[2]["slot_number"] == 2
    assert rows[2]["status"] == "assigned"
    assert rows[0]["slot_number"] == 4
    one_turn = psycon.clean_windows([SpeakerTurn(0, 2, "short")], 2)
    one_observation = [{**observations[0], "source_segment_id": one_turn[0]["id"],
                        "cluster_label": "short"}]
    assert psycon.recover_supported_faces(one_turn, one_observation,
                                          {one_turn[0]["id"]: [1., 0.]}, {4}) == 0


def test_unknown_speech_can_be_offered_for_review_without_training() -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 2, "anonymous")], 2)
    item = {"cluster_label": "anonymous", "slot_number": 4,
            "source_segment_id": rows[0]["id"], "start_s": rows[0]["start_s"],
            "end_s": rows[0]["end_s"], "score": .67, "competing_score": .3,
            "track_continuity": .95, "face_identity_verified": True,
            "mouth_activity": .6}
    assert psycon.mark_review_candidates(rows, [item], {4}) == 1
    assert rows[0]["status"] == "unknown"
    assert rows[0]["slot_number"] is None
    assert rows[0]["evidence"]["review_slot"] == 4
    assert rows[0]["evidence"]["review_source"] == "talknet_visible_face"
    rows[0]["evidence"].pop("review_slot")
    assert psycon.mark_review_candidates(rows, [{**item, "face_identity_verified": False}], {4}) == 0


def test_merged_acoustic_label_keeps_a_distinct_short_face_playable() -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 2.1, "merged"),
                                SpeakerTurn(5, 8, "merged"),
                                SpeakerTurn(12, 15, "merged")], 15)
    observations = [{"cluster_label": "merged", "slot_number": slot,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "reliable": True,
                     "score": .95, "competing_score": .2}
                    for row, slot in zip(rows, (8, 2, 2))]
    embeddings = {row["id"]: np.array([0., 1.] if slot == 8 else [1., 0.])
                  for row, slot in zip(rows, (8, 2, 2))}
    assert psycon.link_faces(rows, observations, embeddings, {2, 8}) == {"merged": 2}
    assert [row["slot_number"] for row in rows] == [8, 2, 2]
    assert rows[0]["evidence"]["reason"] == "isolated_active_speaker_playback_only"
    assert rows[0]["evidence"]["source_segments"] == [rows[0]["id"]]
    assert rows[0]["evidence"]["training_eligible"] is False
    audio, _ = assigned_audio_for_slot(np.ones(15*16000, dtype=np.int16)*1000, 16000, rows, 8)
    assert len(audio) == 0
    assert psycon.playback_intervals(rows, 8)[0]


def test_single_extremely_clear_turn_can_be_played_without_a_voice_profile() -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 2, "one-turn-speaker")], 2)
    observation = {"cluster_label": "one-turn-speaker", "slot_number": 4,
                   "source_segment_id": rows[0]["id"], "start_s": rows[0]["start_s"],
                   "end_s": rows[0]["end_s"], "reliable": True,
                   "score": .98, "competing_score": .1}
    assert psycon.link_faces(rows, [observation], {rows[0]["id"]: [1., 0.]}, {4}) == {}
    assert rows[0]["slot_number"] == 4
    assert rows[0]["evidence"]["training_eligible"] is False


def test_two_video_windows_and_voice_rescue_a_split_cluster() -> None:
    turns = [SpeakerTurn(0, 2.1, "mixed-a"),
             SpeakerTurn(5, 8, "mixed-a"), SpeakerTurn(10, 13, "mixed-a"),
             SpeakerTurn(16, 20.4, "mixed-b"),
             SpeakerTurn(24, 27, "mixed-b"), SpeakerTurn(30, 33, "mixed-b")]
    rows = psycon.clean_windows(turns, 33)
    def observation(row, slot, score, *, repeated=False):
        return {"cluster_label": row["cluster_label"], "slot_number": slot,
                "source_segment_id": row["id"], "start_s": row["start_s"],
                "end_s": row["end_s"], "reliable": True, "score": score,
                "competing_score": .2, "visual_repetition": repeated}
    observations = [observation(rows[0], 8, .95),
                    observation(rows[1], 2, .9), observation(rows[2], 2, .9),
                    observation(rows[3], 8, .69, repeated=True),
                    observation(rows[4], 5, .9), observation(rows[5], 5, .9)]
    embeddings = {row["id"]: vector for row, vector in zip(rows, (
        [1., 0., 0., 0.], [0., 0., 1., 0.], [0., 0., 1., 0.],
        [.6, .8, 0., 0.], [0., 0., 0., 1.], [0., 0., 0., 1.]))}
    assert psycon.link_faces(rows, observations, embeddings, {2, 5, 8}) == {
        "mixed-a": 2, "mixed-b": 5}
    assert [rows[index]["slot_number"] for index in (0, 3)] == [8, 8]
    assert all(rows[index]["evidence"]["reason"] == "repeated_visual_voice_consistent"
               and rows[index]["evidence"]["training_eligible"] for index in (0, 3))
    assert rows[0]["evidence"]["source_segments"] == [rows[0]["id"], rows[3]["id"]]
    embeddings[rows[3]["id"]] = [0., 1., 0., 0.]
    rows = psycon.clean_windows(turns, 33)
    observations = [{**item, "source_segment_id": rows[index]["id"]}
                    for index, item in enumerate(observations)]
    embeddings = {rows[index]["id"]: vector for index, vector in enumerate((
        [1., 0., 0., 0.], [0., 0., 1., 0.], [0., 0., 1., 0.],
        [0., 1., 0., 0.], [0., 0., 0., 1.], [0., 0., 0., 1.]))}
    psycon.link_faces(rows, observations, embeddings, {2, 5, 8})
    assert all(rows[index]["evidence"]["training_eligible"] is False for index in (0, 3))


def test_two_disjoint_moderate_visual_windows_require_same_face(monkeypatch) -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 4.5, "anonymous")], 4.5)
    row = rows[0]
    def window(start, end, slot):
        return {"source_segment_id": row["id"], "cluster_label": "anonymous",
                "slot_number": slot, "start_s": start, "end_s": end,
                "score": .68, "competing_score": .25, "track_continuity": 1.,
                "face_identity_verified": True}
    first = window(row["start_s"], row["start_s"]+1.8, 8)
    second = window(row["end_s"]-1.8, row["end_s"], 8)
    monkeypatch.setattr(talknet, "observations", lambda *_args, **_kwargs: [first, second])
    checked = psycon.active_observations(rows, [{"slot_number": 8}], b"video", np.zeros(72000, dtype=np.int16))
    assert all(item["reliable"] and item["visual_repetition"] for item in checked)
    second["slot_number"] = 7
    checked = psycon.active_observations(rows, [{"slot_number": 7}, {"slot_number": 8}],
                                         b"video", np.zeros(72000, dtype=np.int16))
    assert all(not item["reliable"] for item in checked)


def test_relative_voice_margin_preserves_distinct_video_faces() -> None:
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, cluster)
                                for cluster, starts in (("A", (0, 4)), ("B", (8, 12)))
                                for start in starts], 14)
    observations = [{"cluster_label": row["cluster_label"], "slot_number":
                     1 if row["cluster_label"] == "A" else 2,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "reliable": True} for row in rows]
    vectors = ([1., 0., 0.], [.8, .6, 0.], [.6, 0., .8], [.65, 0., .76])
    embeddings = {row["id"]: vector for row, vector in zip(rows, vectors)}
    assert psycon.link_faces(rows, observations, embeddings, {1, 2}) == {"A": 1, "B": 2}
    assert [row["slot_number"] for row in rows] == [1, 1, 2, 2]


def test_split_clusters_for_one_face_must_agree_with_each_other() -> None:
    rows = psycon.clean_windows([SpeakerTurn(start, start+2, cluster)
                                for cluster, starts in (("A", (0, 4)), ("B", (8, 12)),
                                                        ("C", (16, 20)))
                                for start in starts], 22)
    observations = [{"cluster_label": row["cluster_label"], "slot_number": 1,
                     "source_segment_id": row["id"], "start_s": row["start_s"],
                     "end_s": row["end_s"], "reliable": True} for row in rows]
    voices = {"A": [1., 0.], "B": [.7, .714], "C": [.7, -.714]}
    embeddings = {row["id"]: voices[row["cluster_label"]] for row in rows}
    assert psycon.link_faces(rows, observations, embeddings, {1}) == {}
    assert all(row["status"] == "unknown" for row in rows)


def test_local_active_speaker_checks_tracks_and_competitors(monkeypatch) -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 2, "speaker")], 2)
    row = rows[0]
    payload = {"source_segment_id": row["id"], "cluster_label": "speaker", "slot_number": 1,
               "start_s": row["start_s"], "end_s": row["end_s"], "score": .9,
               "competing_score": .1, "track_continuity": .9, "reliable": True}
    monkeypatch.setattr(talknet, "observations", lambda *_args, **_kwargs: [payload])
    boxes = [{"slot_number": 1}]
    assert psycon.active_observations(rows, boxes, b"video", np.zeros(32000, dtype=np.int16))[0]["reliable"]
    payload["competing_score"] = .8
    assert not psycon.active_observations(rows, boxes, b"video", np.zeros(32000, dtype=np.int16))[0]["reliable"]


def test_active_speaker_sampling_reaches_later_clean_turns() -> None:
    rows = psycon.clean_windows([SpeakerTurn(i*3, i*3+2, "anonymous") for i in range(30)], 90)
    selected = talknet._diverse_windows(rows, 16)
    assert len(selected) == 16
    assert len({source_id for _, _, _, source_id in selected}) == 16
    assert any(start > 70 for _, start, _, _ in selected)


def test_targeted_active_speaker_windows_and_mouth_motion(monkeypatch) -> None:
    rows = psycon.clean_windows([SpeakerTurn(0, 2, "anonymous")], 2)
    row = rows[0]
    selected = [("anonymous", row["start_s"], row["end_s"], row["id"])]
    called = []
    def detector(*_args, **kwargs):
        called.append(kwargs["selected_windows"])
        return [{"source_segment_id": row["id"], "cluster_label": "anonymous",
                 "slot_number": 1, "start_s": row["start_s"], "end_s": row["end_s"],
                 "score": .9, "competing_score": .1, "track_continuity": 1.,
                 "face_identity_verified": True}]
    monkeypatch.setattr(talknet, "observations", detector)
    result = psycon.active_observations(rows, [{"slot_number": 1}], b"video",
                                        np.zeros(32000, dtype=np.int16), windows=selected)
    assert called == [selected] and result[0]["reliable"]
    faces = np.zeros((14, 112, 112), dtype=np.uint8)
    faces[1::2, 70:90, 35:75] = 200
    assert talknet._mouth_activity(faces) > .01
    global_brightness = np.zeros_like(faces)
    global_brightness[1::2] = 200
    assert talknet._mouth_activity(global_brightness) == 0.


def test_face_identity_requires_repeated_matches_to_the_marked_person() -> None:
    assert talknet._identity_decision([(.71, .23), (.65, .16), (.68, .19)])[2]
    assert not talknet._identity_decision([(.7, -.1), (.72, -.08), (.68, -.04)])[2]
    assert not talknet._identity_decision([(.3, .15), (.32, .14), (.31, .1)])[2]
    assert not talknet._identity_decision([(.8, .2)])[2]


def test_face_identity_reacquires_a_person_after_seats_change(monkeypatch) -> None:
    import cv2

    class Detector:
        def detect(self, _frame):
            left = np.array([10, 20, 20, 20, *([0.] * 10), 2.], dtype=np.float32)
            right = np.array([70, 20, 20, 20, *([0.] * 10), 1.], dtype=np.float32)
            return None, np.stack([left, right])

    monkeypatch.setattr(cv2, "FaceDetectorYN", type("Factory", (), {
        "create": staticmethod(lambda *_args, **_kwargs: Detector())}))
    monkeypatch.setattr(talknet, "_identity_vector", lambda _model, _frame, detection:
                        np.array([1., 0.]) if detection[14] == 1 else np.array([0., 1.]))
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:40, 70:90] = 100
    frame[20:40, 10:30] = 200
    boxes = [{"slot_number": 1, "x": .1, "y": .2, "width": .2, "height": .2},
             {"slot_number": 2, "x": .7, "y": .2, "width": .2, "height": .2}]
    crops = talknet._face_crops([frame, frame], boxes, object(),
                                {1: np.array([1., 0.]), 2: np.array([0., 1.])})
    assert crops[1][3] and crops[2][3]
    assert crops[1][0].mean() < crops[2][0].mean()


def test_independent_storage_and_failed_job_never_use_other_method(monkeypatch) -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage)
    service.provision_account(label="Operator", role="operator", account_code="OP-PSYCON")
    actor = service.local_principal()
    session = "s"
    store.insert_recording({"group_session_id": session, "processing_state": "complete",
                            "audio_object_key": "audio", "object_key": "video",
                            "processing": {"nvidia_matching": {"status": "complete"}}})
    store.replace_voice_analysis(session, [{"id": "nvidia"}], [], "nvidia")
    storage.put_immutable("audio", _wav(np.zeros(16000, dtype=np.int16)), "audio/wav")
    storage.put_immutable("video", b"video", "video/mp4")
    queued = service.enqueue_psycon(actor, session)
    service.run_job(queued["job"])
    assert store.recording_for_session(session)["processing"]["psycon_matching"]["status"] == "failed"
    assert store.voice_segments_for(session, "nvidia") == [{"id": "nvidia"}]
    assert store.voice_segments_for(session, "psycon") == []
    assert store.recording_for_session(session)["processing"]["psycon_matching"]["reason"]


def test_reprocessing_invalidates_only_psycon_eligibility() -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage, extractor=lambda *_: (_ for _ in ()).throw(ValueError("bad audio")))
    store.insert_recording({"group_session_id": "s", "processing_state": "complete",
                            "object_key": "video", "processing": {
                                "psycon_matching": {"status": "complete", "version": psycon.MATCHING_VERSION},
                                "nvidia_matching": {"status": "complete"}}})
    store.replace_voice_analysis("s", [{"id": "psycon"}], [], "psycon")
    store.replace_voice_analysis("s", [{"id": "nvidia"}], [], "nvidia")
    storage.put_immutable("video", b"video", "video/mp4")
    service.run_job({"id": "retry", "group_session_id": "s", "job_type": "process_recording"})
    assert store.voice_segments_for("s", "psycon") == []
    assert store.voice_segments_for("s", "nvidia") == [{"id": "nvidia"}]
    assert store.recording_for_session("s")["processing"]["psycon_matching"]["status"] == "not_analyzed"


def test_fake_worker_persists_profiles_and_playback(monkeypatch) -> None:
    store, storage = MemoryGroupStore(), MemoryStorage()
    service = GroupObservationService(store, storage)
    service.provision_account(label="Operator", role="operator", account_code="OP-PSYCON-2")
    actor = service.local_principal()
    session = service.create_session(actor, {"participant_count": 2})["session"]["id"]
    store.replace_face_samples(session, [
        {"group_session_id": session, "slot_number": slot, "feature": [0.] * 80,
         "x": x, "y": .3, "width": .1, "height": .1}
        for slot, x in ((1, .7), (2, .2))
    ])
    samples = (1000*np.sin(2*np.pi*180*np.arange(11*16000)/16000)).astype(np.int16)
    storage.put_immutable("audio", _wav(samples), "audio/wav")
    storage.put_immutable("video", b"video", "video/mp4")
    store.insert_recording({"group_session_id": session, "processing_state": "complete",
                            "audio_object_key": "audio", "object_key": "video", "processing": {}})
    turns = (SpeakerTurn(0, 3, "voice-A"), SpeakerTurn(5, 9, "voice-A"))
    monkeypatch.setattr(psycon, "diarize", lambda _samples: DiarizationResult(turns, turns, "fake-community-1"))
    def detector(rows, _boxes, _video, _samples):
        return [{"source_segment_id": row["id"], "cluster_label": row["cluster_label"],
                 "slot_number": 2, "start_s": row["start_s"], "end_s": row["end_s"],
                 "score": .9, "reliable": True} for row in rows]
    monkeypatch.setattr(psycon, "active_observations", detector)
    class Embedder:
        engine_name = "fake-speechbrain"
        verification_threshold = .55
        def __init__(self, **_): pass
        def embed(self, *_): return np.array([1., 0.])
    class Transcriber:
        engine_name = "fake-whisper"
        def __init__(self, **_): pass
        def transcribe(self, *_):
            return TranscriptionResult(TranscriptionStatus.NO_SPEECH, "", None, 0., 0., (),
                                       self.engine_name)
    monkeypatch.setattr(psycon, "SpeechBrainEmbedder", Embedder)
    monkeypatch.setattr(psycon, "FasterWhisperTranscriber", Transcriber)
    monkeypatch.setenv("HF_TOKEN", "fake")
    job = service.enqueue_psycon(actor, session)["job"]
    service.run_job(job)
    details = service.face_voice_details(actor, session, "psycon")
    assert details["voice_matching"]["status"] == "complete"
    assert details["people"][1]["voice"]["status"] == "ready"
    assert details["people"][0]["voice"]["status"] == "insufficient_speech"
    assert details["people"][1]["combined_feature_ready"]
    assert details["voice_matching"]["regular_turns"][0]["speaker_id"] == "voice-A"
    assert len(details["speaking_timeline"]) == 2
    with wave.open(io.BytesIO(service.face_voice_audio(actor, session, 2, "psycon"))) as clip:
        assert clip.getnframes() == round(details["people"][1]["voice"]["usable_seconds"]*16000)
    with pytest.raises(GroupError):
        service.face_voice_audio(actor, session, 1, "psycon")
    monkeypatch.setattr("backend.group.voice._embedding_available", lambda: False)
    selected = details["speaking_timeline"][0]
    service.review_psycon_interval(actor, session, {"segment_id": selected["id"],
                                                    "slot_number": 1, "note": "Visible speaker at 0 s"})
    corrected = service.face_voice_details(actor, session, "psycon")
    assert corrected["speaking_timeline"][0]["slot_number"] == 1
    assert corrected["speaking_timeline"][1]["status"] == "unknown"
    assert corrected["people"][0]["voice"]["status"] == "insufficient_speech"
    with wave.open(io.BytesIO(service.face_voice_audio(actor, session, 1, "psycon"))) as clip:
        assert clip.getnframes() > 0
    split = store.voice_segments_for(session, "psycon")
    split[0]["evidence"]["voice_embedding"] = [0., 1.]
    split[1].update(status="assigned", slot_number=2)
    split[1]["evidence"].update(reason="active_speaker_and_voice_consistent",
                                voice_embedding=[1., 0.], source_segments=[split[1]["id"], "other"])
    store.replace_voice_analysis(session, split, store.voice_profiles_for(session, "psycon"), "psycon")
    service.review_psycon_interval(actor, session, {"segment_id": split[0]["id"],
                                                   "slot_number": 1, "note": "Different voice and visible face"})
    preserved = service.face_voice_details(actor, session, "psycon")["speaking_timeline"]
    assert preserved[1]["slot_number"] == 2
    assert preserved[1]["status"] == "assigned"
    split = store.voice_segments_for(session, "psycon")
    split.append(psycon._row(9.1, 9.5, None, "overlapping_speakers", .4,
                             ["voice-A", "other"], None))
    psycon.mark_playback_overlap(split)
    store.replace_voice_analysis(session, split, store.voice_profiles_for(session, "psycon"), "psycon")
    clean, _ = assigned_audio_for_slot(samples, 16000, split, 2)
    with wave.open(io.BytesIO(service.face_voice_audio(actor, session, 2, "psycon"))) as clip:
        assert clip.getnframes() == len(clean) + round(.4 * 16000)
    assert service.face_voice_details(actor, session, "psycon")["people"][1]["mixed_overlap_seconds"] == pytest.approx(.4)
    for row in split:
        if row.get("slot_number") == 1:
            row["evidence"]["training_eligible"] = False
    profiles = store.voice_profiles_for(session, "psycon")
    for profile in profiles:
        if profile["slot_number"] == 1:
            profile.update(usable_seconds=0., status="insufficient_speech")
    store.replace_voice_analysis(session, split, profiles, "psycon")
    with wave.open(io.BytesIO(service.face_voice_audio(actor, session, 1, "psycon"))) as clip:
        assert clip.getnframes() > 0
    assert service.face_voice_details(actor, session, "psycon")["people"][0]["voice"]["usable_seconds"] == 0
    split[0].update(status="unknown", slot_number=None)
    split[0]["evidence"]["review_slot"] = 1
    store.replace_voice_analysis(session, split, profiles, "psycon")
    with wave.open(io.BytesIO(service.face_voice_audio(actor, session, 1, "psycon"))) as clip:
        assert clip.getnframes() == round((split[0]["end_s"]-split[0]["start_s"])*16000)


def _wav(samples):
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(samples.tobytes())
    return output.getvalue()
