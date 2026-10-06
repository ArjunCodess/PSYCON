"""Opt-in live PostgreSQL test; model inference remains deterministic here."""
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from backend.db import Database
from backend.communication.service import CommunicationService, Enrollment
from backend.communication.store import PostgresCommunicationStore
from ml.src.speaker_analysis import VoiceProfile


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("PSYCON_COMMUNICATION_TEST_DATABASE"), reason="Set a local test database URL")
def test_live_postgres_two_wearers_processing_patterns_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setenv("PSYCON_PROFILE_KEY", "integration-profile-encryption-key-"*2)
    database = Database(os.environ["PSYCON_COMMUNICATION_TEST_DATABASE"])
    database.migrate()
    store = PostgresCommunicationStore(database)
    class Interpreter:
        def interpret(self, evidence, context=None):
            return {"state": "unavailable", "events": []}
    def analyzer(raw, filename, digest, profile):
        return {"identity": "verified", "quality": "usable", "language": "en", "usable_speech_s": 400,
                "metrics": {"speaking_share": .3 if int(raw) < 5 else .8}, "evidence": [], "_transient": []}
    service = CommunicationService(store, spool=tmp_path/"spool", analyzer=analyzer, interpreter=Interpreter())
    users = []
    try:
        for role in ("leadership", "sales"):
            user = service.provision(role, "Automated integration test")
            users.append(user)
            service.update_profile(user["id"], {"consent": True})
            Enrollment(service, store.get("profile", user["id"])).save(VoiceProfile(np.array([1., 0.]), "fake", 3, 18))
            for i in range(8):
                stamp = (datetime.now(timezone.utc)-timedelta(days=10-i)).isoformat()
                context = {"language": "en", "conversation_type": "discussion", "setting": "work", "microphone": "test"}
                service.upload(user["id"], str(i).encode(), "test.wav", context, stamp)
                assert service.process_one()
            report = service.history(user["id"])
            assert report["patterns"][0]["evidence_count"] == 3
            assert len(service.conversations(user["id"])) == 8
            assert all(c["raw_state"] == "deleted" for c in service.conversations(user["id"]))
        # A profile lock is deliberately reentrant, as it is during deletion.
        with store.lock(users[0]["id"]):
            with store.lock(users[0]["id"]):
                service.delete_conversation(users[0]["id"], service.conversations(users[0]["id"])[0]["id"])
        assert len(service.conversations(users[1]["id"])) == 8
        assert service.history(users[0]["id"])["patterns"] == []
    finally:
        for user in users:
            for kind in ("conversation", "profile", "grant", "goal", "link", "audit", "baseline"):
                for row in store.rows(kind, user["id"]):
                    store.delete(kind, row["id"])
        database.close()
