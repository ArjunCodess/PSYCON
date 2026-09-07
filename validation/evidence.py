from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping


class EvidenceStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class EvidenceSource(StrEnum):
    SOFTWARE_TEST = "software_test"
    SIMULATED_STACK = "simulated_stack"
    PHYSICAL_MEASUREMENT = "physical_measurement"
    DOCUMENT_REVIEW = "document_review"


class ValidationError(ValueError):
    """Raised when an evidence record would make an unsupported claim."""


PHYSICAL_CATEGORIES = {"assembly", "battery", "calibration", "electrical", "mechanical", "runtime", "wearability"}


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    procedure_id: str
    category: str
    status: EvidenceStatus
    source: EvidenceSource
    recorded_at_utc: str
    operator_id: str
    hardware_revision: str
    firmware_versions: Mapping[str, str]
    conditions: Mapping[str, Any]
    measurements: Mapping[str, Any]
    artifacts: tuple[str, ...]
    notes: str = ""
    corrective_actions: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> "EvidenceRecord":
        errors: list[str] = []
        if not self.record_id.strip() or not self.procedure_id.strip():
            errors.append("record_id and procedure_id are required")
        if not self.operator_id.strip():
            errors.append("operator_id is required")
        if not self.recorded_at_utc.endswith("Z"):
            errors.append("recorded_at_utc must be an ISO-8601 UTC timestamp ending in Z")
        else:
            try:
                datetime.fromisoformat(self.recorded_at_utc.replace("Z", "+00:00"))
            except ValueError:
                errors.append("recorded_at_utc is invalid")
        if self.status == EvidenceStatus.PASSED and not self.artifacts:
            errors.append("passed evidence requires at least one artifact")
        if self.status == EvidenceStatus.PASSED and self.category in PHYSICAL_CATEGORIES:
            if self.source != EvidenceSource.PHYSICAL_MEASUREMENT:
                errors.append(f"{self.category} can pass only with physical_measurement evidence")
            if not self.measurements:
                errors.append(f"{self.category} pass requires recorded measurements")
            if not self.hardware_revision.strip() or self.hardware_revision in {"unknown", "simulated"}:
                errors.append(f"{self.category} pass requires a real hardware revision")
        if self.status == EvidenceStatus.FAILED and not self.corrective_actions:
            errors.append("failed evidence requires a corrective action")
        if self.status == EvidenceStatus.BLOCKED and not self.notes.strip():
            errors.append("blocked evidence requires a named blocker")
        if errors:
            raise ValidationError("; ".join(errors))
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["status"] = self.status.value
        value["source"] = self.source.value
        value["artifacts"] = list(self.artifacts)
        value["corrective_actions"] = list(self.corrective_actions)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceRecord":
        try:
            record = cls(
                record_id=str(value["record_id"]),
                procedure_id=str(value["procedure_id"]),
                category=str(value["category"]),
                status=EvidenceStatus(str(value["status"])),
                source=EvidenceSource(str(value["source"])),
                recorded_at_utc=str(value["recorded_at_utc"]),
                operator_id=str(value["operator_id"]),
                hardware_revision=str(value.get("hardware_revision", "")),
                firmware_versions=dict(value.get("firmware_versions", {})),
                conditions=dict(value.get("conditions", {})),
                measurements=dict(value.get("measurements", {})),
                artifacts=tuple(str(item) for item in value.get("artifacts", [])),
                notes=str(value.get("notes", "")),
                corrective_actions=tuple(str(item) for item in value.get("corrective_actions", [])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValidationError(f"invalid evidence record: {error}") from error
        return record.validate()


def load_evidence(path: Path) -> list[EvidenceRecord]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValidationError("evidence file must contain a JSON array")
    return [EvidenceRecord.from_dict(item) for item in value]


def write_evidence(path: Path, records: list[EvidenceRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([record.to_dict() for record in records], indent=2, sort_keys=True) + "\n", encoding="utf-8")

