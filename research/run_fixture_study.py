from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform

import numpy
import pandas
import sklearn

from .evaluation import SplitConfig, assign_participants, evaluate_modalities, write_evaluation_artifacts
from .fixture import DATASET_VERSION, SEED, write_fixture_dataset
from .report import write_markdown_report


MODEL_VERSION = "week5-fixture-model-1.0.0"


def run(dataset_dir: Path, output_dir: Path) -> None:
    windows = write_fixture_dataset(dataset_dir)
    assignments = assign_participants(windows, SplitConfig(seed=SEED))
    report, predictions = evaluate_modalities(windows, assignments, bootstrap_iterations=500, seed=SEED)
    report["dataset_version"] = DATASET_VERSION
    report["model_version"] = MODEL_VERSION
    write_evaluation_artifacts(output_dir, report, predictions, assignments, windows)
    write_markdown_report(output_dir / "REPORT.md", report, dataset_version=DATASET_VERSION, model_version=MODEL_VERSION)
    run_record = {
        "command": "python -m research.run_fixture_study",
        "dataset_version": DATASET_VERSION,
        "model_version": MODEL_VERSION,
        "seed": SEED,
        "runtime": {
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "external_validation": "blocked: no separate compatible dataset supplied",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(json.dumps(run_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic PSYCON Week 5 software evaluation.")
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/research_fixture/v1"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/week5_fixture"))
    arguments = parser.parse_args()
    run(arguments.dataset_dir, arguments.output_dir)


if __name__ == "__main__":
    main()

