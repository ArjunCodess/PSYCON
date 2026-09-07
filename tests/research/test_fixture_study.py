from __future__ import annotations

import json
from pathlib import Path

from research.fixture import generate_fixture_tables, write_fixture_dataset
from research.run_fixture_study import run


def test_fixture_generator_is_deterministic() -> None:
    first = generate_fixture_tables()
    second = generate_fixture_tables()
    for first_table, second_table in zip(first, second, strict=True):
        assert first_table.equals(second_table)


def test_fixture_dataset_marks_records_as_non_human(tmp_path: Path) -> None:
    windows = write_fixture_dataset(tmp_path)
    sessions = json.loads((tmp_path / "metadata" / "sessions.json").read_text(encoding="utf-8"))
    assert len(windows) == 180
    assert all(session["human_participant"] is False for session in sessions)
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["source_kind"] == "synthetic_fixture"


def test_full_fixture_run_writes_machine_and_human_reports(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    output_dir = tmp_path / "results"
    run(dataset_dir, output_dir)
    report = json.loads((output_dir / "evaluation.json").read_text(encoding="utf-8"))
    assert report["external_validation"]["status"] == "blocked"
    assert (output_dir / "REPORT.md").is_file()
    assert (output_dir / "run.json").is_file()
    assert (output_dir / "charts" / "modality_f1.png").is_file()
    assert (output_dir / "charts" / "roc_curve_combined.png").is_file()
