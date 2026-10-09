from __future__ import annotations

import hashlib
import json

import pytest

from backend.backup import verify_backup
from backend.config import Settings


def test_production_rejects_local_default_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PSYCON_ENV", "production")
    monkeypatch.setenv("PSYCON_DATABASE_URL", "postgresql://localhost/psycon")
    with pytest.raises(RuntimeError, match="Production secrets"):
        Settings.from_env()


def test_hosted_upload_limit_rejects_large_body_before_ingestion(monkeypatch):
    from backend.app import create_app
    from unittest.mock import Mock

    monkeypatch.setenv("PSYCON_MAX_GROUP_VIDEO_BYTES", "1048576")
    settings = Settings.from_env(testing=True)
    app = create_app(testing=True, settings=settings, database=Mock(), storage=Mock(), initialize=False)
    service = Mock()
    app.extensions["psycon_group"] = service
    response = app.test_client().post("/api/v1/group-auth", data=b" " * (1048576 + 1), content_type="application/json")
    assert response.status_code == 413
    service.authenticate.assert_not_called()
    assert b"Upload limit: 1 MB" in app.test_client().get("/group").data


@pytest.mark.parametrize("value", ["0", "65575", "2147483649"])
def test_invalid_upload_limit_stops_startup(monkeypatch, value):
    monkeypatch.setenv("PSYCON_MAX_GROUP_VIDEO_BYTES", value)
    with pytest.raises(ValueError, match="PSYCON_MAX_GROUP_VIDEO_BYTES"):
        Settings.from_env(testing=True)


def test_backup_manifest_verification_detects_tampering(tmp_path) -> None:
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"postgres-backup")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"database_dump": dump.name, "size": dump.stat().st_size, "sha256": hashlib.sha256(dump.read_bytes()).hexdigest()}), encoding="utf-8")
    assert verify_backup(manifest)
    dump.write_bytes(b"changed")
    assert not verify_backup(manifest)
