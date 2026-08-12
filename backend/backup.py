from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .config import Settings


def create_backup(destination: Path, settings: Settings, storage=None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump = destination / f"psycon-{stamp}.dump"
    subprocess.run(["pg_dump", "--format=custom", "--file", str(dump), settings.database_url], check=True)
    objects = []
    if storage is not None:
        object_root = destination / f"psycon-{stamp}-objects"
        for key in storage.list_keys():
            key_path = PurePosixPath(key)
            if key_path.is_absolute() or ".." in key_path.parts:
                raise ValueError("object key cannot be represented safely in a backup")
            local = object_root.joinpath(*key_path.parts)
            storage.download_to(key, local)
            objects.append({"key": key, "path": str(local.relative_to(destination)), "sha256": hashlib.sha256(local.read_bytes()).hexdigest(), "size": local.stat().st_size})
    manifest = destination / f"psycon-{stamp}.json"
    manifest.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "database_dump": dump.name, "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(), "size": dump.stat().st_size, "objects": objects}, indent=2), encoding="utf-8")
    return manifest


def verify_backup(manifest_path: Path) -> bool:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dump = manifest_path.parent / manifest["database_dump"]
    if not (dump.is_file() and dump.stat().st_size == manifest["size"] and hashlib.sha256(dump.read_bytes()).hexdigest() == manifest["sha256"]):
        return False
    return all(
        (manifest_path.parent / item["path"]).is_file()
        and (manifest_path.parent / item["path"]).stat().st_size == item["size"]
        and hashlib.sha256((manifest_path.parent / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        for item in manifest.get("objects", [])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or verify a PSYCON PostgreSQL backup")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("destination", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        settings = Settings.from_env()
        from .storage import ObjectStorage

        print(create_backup(args.destination, settings, ObjectStorage(settings)))
    elif not verify_backup(args.manifest):
        raise SystemExit("backup verification failed")
    else:
        print("backup verified")


if __name__ == "__main__":
    main()
