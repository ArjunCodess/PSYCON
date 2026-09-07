from __future__ import annotations

from typing import Iterable

from .evidence import EvidenceRecord, EvidenceSource, EvidenceStatus


RISK_REQUIREMENTS = {
    "battery_depletion": ("six_hour_runtime", "safe_shutdown"),
    "sensor_disconnect": ("sensor_initialization", "error_recovery"),
    "i2c_failure": ("i2c_address_scan", "i2c_one_hour_stability"),
    "motion_artifacts": ("sensor_mpu6050", "wrist_continuity"),
    "audio_noise": ("sensor_inmp441", "audio_continuity"),
    "gsr_contact_loss": ("sensor_ads1115_gsr", "gsr_safety"),
    "firmware_crash": ("watchdog", "memory_stability"),
    "wireless_interruption": ("communication_recovery", "one_hour_stress"),
    "data_corruption": ("missing_corrupt_data", "research_export"),
}


def evaluate_risks(records: Iterable[EvidenceRecord]) -> list[dict]:
    latest: dict[str, EvidenceRecord] = {}
    for record in records:
        record.validate()
        if record.procedure_id not in latest or record.recorded_at_utc > latest[record.procedure_id].recorded_at_utc:
            latest[record.procedure_id] = record
    rows = []
    for risk, procedures in RISK_REQUIREMENTS.items():
        evidence = [latest.get(procedure) for procedure in procedures]
        mitigated = all(
            item is not None
            and item.status == EvidenceStatus.PASSED
            and (
                item.source == EvidenceSource.PHYSICAL_MEASUREMENT
                or item.procedure_id in {"missing_corrupt_data", "research_export"}
            )
            for item in evidence
        )
        rows.append({
            "risk": risk,
            "status": "mitigated" if mitigated else "open",
            "required_procedures": list(procedures),
            "evidence_records": [item.record_id for item in evidence if item is not None],
            "missing_procedures": [procedure for procedure, item in zip(procedures, evidence, strict=True) if item is None or item.status != EvidenceStatus.PASSED],
        })
    return rows

