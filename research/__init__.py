"""Research-study data contracts and evaluation tools."""

from .dataset import MODALITIES, assemble_feature_windows, build_dataset_manifest
from .schema import MetadataError, validate_session_metadata

__all__ = [
    "MODALITIES",
    "MetadataError",
    "assemble_feature_windows",
    "build_dataset_manifest",
    "validate_session_metadata",
]

