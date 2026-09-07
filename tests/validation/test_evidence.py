from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.evidence import EvidenceRecord, EvidenceSource, EvidenceStatus, ValidationError, load_evidence, write_evidence


def record(**overrides) -> EvidenceRecord:
    values = {
        "record_id": "REC-01",
        "procedure_id": "PROC-01",
        "category": "software",
        "status": EvidenceStatus.PASSED,
        "source": EvidenceSource.SOFTWARE_TEST,
        "recorded_at_utc": "2026-09-08T12:00:00Z",
        "operator_id": "OP-01",
        "hardware_revision": "",
        "firmware_versions": {"backend": "1.0.0"},
        "conditions": {"python": "3.14"},
        "measurements": {"tests": 1},
        "artifacts": ("pytest.txt",),
    }
    values.update(overrides)
    return EvidenceRecord(**values)


def test_software_pass_accepts_repeatable_artifact() -> None:
    assert record().validate().status == EvidenceStatus.PASSED


def test_simulation_cannot_pass_physical_gate() -> None:
    with pytest.raises(ValidationError, match="physical_measurement"):
        record(category="electrical", source=EvidenceSource.SIMULATED_STACK).validate()


def test_failed_record_requires_corrective_action() -> None:
    with pytest.raises(ValidationError, match="corrective action"):
        record(status=EvidenceStatus.FAILED, artifacts=()).validate()


def test_evidence_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    write_evidence(path, [record()])
    loaded = load_evidence(path)
    assert loaded == [record()]
    assert json.loads(path.read_text(encoding="utf-8"))[0]["source"] == "software_test"

