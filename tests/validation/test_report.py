from __future__ import annotations

import json
from pathlib import Path

from validation.evidence import EvidenceRecord, EvidenceSource, EvidenceStatus
from validation.report import build_report, write_report
from validation.risk import evaluate_risks


def evidence(procedure: str, source: EvidenceSource, category: str = "software") -> EvidenceRecord:
    return EvidenceRecord(
        record_id=f"REC-{procedure}",
        procedure_id=procedure,
        category=category,
        status=EvidenceStatus.PASSED,
        source=source,
        recorded_at_utc="2026-09-08T12:00:00Z",
        operator_id="OP-01",
        hardware_revision="rev-a" if source == EvidenceSource.PHYSICAL_MEASUREMENT else "",
        firmware_versions={"wrist": "1.0.0"},
        conditions={},
        measurements={"value": 1},
        artifacts=(f"evidence/{procedure}.json",),
    )


def test_empty_report_keeps_physical_and_exit_gates_open() -> None:
    report = build_report([])
    assert report["exit_gate"] == {"passed": False, "software_complete": False, "physical_complete": False}
    assert all(item["status"] == "missing" for item in report["procedures"])


def test_wrong_evidence_source_does_not_pass_procedure() -> None:
    report = build_report([evidence("dashboard", EvidenceSource.SOFTWARE_TEST)])
    dashboard = next(item for item in report["procedures"] if item["procedure_id"] == "dashboard")
    assert dashboard["status"] == "invalid_source"
    assert dashboard["source_matches"] is False
    assert report["exit_gate"]["passed"] is False


def test_report_writer_creates_machine_and_human_outputs(tmp_path: Path) -> None:
    report = build_report([])
    write_report(tmp_path, report)
    assert json.loads((tmp_path / "week6-validation.json").read_text(encoding="utf-8"))["exit_gate"]["passed"] is False
    assert "Overall exit gate: **open**" in (tmp_path / "week6-validation.md").read_text(encoding="utf-8")


def test_risk_closes_only_after_required_evidence() -> None:
    records = [
        evidence("missing_corrupt_data", EvidenceSource.SIMULATED_STACK),
        evidence("research_export", EvidenceSource.SIMULATED_STACK),
    ]
    risks = evaluate_risks(records)
    assert next(item for item in risks if item["risk"] == "data_corruption")["status"] == "mitigated"
    assert next(item for item in risks if item["risk"] == "battery_depletion")["status"] == "open"
