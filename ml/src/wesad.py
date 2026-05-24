from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import CHEST_LABEL_HZ, LABEL_CALM, LABEL_HIGH_STRESS, WESAD_RAW_DIR


@dataclass(frozen=True)
class WesadSubject:
    subject_id: str
    path: Path


def discover_subjects(raw_dir: Path = WESAD_RAW_DIR) -> list[WesadSubject]:
    subjects: list[WesadSubject] = []
    for subject_dir in sorted(raw_dir.glob("S*"), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 999):
        pkl_path = subject_dir / f"{subject_dir.name}.pkl"
        if pkl_path.exists():
            subjects.append(WesadSubject(subject_id=subject_dir.name, path=pkl_path))
    return subjects


def load_subject(subject: WesadSubject | str | Path) -> dict[str, Any]:
    path = _subject_to_path(subject)
    with path.open("rb") as f:
        return pickle.load(f, encoding="latin1")


def map_wesad_label(label: int) -> str | None:
    if label == 1:
        return LABEL_CALM
    if label == 2:
        return LABEL_HIGH_STRESS
    return None


def resample_labels(labels: np.ndarray, target_len: int, common_hz: int) -> np.ndarray:
    times = np.arange(target_len, dtype=float) / common_hz
    indices = np.minimum((times * CHEST_LABEL_HZ).astype(int), len(labels) - 1)
    return labels[indices]


def _subject_to_path(subject: WesadSubject | str | Path) -> Path:
    if isinstance(subject, WesadSubject):
        return subject.path
    path = Path(subject)
    if path.suffix == ".pkl":
        return path
    return WESAD_RAW_DIR / path.name / f"{path.name}.pkl"

