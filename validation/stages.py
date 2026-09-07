from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Iterable

from .evidence import EvidenceRecord, EvidenceSource, EvidenceStatus


class IntegrationStage(IntEnum):
    SENSOR_VALIDATION = 1
    I2C_VALIDATION = 2
    WRIST_INTEGRATION = 3
    AUDIO_INTEGRATION = 4
    FULL_SYSTEM = 5


@dataclass(frozen=True)
class ProcedureRequirement:
    procedure_id: str
    required_source: EvidenceSource


@dataclass(frozen=True)
class StageResult:
    stage: IntegrationStage
    status: EvidenceStatus
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    blocked: tuple[str, ...]
    missing: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["stage"] = self.stage.name.lower()
        value["status"] = self.status.value
        return value


STAGE_REQUIREMENTS: dict[IntegrationStage, tuple[ProcedureRequirement, ...]] = {
    IntegrationStage.SENSOR_VALIDATION: tuple(
        ProcedureRequirement(procedure_id, EvidenceSource.PHYSICAL_MEASUREMENT)
        for procedure_id in (
            "sensor_max30102",
            "sensor_mpu6050",
            "sensor_mcp9808",
            "sensor_ads1115_gsr",
            "sensor_inmp441",
            "sensor_temt6000",
        )
    ),
    IntegrationStage.I2C_VALIDATION: tuple(
        ProcedureRequirement(procedure_id, EvidenceSource.PHYSICAL_MEASUREMENT)
        for procedure_id in ("i2c_address_scan", "i2c_one_hour_stability")
    ),
    IntegrationStage.WRIST_INTEGRATION: tuple(
        ProcedureRequirement(procedure_id, EvidenceSource.PHYSICAL_MEASUREMENT)
        for procedure_id in ("wrist_continuity", "wrist_sensor_isolation", "wrist_buffer_recovery")
    ),
    IntegrationStage.AUDIO_INTEGRATION: tuple(
        ProcedureRequirement(procedure_id, EvidenceSource.PHYSICAL_MEASUREMENT)
        for procedure_id in ("audio_continuity", "light_response", "audio_buffer_recovery")
    ),
    IntegrationStage.FULL_SYSTEM: (
        ProcedureRequirement("module_independence", EvidenceSource.PHYSICAL_MEASUREMENT),
        ProcedureRequirement("time_sync", EvidenceSource.PHYSICAL_MEASUREMENT),
        ProcedureRequirement("communication_recovery", EvidenceSource.PHYSICAL_MEASUREMENT),
        ProcedureRequirement("safe_shutdown", EvidenceSource.PHYSICAL_MEASUREMENT),
        ProcedureRequirement("backend_e2e", EvidenceSource.PHYSICAL_MEASUREMENT),
    ),
}


def evaluate_stage_gates(records: Iterable[EvidenceRecord]) -> list[StageResult]:
    """Evaluate the five physical stages in order using the latest record per procedure."""
    latest: dict[str, EvidenceRecord] = {}
    for record in records:
        record.validate()
        current = latest.get(record.procedure_id)
        if current is None or record.recorded_at_utc > current.recorded_at_utc:
            latest[record.procedure_id] = record

    results: list[StageResult] = []
    previous_passed = True
    for stage in IntegrationStage:
        requirements = STAGE_REQUIREMENTS[stage]
        if not previous_passed:
            result = StageResult(
                stage=stage,
                status=EvidenceStatus.BLOCKED,
                passed=(),
                failed=(),
                blocked=(),
                missing=tuple(item.procedure_id for item in requirements),
                reason=f"stage {stage.value - 1} has not passed",
            )
            results.append(result)
            continue

        passed: list[str] = []
        failed: list[str] = []
        blocked: list[str] = []
        missing: list[str] = []
        for requirement in requirements:
            record = latest.get(requirement.procedure_id)
            if record is None:
                missing.append(requirement.procedure_id)
            elif record.source != requirement.required_source:
                blocked.append(requirement.procedure_id)
            elif record.status == EvidenceStatus.PASSED:
                passed.append(requirement.procedure_id)
            elif record.status == EvidenceStatus.FAILED:
                failed.append(requirement.procedure_id)
            else:
                blocked.append(requirement.procedure_id)

        if failed:
            status = EvidenceStatus.FAILED
            reason = "one or more required procedures failed"
        elif blocked or missing:
            status = EvidenceStatus.BLOCKED
            reason = "required physical evidence is blocked or missing"
        else:
            status = EvidenceStatus.PASSED
            reason = "all required procedures passed with physical evidence"
        result = StageResult(stage, status, tuple(passed), tuple(failed), tuple(blocked), tuple(missing), reason)
        results.append(result)
        previous_passed = status == EvidenceStatus.PASSED
    return results

