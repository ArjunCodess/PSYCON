"""Opt-in database checks use synthetic sessions and remove them afterward."""
import os
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.db import Database
from backend.group import psycon
from backend.group.coaching import GroupCoaching
from backend.group.postgres import PostgresGroupStore
from backend.group.service import GroupObservationService
from backend.group.train import database_snapshot
from backend.group.voice import SCALAR_NAMES


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("PSYCON_COMMUNICATION_TEST_DATABASE"), reason="Set a local test database URL")
def test_database_import_feedback_training_snapshot_and_cleanup(tmp_path):
    database = Database(os.environ["PSYCON_COMMUNICATION_TEST_DATABASE"])
    database.migrate()
    store = PostgresGroupStore(database)
    service = GroupObservationService(store, Mock())
    actor = service.local_principal()
    sessions = []
    try:
        for index in range(6):
            session_id = service.create_session(actor, {"participant_count": 2, "topic": "Synthetic test", "language": "en"})["session"]["id"]
            sessions.append(session_id)
            store.insert_recording({"id": str(uuid4()), "group_session_id": session_id, "object_key": f"synthetic/{session_id}",
                                    "sha256": session_id, "filename": "test.mp4", "content_type": "video/mp4", "size_bytes": 1,
                                    "duration_s": 10, "video_codec": "h264", "audio_codec": "aac", "width": 100, "height": 100,
                                    "timestamps_readable": True, "processing_state": "complete", "failure_reason": None,
                                    "quality_state": "usable", "tool_version": "synthetic-test",
                                    "processing": {"psycon_matching": {"status": "complete", "version": psycon.MATCHING_VERSION, "model_revision": psycon.MODEL_REVISION}}})
            people = store.participants(session_id)
            store.replace_face_samples(session_id, [{"id": str(uuid4()), "group_session_id": session_id, "participant_id": p["id"],
                                                     "slot_number": p["slot_number"], "x": .1, "y": .1, "width": .2, "height": .2,
                                                     "feature": [float(index), float(p["slot_number"])] + [0.] * 78} for p in people])
            store.replace_voice_analysis(session_id, [], [{"id": str(uuid4()), "group_session_id": session_id,
                                                         "slot_number": p["slot_number"], "status": "ready", "usable_seconds": 5, "engine": "synthetic-test",
                                                         "vector": [float(p["slot_number"])] * 32, "embedding": [.1] * 192,
                                                         "metrics": {"matching_version": psycon.MATCHING_VERSION, "feature_schema": psycon.FEATURE_SCHEMA,
                                                                     "quality_gate": {"status": "model_supported"}, **{name: 1. for name in SCALAR_NAMES}}} for p in people], "psycon")
            service.import_labels(actor, session_id, "test.csv", b"participant,class,A\n1,test,1\n2,test,2\n")
        first = sessions[0]
        source = store.label_imports_for(first)[0]
        assert source["rows"][0]["scores"]["A"] == "1"
        coach = GroupCoaching(service, interpreter=lambda *_: {"state": "rule_based", "suggestions": {}})
        coach.request(actor, first, {"topic": "Shared context"})
        # Select only this test's job. Never claim another user's pending work.
        with database.connection() as connection:
            job = connection.execute("SELECT * FROM group_jobs WHERE group_session_id=%s AND job_type='group_feedback' ORDER BY created_at LIMIT 1", (first,)).fetchone()
        job = {**job, "id": str(job["id"]), "group_session_id": first}
        coach.run(job)
        assert coach.get(actor, first)["status"] == "complete"
        revision = store.feedback_for(first)["revision"]
        assert not store.save_feedback(first, {}, expected_revision="obsolete")
        assert store.feedback_for(first)["revision"] == revision
        person = store.participants(first)[0]
        service.withdraw_participant(actor, first, person["id"], {})
        assert coach.get(actor, first)["status"] == "stale"
        snapshot = database_snapshot(database)
        # Restrict model verification to the synthetic records just created.
        snapshot.training_labels = [r for r in snapshot.training_labels if r["group_session_id"] in sessions]
        assert len(snapshot.training_labels) == 11
        assert not any(r["participant_id"] == person["id"] for r in snapshot.training_labels)
        result = GroupObservationService(snapshot, None).train_faces(actor, output_dir=tmp_path / "run")
        assert result["items"][0]["status"] == "fitted"
        assert (tmp_path / "run" / "item-A.joblib").exists()
    finally:
        for session_id in sessions:
            store.delete_session(session_id)
            assert store.feedback_for(session_id) is None
            assert store.label_imports_for(session_id) == []
        database.close()
