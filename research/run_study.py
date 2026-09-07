from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .dataset import assemble_feature_windows
from .evaluation import SplitConfig, assign_participants, evaluate_modalities, write_evaluation_artifacts
from .report import write_markdown_report
from .schema import validate_session_metadata


def run(
    *,
    physiology_path: Path,
    speech_path: Path,
    context_path: Path,
    metadata_path: Path,
    output_dir: Path,
    dataset_version: str,
    model_version: str,
    seed: int = 42,
    external_paths: tuple[Path, Path, Path] | None = None,
) -> None:
    source_paths = [physiology_path, speech_path, context_path, metadata_path]
    windows = assemble_feature_windows(
        pd.read_csv(physiology_path),
        pd.read_csv(speech_path),
        pd.read_csv(context_path),
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    validate_metadata_coverage(windows, metadata)

    external_windows = None
    if external_paths is not None:
        source_paths.extend(external_paths)
        external_windows = assemble_feature_windows(*(pd.read_csv(path) for path in external_paths))

    assignments = assign_participants(windows, SplitConfig(seed=seed))
    report, predictions = evaluate_modalities(
        windows,
        assignments,
        external_windows=external_windows,
        bootstrap_iterations=1_000,
        seed=seed,
    )
    report["dataset_version"] = dataset_version
    report["model_version"] = model_version
    write_evaluation_artifacts(output_dir, report, predictions, assignments, windows)
    write_markdown_report(output_dir / "REPORT.md", report, dataset_version=dataset_version, model_version=model_version)
    run_record = {
        "dataset_version": dataset_version,
        "model_version": model_version,
        "seed": seed,
        "source_sha256": {str(path): _sha256(path) for path in source_paths},
        "external_validation_status": report["external_validation"]["status"],
    }
    (output_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_metadata_coverage(windows: pd.DataFrame, records: Any) -> None:
    if not isinstance(records, list) or not records:
        raise ValueError("metadata file must contain a non-empty JSON array")
    validated = [validate_session_metadata(record) for record in records]
    metadata_keys = {(item["participant_id"], item["session_id"]) for item in validated}
    if len(metadata_keys) != len(validated):
        raise ValueError("metadata contains duplicate participant and session records")
    window_keys = set(zip(windows["participant_id"].astype(str), windows["session_id"].astype(str), strict=True))
    missing = sorted(window_keys - metadata_keys)
    extra = sorted(metadata_keys - window_keys)
    if missing or extra:
        raise ValueError(f"metadata coverage mismatch; missing={missing}, extra={extra}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a participant-separated PSYCON research comparison.")
    parser.add_argument("--physiology", type=Path, required=True)
    parser.add_argument("--speech", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--external-physiology", type=Path)
    parser.add_argument("--external-speech", type=Path)
    parser.add_argument("--external-context", type=Path)
    arguments = parser.parse_args()
    external = [arguments.external_physiology, arguments.external_speech, arguments.external_context]
    if any(external) and not all(external):
        parser.error("all three external modality paths are required together")
    return arguments


def main() -> None:
    arguments = _parse_args()
    external_paths = None
    if arguments.external_physiology is not None:
        external_paths = (arguments.external_physiology, arguments.external_speech, arguments.external_context)
    run(
        physiology_path=arguments.physiology,
        speech_path=arguments.speech,
        context_path=arguments.context,
        metadata_path=arguments.metadata,
        output_dir=arguments.output_dir,
        dataset_version=arguments.dataset_version,
        model_version=arguments.model_version,
        seed=arguments.seed,
        external_paths=external_paths,
    )


if __name__ == "__main__":
    main()

