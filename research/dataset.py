from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


MODALITIES = ("physiology", "speech", "context")
KEY_COLUMNS = ["participant_id", "session_id", "window_start_ms", "window_end_ms"]
UNUSABLE_STATES = {"corrupt", "missing", "low_quality", "untranscribable", "unsynchronized"}


def assemble_feature_windows(
    physiology: pd.DataFrame,
    speech: pd.DataFrame,
    context: pd.DataFrame,
    *,
    label_column: str = "label",
) -> pd.DataFrame:
    """Outer-join synchronized windows while retaining modality quality and missingness."""
    tables = {
        "physiology": physiology,
        "speech": speech,
        "context": context,
    }
    normalized: list[pd.DataFrame] = []
    for modality, frame in tables.items():
        _validate_feature_table(frame, modality, label_column)
        renamed = frame.copy()
        value_columns = [column for column in renamed.columns if column not in KEY_COLUMNS + [label_column]]
        renamed = renamed.rename(columns={column: f"{modality}__{column}" for column in value_columns})
        normalized.append(renamed)

    merged = normalized[0]
    for next_frame in normalized[1:]:
        merged = merged.merge(
            next_frame,
            how="outer",
            on=KEY_COLUMNS,
            suffixes=("", "__candidate"),
            validate="one_to_one",
        )
        candidate = f"{label_column}__candidate"
        if candidate in merged:
            conflict = merged[label_column].notna() & merged[candidate].notna() & (merged[label_column] != merged[candidate])
            if conflict.any():
                raise ValueError("conflicting labels for the same synchronized window")
            candidate_labels = merged.pop(candidate)
            merged[label_column] = merged[label_column].where(merged[label_column].notna(), candidate_labels)

    merged = merged.sort_values(KEY_COLUMNS, kind="stable").reset_index(drop=True)
    for modality in MODALITIES:
        quality_column = f"{modality}__quality_state"
        modality_columns = [column for column in merged if column.startswith(f"{modality}__")]
        feature_columns = [column for column in modality_columns if column != quality_column]
        present = merged[feature_columns].notna().any(axis=1) if feature_columns else pd.Series(False, index=merged.index)
        quality = merged.get(quality_column, pd.Series("missing", index=merged.index)).fillna("missing").astype(str)
        merged[f"{modality}__available"] = present
        merged[f"{modality}__usable"] = present & ~quality.isin(UNUSABLE_STATES)
        merged[f"{modality}__quality_state"] = quality.where(present, "missing")
        unusable = present & quality.isin(UNUSABLE_STATES)
        merged.loc[unusable, feature_columns] = np.nan

    usable_columns = [f"{modality}__usable" for modality in MODALITIES]
    merged["usable_modality_count"] = merged[usable_columns].sum(axis=1).astype(int)
    merged["data_quality_score"] = merged["usable_modality_count"] / len(MODALITIES)
    merged["missing_or_bad"] = merged["usable_modality_count"] < len(MODALITIES)
    return merged


def modality_dataset(windows: pd.DataFrame, modality: str) -> tuple[pd.DataFrame, list[str]]:
    """Select one frozen modality without changing the window or participant set."""
    if modality not in {"physiology", "speech", "combined"}:
        raise ValueError(f"unsupported modality: {modality}")
    prefixes = ("physiology__",) if modality == "physiology" else ("speech__",)
    if modality == "combined":
        prefixes = ("physiology__", "speech__", "context__")
    excluded_suffixes = ("__available", "__usable", "__quality_state")
    columns = [
        column
        for column in windows.columns
        if column.startswith(prefixes)
        and not column.endswith(excluded_suffixes)
        and pd.api.types.is_numeric_dtype(windows[column])
    ]
    if not columns:
        raise ValueError(f"no numeric features for modality: {modality}")
    return windows[KEY_COLUMNS + ["label", "data_quality_score", *columns]].copy(), columns


def build_dataset_manifest(
    root: Path,
    files: Iterable[Path],
    *,
    dataset_version: str,
    protocol_version: str,
    source_kind: str,
) -> dict[str, object]:
    """Hash an explicit file list without reading files outside the dataset root."""
    resolved_root = root.resolve()
    entries: list[dict[str, object]] = []
    for path in sorted((Path(item) for item in files), key=lambda item: item.as_posix()):
        resolved = path.resolve()
        if resolved_root != resolved and resolved_root not in resolved.parents:
            raise ValueError(f"manifest path is outside dataset root: {path}")
        if not resolved.is_file():
            raise FileNotFoundError(path)
        payload = resolved.read_bytes()
        entries.append({
            "path": resolved.relative_to(resolved_root).as_posix(),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return {
        "schema_version": "1.0.0",
        "dataset_version": dataset_version,
        "protocol_version": protocol_version,
        "source_kind": source_kind,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": entries,
    }


def write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_feature_table(frame: pd.DataFrame, modality: str, label_column: str) -> None:
    missing = [column for column in KEY_COLUMNS + [label_column, "quality_state"] if column not in frame]
    if missing:
        raise ValueError(f"{modality} table is missing columns: {', '.join(missing)}")
    if frame.duplicated(KEY_COLUMNS).any():
        raise ValueError(f"{modality} table has duplicate synchronized windows")
    if ((frame["window_end_ms"] - frame["window_start_ms"]) <= 0).any():
        raise ValueError(f"{modality} table has a non-positive window")
    if frame[KEY_COLUMNS].isna().any().any():
        raise ValueError(f"{modality} table has a missing synchronization key")
    finite_times = np.isfinite(frame[["window_start_ms", "window_end_ms"]].to_numpy(dtype=float))
    if not finite_times.all():
        raise ValueError(f"{modality} table has a non-finite timestamp")
