from types import SimpleNamespace
from unittest.mock import Mock

from backend.worker import run_worker


def test_device_worker_does_not_claim_group_jobs(monkeypatch):
    repository = Mock()
    repository.claim_job.return_value = None
    group = Mock()
    monkeypatch.setattr("backend.worker.create_app", lambda: SimpleNamespace(extensions={
        "psycon_repository": repository, "psycon_processor": Mock(), "psycon_group": group,
    }))
    run_worker(once=True, device_only=True)
    repository.heartbeat.assert_called_once()
    group.claim_job.assert_not_called()


def test_default_worker_still_claims_group_jobs(monkeypatch):
    repository = Mock()
    repository.claim_job.return_value = None
    group = Mock()
    group.claim_job.return_value = {"id": "group-job"}
    monkeypatch.setattr("backend.worker.create_app", lambda: SimpleNamespace(extensions={
        "psycon_repository": repository, "psycon_processor": Mock(), "psycon_group": group,
    }))
    run_worker(once=True)
    group.run_job.assert_called_once_with({"id": "group-job"})
