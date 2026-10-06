import hashlib
import json

import joblib
import pytest

from research.face_training import train_face_items


def examples():
    return [{"group_session_id": f"s{session}", "slot_number": slot, "item_letter": "A",
             "score": str(slot), "feature": [float(session), float(slot)],
             "participant_key": f"person-{session}-{slot}", "source_hash": f"source-{session}"}
            for session in range(8) for slot in (1, 2)]


def test_saved_model_loads_and_matches_manifest(tmp_path):
    destination = tmp_path / "run"
    report = train_face_items(examples(), output_dir=destination)
    item = report["items"][0]
    assert item["status"] == "fitted"
    assert item["test_metrics"]["test_examples"] > 0
    artifact = destination / item["artifact"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == item["artifact_sha256"]
    model = joblib.load(artifact)
    assert model.predict([[0., 1.], [0., 2.]]).tolist() == ["1", "2"]
    assert json.loads((destination / "manifest.json").read_text())["dataset_hash"] == report["dataset_hash"]
    with pytest.raises(FileExistsError):
        train_face_items(examples(), output_dir=destination)


def test_repeated_people_and_reuploaded_recordings_cannot_cross_splits():
    rows = examples()
    for row in rows:
        if row["group_session_id"] in {"s0", "s1"}:
            row["participant_key"] = "explicitly-linked-person"
        if row["group_session_id"] in {"s2", "s3"}:
            row["source_hash"] = "same-recording"
    result = train_face_items(rows)
    splits = {row["group_session_id"]: row["split"] for row in result["splits"]}
    assert splits["s0"] == splits["s1"]
    assert splits["s2"] == splits["s3"]


def test_insufficient_independent_groups_stay_unavailable(tmp_path):
    rows = examples()
    for row in rows:
        row["participant_key"] = "one-person"
    report = train_face_items(rows, output_dir=tmp_path / "sparse")
    assert report["items"][0]["status"] == "unavailable"
    assert not list((tmp_path / "sparse").glob("*.joblib"))
