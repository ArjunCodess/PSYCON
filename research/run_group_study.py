"""Write a versioned group-observation evaluation without using the binary study runner."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.group_observation import (
    assign_group_splits,
    evaluate_group_observations,
    split_hash,
)


def run(
    *,
    examples_path: Path,
    sessions_path: Path,
    output_dir: Path,
    turns_path: Path | None = None,
    seed: int = 42,
    code_revision: str = "unknown",
    consent_version: str = "group-consent-2.0",
) -> dict:
    examples = json.loads(examples_path.read_text(encoding="utf-8"))
    sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    turns = json.loads(turns_path.read_text(encoding="utf-8")) if turns_path else None
    output_dir.mkdir(parents=True, exist_ok=True)
    assignments = assign_group_splits(sessions, seed=seed)
    digest = split_hash(assignments)
    (output_dir / "split_assignment.json").write_text(json.dumps(assignments, indent=2), encoding="utf-8")
    report = evaluate_group_observations(
        examples,
        sessions,
        frozen_split_hash=digest,
        seed=seed,
        code_revision=code_revision,
        consent_version=consent_version,
        speaker_turns=turns,
    )
    report_path = output_dir / "evaluation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    manifest = {
        "examples_sha256": _file_hash(examples_path),
        "sessions_sha256": _file_hash(sessions_path),
        "turns_sha256": None if turns_path is None else _file_hash(turns_path),
        "split_assignment_sha256": digest,
        "evaluation_sha256": _file_hash(report_path),
        "consent_version": consent_version,
        "code_revision": code_revision,
        "recording_hashes": report["recording_hashes"],
        "dataset_manifest_sha256": report["dataset_manifest_sha256"],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return report


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate group-observation marksheets on frozen session splits")
    parser.add_argument("--examples", required=True, type=Path)
    parser.add_argument("--sessions", required=True, type=Path)
    parser.add_argument("--turns", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--code-revision", default="unknown")
    parser.add_argument("--consent-version", default="group-consent-2.0")
    args = parser.parse_args()
    run(
        examples_path=args.examples,
        sessions_path=args.sessions,
        turns_path=args.turns,
        output_dir=args.output_dir,
        seed=args.seed,
        code_revision=args.code_revision,
        consent_version=args.consent_version,
    )


if __name__ == "__main__":
    main()
