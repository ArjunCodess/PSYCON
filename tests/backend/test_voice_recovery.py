from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from backend.group.recover_voice_job import recover


class RecoveryDatabase:
    def __init__(self, job):
        self.connection_mock = Mock()
        self.connection_mock.execute.return_value.fetchone.side_effect = [job, {"processing": {
            "nvidia_matching": {"status": "complete", "ready_voices": 3},
            "psycon_matching": {"status": "running", "ready_voices": 0},
        }}]

    @contextmanager
    def connection(self):
        yield self.connection_mock


def test_recovery_preserves_other_method_and_clears_only_interrupted_profiles():
    database = RecoveryDatabase({"job_type": "process_psycon", "group_session_id": "session"})
    assert recover(database, "job", "stopped-worker", "runtime_interrupted") == "psycon"
    calls = database.connection_mock.execute.call_args_list
    assert calls[0].args[1] == ("job", "stopped-worker")
    assert calls[2].args[1] == calls[3].args[1] == ("session", "psycon")
    processing = calls[4].args[1][0].obj
    assert processing["nvidia_matching"] == {"status": "complete", "ready_voices": 3}
    assert processing["psycon_matching"]["status"] == "failed"


def test_recovery_rejects_unmatched_or_completed_job_without_writes():
    database = RecoveryDatabase(None)
    with pytest.raises(ValueError, match="No running voice job"):
        recover(database, "job", "wrong-worker", "runtime_interrupted")
    assert database.connection_mock.execute.call_count == 1
