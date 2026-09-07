from __future__ import annotations

from validation.evidence import EvidenceRecord, EvidenceSource, EvidenceStatus
from validation.stages import IntegrationStage, STAGE_REQUIREMENTS, evaluate_stage_gates


def physical_record(procedure_id: str, *, status: EvidenceStatus = EvidenceStatus.PASSED) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=f"REC-{procedure_id}",
        procedure_id=procedure_id,
        category="calibration",
        status=status,
        source=EvidenceSource.PHYSICAL_MEASUREMENT,
        recorded_at_utc="2026-09-08T12:00:00Z",
        operator_id="OP-01",
        hardware_revision="rev-a",
        firmware_versions={"wrist": "1.0.0"},
        conditions={"bench": "lab"},
        measurements={"samples": 100},
        artifacts=(f"logs/{procedure_id}.json",),
        corrective_actions=("repair and retest",) if status == EvidenceStatus.FAILED else (),
    )


def test_missing_first_stage_blocks_all_later_stages() -> None:
    results = evaluate_stage_gates([])
    assert len(results) == 5
    assert all(result.status == EvidenceStatus.BLOCKED for result in results)
    assert results[1].reason == "stage 1 has not passed"


def test_stages_pass_only_in_order() -> None:
    records = [
        physical_record(requirement.procedure_id)
        for stage in IntegrationStage
        for requirement in STAGE_REQUIREMENTS[stage]
    ]
    results = evaluate_stage_gates(records)
    assert all(result.status == EvidenceStatus.PASSED for result in results)


def test_latest_failure_stops_current_and_later_stages() -> None:
    stage_one = [physical_record(requirement.procedure_id) for requirement in STAGE_REQUIREMENTS[IntegrationStage.SENSOR_VALIDATION]]
    failed = physical_record("sensor_inmp441", status=EvidenceStatus.FAILED)
    failed = EvidenceRecord(**{**failed.__dict__, "recorded_at_utc": "2026-09-08T13:00:00Z"})
    results = evaluate_stage_gates([*stage_one, failed])
    assert results[0].status == EvidenceStatus.FAILED
    assert results[0].failed == ("sensor_inmp441",)
    assert results[1].status == EvidenceStatus.BLOCKED


def test_simulated_record_cannot_satisfy_physical_requirement() -> None:
    record = physical_record("sensor_max30102")
    simulated = EvidenceRecord(
        **{
            **record.__dict__,
            "category": "software",
            "source": EvidenceSource.SIMULATED_STACK,
        }
    )
    result = evaluate_stage_gates([simulated])[0]
    assert result.status == EvidenceStatus.BLOCKED
    assert result.blocked == ("sensor_max30102",)

