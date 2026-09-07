from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .evidence import EvidenceRecord, EvidenceSource, EvidenceStatus, load_evidence
from .stages import evaluate_stage_gates


@dataclass(frozen=True)
class Procedure:
    procedure_id: str
    category: str
    description: str
    required_source: EvidenceSource


PROCEDURES = (
    Procedure("visual_inspection", "assembly", "PCB, polarity, soldering, wiring, and battery inspection", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("connector_inspection", "assembly", "Connector, strap, access, insulation, and strain-relief inspection", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("supply_rails", "electrical", "Boot, idle, sensing, and wireless supply-rail measurements", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("current_consumption", "electrical", "Idle and peak current measurements", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("brownout", "electrical", "Brownout threshold and recovery", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("charge_cycle", "battery", "Charge current, time, temperature, and disconnect behavior", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("boot_cycles", "firmware", "Rapid reboot reliability", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("sensor_initialization", "firmware", "Sensor initialization and address checks", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("error_recovery", "firmware", "Sensor, communication, corrupt-data, and missing-data recovery", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("watchdog", "firmware", "Watchdog reset and resumed acquisition", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("memory_stability", "firmware", "Free-heap and allocation stability", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("one_hour_stress", "runtime", "One-hour full transmission stress test", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("six_hour_runtime", "runtime", "Six-hour battery-powered runtime", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("feature_extraction", "software", "Feature provenance and quality handling", EvidenceSource.SOFTWARE_TEST),
    Procedure("time_sync", "integration", "Measured device-to-backend synchronization", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("inference_validation", "software", "Inference, confidence, and abstention", EvidenceSource.SOFTWARE_TEST),
    Procedure("dashboard", "software", "Dashboard session and quality display", EvidenceSource.SIMULATED_STACK),
    Procedure("research_export", "software", "Hashed research export and restore", EvidenceSource.SIMULATED_STACK),
    Procedure("missing_corrupt_data", "software", "Visible missing and corrupt data handling", EvidenceSource.SIMULATED_STACK),
    Procedure("mechanical_checks", "mechanical", "Enclosure, wearability, access, and microphone-port checks", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("gsr_safety", "electrical", "GSR excitation, insulation, and no-charge-during-wear rule", EvidenceSource.PHYSICAL_MEASUREMENT),
    Procedure("safe_shutdown", "firmware", "Buffer flush and controlled shutdown", EvidenceSource.PHYSICAL_MEASUREMENT),
)


def build_report(records: Iterable[EvidenceRecord]) -> dict:
    records = list(records)
    latest: dict[str, EvidenceRecord] = {}
    for record in records:
        record.validate()
        if record.procedure_id not in latest or record.recorded_at_utc > latest[record.procedure_id].recorded_at_utc:
            latest[record.procedure_id] = record
    procedure_rows = []
    for procedure in PROCEDURES:
        record = latest.get(procedure.procedure_id)
        source_matches = record is not None and record.source == procedure.required_source
        passed = record is not None and record.status == EvidenceStatus.PASSED and source_matches
        displayed_status = "missing" if record is None else record.status.value
        if record is not None and record.status == EvidenceStatus.PASSED and not source_matches:
            displayed_status = "invalid_source"
        procedure_rows.append({
            "procedure_id": procedure.procedure_id,
            "category": procedure.category,
            "description": procedure.description,
            "required_source": procedure.required_source.value,
            "status": "passed" if passed else displayed_status,
            "source_matches": source_matches,
            "record_id": record.record_id if record is not None else None,
            "artifacts": list(record.artifacts) if record is not None else [],
            "corrective_actions": list(record.corrective_actions) if record is not None else [],
        })
    stages = [result.to_dict() for result in evaluate_stage_gates(records)]
    all_procedures_pass = all(row["status"] == "passed" and row["source_matches"] for row in procedure_rows)
    all_stages_pass = all(row["status"] == "passed" for row in stages)
    return {
        "schema_version": "1.0.0",
        "procedures": procedure_rows,
        "integration_stages": stages,
        "exit_gate": {
            "passed": all_procedures_pass and all_stages_pass,
            "software_complete": all(
                row["status"] == "passed"
                for row in procedure_rows
                if row["required_source"] in {EvidenceSource.SOFTWARE_TEST.value, EvidenceSource.SIMULATED_STACK.value}
            ),
            "physical_complete": all(
                row["status"] == "passed" and row["source_matches"]
                for row in procedure_rows
                if row["required_source"] == EvidenceSource.PHYSICAL_MEASUREMENT.value
            ) and all_stages_pass,
        },
    }


def write_report(output_dir: Path, report: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "week6-validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        "# Week 6 validation report",
        "",
        f"Overall exit gate: **{'passed' if report['exit_gate']['passed'] else 'open'}**",
        "",
        "A simulated or unit-test result can pass only its named software procedure. Physical integration, safety, calibration, electrical, mechanical, stress, and battery gates require measured hardware evidence.",
        "",
        "## Procedures",
        "",
        "| Procedure | Category | Status | Required evidence | Record |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report["procedures"]:
        rows.append(f"| `{item['procedure_id']}` | {item['category']} | {item['status']} | {item['required_source']} | {item['record_id'] or ''} |")
    rows.extend(["", "## Integration stages", "", "| Stage | Status | Reason |", "| --- | --- | --- |"])
    for item in report["integration_stages"]:
        rows.append(f"| {item['stage']} | {item['status']} | {item['reason']} |")
    rows.append("")
    (output_dir / "week6-validation.md").write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Week 6 evidence-backed validation report.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    report = build_report(load_evidence(arguments.evidence))
    write_report(arguments.output_dir, report)
    raise SystemExit(0 if report["exit_gate"]["passed"] else 2)


if __name__ == "__main__":
    main()
