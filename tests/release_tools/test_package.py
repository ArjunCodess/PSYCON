from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from release_tools.package import ReleaseError, build_manifest, is_excluded, load_config, verify_manifest, write_archive


def config() -> dict:
    return {
        "schema_version": "1.0.0",
        "release_id": "test-release",
        "release_status": "candidate",
        "versions": {"protocol": "2"},
        "release_blockers": ["physical evidence missing"],
        "excluded_prefixes": ["audios/"],
        "excluded_files": [".env"],
    }


def test_manifest_hashes_only_allowed_files(tmp_path: Path) -> None:
    (tmp_path / "safe.txt").write_bytes(b"safe\n")
    (tmp_path / "audios").mkdir()
    (tmp_path / "audios" / "voice.wav").write_bytes(b"private")
    manifest = build_manifest(
        tmp_path,
        config(),
        ["safe.txt", "audios/voice.wav"],
        source_commit="abc123",
        tracked_changes=False,
        created_at_utc="2000-01-01T00:00:00Z",
    )
    assert [item["path"] for item in manifest["files"]] == ["safe.txt"]
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"safe\n").hexdigest()
    assert manifest["excluded_paths"] == ["audios/voice.wav"]


def test_manifest_verification_detects_changes(tmp_path: Path) -> None:
    target = tmp_path / "safe.txt"
    target.write_text("first", encoding="utf-8")
    manifest = build_manifest(tmp_path, config(), ["safe.txt"], source_commit="abc", tracked_changes=False)
    assert verify_manifest(tmp_path, manifest) == []
    target.write_text("other", encoding="utf-8")
    assert verify_manifest(tmp_path, manifest) == ["hash mismatch: safe.txt"]


def test_archive_is_deterministic_and_contains_manifest(tmp_path: Path) -> None:
    (tmp_path / "safe.txt").write_text("safe", encoding="utf-8")
    manifest = build_manifest(
        tmp_path,
        config(),
        ["safe.txt"],
        source_commit="abc",
        tracked_changes=False,
        created_at_utc="2000-01-01T00:00:00Z",
    )
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_archive(tmp_path, manifest, first)
    write_archive(tmp_path, manifest, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        archived_manifest = json.loads(archive.read("test-release/release-manifest.json"))
        assert archived_manifest["source_commit"] == "abc"
        assert archive.read("test-release/safe.txt") == b"safe"


def test_final_config_rejects_open_blockers(tmp_path: Path) -> None:
    value = {**config(), "release_status": "final"}
    path = tmp_path / "versions.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ReleaseError, match="final release"):
        load_config(path)


def test_private_paths_are_excluded() -> None:
    assert is_excluded("audios/student.ogg", config())
    assert is_excluded(".env", config())
    assert not is_excluded("docs/README.md", config())
