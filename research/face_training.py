"""Train one classifier per marksheet item from paired face and voice features.

Labels come from the session spreadsheet. Features belong to numbers in one
recording. This baseline does not establish a psychological condition.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib
import json
import joblib

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.group_observation import assign_group_splits


MODEL_VERSION = "group-face-voice-psycon-3.2.0"
FEATURE_NAME = "psycon-face-voice-2"
MIN_SESSIONS = 5
MIN_NONZERO = 5


def train_face_items(examples: list[dict[str, Any]], *, seed: int = 42, output_dir=None) -> dict[str, Any]:
    sessions = sorted({row["group_session_id"] for row in examples})
    grouped_sessions = [{"group_session_id": session_id,
                         "participant_ids": sorted({str(row.get("participant_key") or session_id) for row in examples if row["group_session_id"] == session_id}
                                                   | {"recording:" + row["source_hash"] for row in examples if row["group_session_id"] == session_id and row.get("source_hash")})}
                        for session_id in sessions]
    split_rows = assign_group_splits(
        grouped_sessions,
        seed=seed,
    ) if len(sessions) >= 3 else [
        {"group_session_id": session_id, "split": "train"} for session_id in sessions
    ]
    split_of = {row["group_session_id"]: row["split"] for row in split_rows}
    letters = sorted({row["item_letter"] for row in examples})
    items = []
    models = {}
    for letter in letters:
        rows = [row for row in examples if row["item_letter"] == letter and row.get("score") not in {None, "", "N/O"}]
        components = {row["group_session_id"]: row.get("component", row["group_session_id"]) for row in split_rows}
        session_count = len({components[row["group_session_id"]] for row in rows})
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
        # Seconds and counts can be orders of magnitude larger than normalized
        # appearance and spectral values. Fit scaling on the training split only.
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=400))
        model.fit(_matrix(trainable), [str(row["score"]) for row in trainable])
        models[letter] = model
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
    result = {
        "model_version": MODEL_VERSION,
        "feature": FEATURE_NAME,
        "sessions": len(sessions),
        "examples": len(examples),
        "items": items,
        "validated_psychological_result": False,
        "seed": seed,
        "splits": split_rows,
        "dataset_hash": hashlib.sha256(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "label_lineage": [{key: row.get(key) for key in ("group_session_id", "slot_number", "label_id", "item_letter", "score", "source_hash")} for row in examples],
    }
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=False)
        for letter, model in models.items():
            path = destination / f"item-{letter}.joblib"
            joblib.dump(model, path)
            next(row for row in items if row["item_letter"] == letter).update(
                artifact=path.name, artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result["artifact_directory"] = str(destination.resolve())
        # Write the manifest last. A run without it is incomplete and must not
        # be loaded. Training never replaces the active application model.
        (destination / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([list(row["feature"]) for row in rows], dtype=np.float64)
