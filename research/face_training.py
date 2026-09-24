"""Train one classifier per marksheet item from paired face and voice features.

Labels come from the session spreadsheet. Features belong to numbers in one
recording. This baseline does not establish a psychological condition.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

from research.group_observation import assign_group_splits


MODEL_VERSION = "group-face-voice-1.0.0"
FEATURE_NAME = "face_and_voice_v1"
MIN_SESSIONS = 5
MIN_NONZERO = 5


def train_face_items(examples: list[dict[str, Any]], *, seed: int = 42) -> dict[str, Any]:
    sessions = sorted({row["group_session_id"] for row in examples})
    split_rows = assign_group_splits(
        [{"group_session_id": session_id, "participant_ids": [session_id]} for session_id in sessions],
        seed=seed,
    ) if len(sessions) >= 3 else [
        {"group_session_id": session_id, "split": "train"} for session_id in sessions
    ]
    split_of = {row["group_session_id"]: row["split"] for row in split_rows}
    letters = sorted({row["item_letter"] for row in examples})
    items = []
    for letter in letters:
        rows = [row for row in examples if row["item_letter"] == letter and row.get("score") not in {None, "", "N/O"}]
        session_count = len({row["group_session_id"] for row in rows})
        nonzero = sum(1 for row in rows if str(row["score"]) != "0")
        if session_count < MIN_SESSIONS or nonzero < MIN_NONZERO:
            items.append(
                {
                    "item_letter": letter,
                    "status": "unavailable",
                    "reason": f"{session_count} sessions and {nonzero} nonzero scores; {MIN_SESSIONS} sessions and {MIN_NONZERO} nonzero scores are required",
                    "test_metrics": None,
                }
            )
            continue
        trainable = [row for row in rows if split_of.get(row["group_session_id"]) == "train"]
        held_out = [row for row in rows if split_of.get(row["group_session_id"]) == "test"]
        labels = sorted({str(row["score"]) for row in trainable})
        if len(trainable) < 2 or len(labels) < 2:
            items.append(
                {
                    "item_letter": letter,
                    "status": "unavailable",
                    "reason": "the training split needs at least two score values",
                    "test_metrics": None,
                }
            )
            continue
        model = LogisticRegression(max_iter=400)
        model.fit(_matrix(trainable), [str(row["score"]) for row in trainable])
        metrics = None
        if held_out:
            predicted = model.predict(_matrix(held_out))
            actual = [str(row["score"]) for row in held_out]
            metrics = {
                "accuracy": float(accuracy_score(actual, predicted)),
                "macro_f1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
                "test_examples": len(held_out),
            }
        items.append(
            {
                "item_letter": letter,
                "status": "fitted",
                "reason": None,
                "classes": labels,
                "test_metrics": metrics,
            }
        )
    return {
        "model_version": MODEL_VERSION,
        "feature": FEATURE_NAME,
        "sessions": len(sessions),
        "examples": len(examples),
        "items": items,
        "validated_psychological_result": False,
    }


def _matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([list(row["feature"]) for row in rows], dtype=np.float64)
