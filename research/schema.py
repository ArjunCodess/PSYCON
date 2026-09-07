from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping


PARTICIPANT_ID_PATTERN = re.compile(r"^P-[A-Z0-9]{6,32}$")
SESSION_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{5,63}$")
FORBIDDEN_KEYS = {
    "address",
    "date_of_birth",
    "dob",
    "email",
    "full_name",
    "name",
    "phone",
    "telephone",
}
ALLOWED_AGE_GROUPS = {
    "not_collected",
    "minor_approved",
    "18-24",
    "25-34",
    "35-44",
    "45-54",
    "55-64",
    "65_plus",
}


class MetadataError(ValueError):
    """Raised when session metadata is unsafe or incomplete for research use."""


def validate_session_metadata(metadata: Mapping[str, Any], *, require_approved: bool = True) -> dict[str, Any]:
    """Validate and copy one session record without accepting direct identifiers."""
    errors: list[str] = []
    _find_forbidden_keys(metadata, errors)

    participant_id = str(metadata.get("participant_id", ""))
    if not PARTICIPANT_ID_PATTERN.fullmatch(participant_id):
        errors.append("participant_id must match P- followed by 6-32 uppercase letters or digits")

    session_id = str(metadata.get("session_id", ""))
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        errors.append("session_id must be 6-64 uppercase letters, digits, underscores, or hyphens")

    if metadata.get("schema_version") != "1.0.0":
        errors.append("unsupported schema_version")

    approval_id = str(metadata.get("approval_id", "")).strip()
    protocol_version = str(metadata.get("protocol_version", "")).strip()
    consent_version = str(metadata.get("consent_version", "")).strip()
    if require_approved:
        if not approval_id or approval_id == "pending-approval":
            errors.append("approval_id is required for research use")
        if not protocol_version or protocol_version == "pending-approval":
            errors.append("an approved protocol_version is required for research use")
        if not consent_version or consent_version == "pending-approval":
            errors.append("an approved consent_version is required for research use")

    consent = _mapping(metadata.get("consent"), "consent", errors)
    physiology_consent = consent.get("physiology") is True
    audio_consent = consent.get("audio") is True
    if not physiology_consent:
        errors.append("physiology consent is required for a PSYCON research session")
    if consent.get("withdrawn") is True:
        errors.append("withdrawn session cannot be used for research")
    if consent.get("transcription") is True and not audio_consent:
        errors.append("transcription consent requires audio consent")
    if consent.get("voice_profile") is True and not audio_consent:
        errors.append("voice-profile consent requires audio consent")

    demographics = _mapping(metadata.get("demographics"), "demographics", errors)
    if demographics.get("age_group") not in ALLOWED_AGE_GROUPS:
        errors.append("age_group is missing or unsupported")

    recording = _mapping(metadata.get("recording"), "recording", errors)
    _validate_utc(recording.get("started_at_utc"), errors)
    duration = recording.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        errors.append("duration_seconds must be positive")
    for field in ("environment", "motion_condition", "stop_reason"):
        if not str(recording.get(field, "")).strip():
            errors.append(f"recording.{field} is required")

    device = _mapping(metadata.get("device"), "device", errors)
    for field in ("hardware_revision", "wrist_firmware_version"):
        if not str(device.get(field, "")).strip():
            errors.append(f"device.{field} is required")
    calibration_ids = device.get("calibration_record_ids")
    if not isinstance(calibration_ids, list) or not calibration_ids:
        errors.append("at least one calibration_record_id is required")

    synchronization = _mapping(metadata.get("synchronization"), "synchronization", errors)
    uncertainty = synchronization.get("max_uncertainty_ms")
    if not isinstance(uncertainty, (int, float)) or isinstance(uncertainty, bool) or uncertainty < 0:
        errors.append("synchronization.max_uncertainty_ms must be non-negative")
    if synchronization.get("quality") not in {"verified", "degraded", "failed"}:
        errors.append("synchronization.quality must be verified, degraded, or failed")

    eligibility = _mapping(metadata.get("eligibility"), "eligibility", errors)
    if eligibility.get("included") is not True:
        errors.append("eligibility.included must be true for research use")
    if not isinstance(eligibility.get("reason_codes"), list):
        errors.append("eligibility.reason_codes must be a list")

    if not str(metadata.get("operator_id", "")).strip():
        errors.append("operator_id is required")

    if errors:
        raise MetadataError("; ".join(dict.fromkeys(errors)))
    return _deep_copy(metadata)


def _mapping(value: Any, field: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{field} must be an object")
        return {}
    return value


def _validate_utc(value: Any, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append("recording.started_at_utc must be an ISO-8601 UTC timestamp ending in Z")
        return
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append("recording.started_at_utc is not a valid timestamp")


def _find_forbidden_keys(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            child_path = f"{path}.{key}" if path else str(key)
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"direct identifier field is forbidden: {child_path}")
            _find_forbidden_keys(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _find_forbidden_keys(child, errors, f"{path}[{index}]")


def _deep_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _deep_copy(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_deep_copy(child) for child in value]
    return value

