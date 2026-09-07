from __future__ import annotations

import copy

import pytest

from research.run_study import validate_metadata_coverage
from tests.research.test_dataset import feature_tables, valid_metadata
from research.dataset import assemble_feature_windows


def metadata_for_fixture() -> dict:
    record = copy.deepcopy(valid_metadata())
    record["participant_id"] = "P-AAAAAA"
    return record


def test_metadata_coverage_accepts_exact_session_records() -> None:
    windows = assemble_feature_windows(*feature_tables())
    validate_metadata_coverage(windows, [metadata_for_fixture()])


def test_metadata_coverage_rejects_missing_sessions() -> None:
    windows = assemble_feature_windows(*feature_tables())
    with pytest.raises(ValueError, match="coverage mismatch"):
        validate_metadata_coverage(windows, [valid_metadata()])


def test_metadata_coverage_runs_consent_validation() -> None:
    windows = assemble_feature_windows(*feature_tables())
    metadata = metadata_for_fixture()
    metadata["consent"]["withdrawn"] = True
    with pytest.raises(ValueError, match="withdrawn"):
        validate_metadata_coverage(windows, [metadata])

