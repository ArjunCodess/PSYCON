from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Mapping
import zipfile


class ReleaseError(ValueError):
    """Raised when a release package cannot be built or verified safely."""


def load_config(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "release_id", "release_status", "versions", "release_blockers"}
    missing = sorted(required - value.keys())
    if missing:
        raise ReleaseError(f"release configuration is missing: {', '.join(missing)}")
    if value["release_status"] == "final" and value["release_blockers"]:
        raise ReleaseError("a final release cannot contain open blockers")
    return value


def git_value(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def tracked_files(root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def is_excluded(path: str, config: Mapping) -> bool:
    normalized = PurePosixPath(path).as_posix()
    return normalized in set(config.get("excluded_files", [])) or any(
        normalized.startswith(prefix) for prefix in config.get("excluded_prefixes", [])
    )


def file_record(root: Path, relative_path: str) -> dict:
    data = (root / relative_path).read_bytes()
    return {
        "path": PurePosixPath(relative_path).as_posix(),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def build_manifest(
    root: Path,
    config: Mapping,
    files: Iterable[str],
    *,
    source_commit: str,
    tracked_changes: bool,
    created_at_utc: str | None = None,
) -> dict:
    included = [path for path in sorted(files) if not is_excluded(path, config)]
    missing = [path for path in included if not (root / path).is_file()]
    if missing:
        raise ReleaseError(f"tracked files are missing: {', '.join(missing)}")
    return {
        "schema_version": config["schema_version"],
        "release_id": config["release_id"],
        "release_status": config["release_status"],
        "created_at_utc": created_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "tracked_changes_present": tracked_changes,
        "versions": dict(config["versions"]),
        "release_blockers": list(config["release_blockers"]),
        "excluded_paths": sorted(path for path in files if is_excluded(path, config)),
        "files": [file_record(root, path) for path in included],
    }


def verify_manifest(root: Path, manifest: Mapping) -> list[str]:
    errors: list[str] = []
    for record in manifest.get("files", []):
        path = root / str(record["path"])
        if not path.is_file():
            errors.append(f"missing: {record['path']}")
            continue
        actual = file_record(root, str(record["path"]))
        if actual["size"] != record["size"]:
            errors.append(f"size mismatch: {record['path']}")
        if actual["sha256"] != record["sha256"]:
            errors.append(f"hash mismatch: {record['path']}")
    return errors


def write_archive(root: Path, manifest: Mapping, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = str(manifest["release_id"])
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        _write_zip_entry(archive, f"{prefix}/release-manifest.json", manifest_bytes)
        for record in manifest["files"]:
            _write_zip_entry(archive, f"{prefix}/{record['path']}", (root / record["path"]).read_bytes())


def _write_zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, data)


def create_release(root: Path, config_path: Path, output_dir: Path) -> tuple[Path, Path, dict]:
    config = load_config(config_path)
    files = tracked_files(root)
    manifest = build_manifest(
        root,
        config,
        files,
        source_commit=git_value(root, "rev-parse", "HEAD"),
        tracked_changes=bool(git_value(root, "status", "--porcelain", "--untracked-files=no")),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive_path = output_dir / f"{config['release_id']}.zip"
    write_archive(root, manifest, archive_path)
    return manifest_path, archive_path, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or verify a PSYCON release candidate.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("release-output"))
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    if arguments.verify:
        manifest = json.loads(arguments.verify.read_text(encoding="utf-8"))
        errors = verify_manifest(root, manifest)
        print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
        raise SystemExit(0 if not errors else 1)
    config_path = arguments.config or root / "release_tools" / "versions.json"
    manifest_path, archive_path, manifest = create_release(root, config_path, arguments.output_dir)
    print(json.dumps({
        "release_id": manifest["release_id"],
        "status": manifest["release_status"],
        "blocker_count": len(manifest["release_blockers"]),
        "manifest": str(manifest_path),
        "archive": str(archive_path),
    }, indent=2))


if __name__ == "__main__":
    main()
