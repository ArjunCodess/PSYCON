from __future__ import annotations

import hashlib
import json

import pytest

from backend.backup import verify_backup
from backend.config import Settings


def test_production_rejects_local_default_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PSYCON_ENV", "production")
    with pytest.raises(RuntimeError, match="Production secrets"):
        Settings.from_env()


def test_backup_manifest_verification_detects_tampering(tmp_path) -> None:
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"postgres-backup")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"database_dump": dump.name, "size": dump.stat().st_size, "sha256": hashlib.sha256(dump.read_bytes()).hexdigest()}), encoding="utf-8")
    assert verify_backup(manifest)
    dump.write_bytes(b"changed")
    assert not verify_backup(manifest)
