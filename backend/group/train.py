"""Train and save PSYCON's group rating models from a consistent DB snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from ml.src.environment import load_project_environment, PROJECT_ROOT
from backend.auth import Principal
from backend.config import Settings
from backend.db import Database
from .errors import GroupError
from .memory import MemoryGroupStore
from .postgres import _public
from .service import GroupObservationService, LOCAL_ACCOUNT_ID


def database_snapshot(database):
    """No raw media, personal histories, LLM output, or model predictions."""
    store = MemoryGroupStore()
    with database.connection() as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            sessions = [_public(row) for row in connection.execute("SELECT * FROM group_sessions WHERE consent_status='recorded'").fetchall()]
            ids = {row["id"] for row in sessions}
            for session in sessions:
                store.insert_session(session)
            for row in connection.execute("SELECT * FROM group_participants WHERE withdrawn_at IS NULL").fetchall():
                person = _public(row)
                if person["group_session_id"] in ids:
                    store.insert_participant(person)
            valid_people = {p["id"] for people in store.participant_rows.values() for p in people}
            for row in connection.execute("SELECT * FROM recordings WHERE processing_state='complete'").fetchall():
                recording = _public(row)
                if recording["group_session_id"] in ids:
                    store.insert_recording(recording)
            for row in connection.execute("SELECT * FROM face_samples").fetchall():
                sample = _public(row)
                if sample["group_session_id"] in ids:
                    store.face_samples.setdefault(sample["group_session_id"], []).append(sample)
            for row in connection.execute("SELECT * FROM voice_profiles WHERE method='psycon'").fetchall():
                profile = _public(row)
                if profile["group_session_id"] in ids:
                    store.psycon_profiles.setdefault(profile["group_session_id"], []).append(profile)
            for row in connection.execute("SELECT * FROM training_labels ORDER BY group_session_id, slot_number, item_letter").fetchall():
                label = _public(row)
                if label["participant_id"] in valid_people and label["group_session_id"] in store.recordings:
                    store.training_labels.append(label)
    return store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / ".runtime" / "models" / "psycon-group")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    load_project_environment(override=False)
    settings = Settings.from_env()
    database = Database(settings.database_url)
    try:
        database.migrate()
        snapshot = database_snapshot(database)
        run = args.output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        service = GroupObservationService(snapshot, None)
        actor = Principal(LOCAL_ACCOUNT_ID, "operator", None, "Local training script")
        result = service.train_faces(actor, output_dir=run, seed=args.seed)
        print(json.dumps(result, indent=2))
        if not any(item["status"] == "fitted" for item in result["items"]):
            print("No item met the training requirements. See manifest.json for the missing data.", file=sys.stderr)
            return 2
        return 0
    except GroupError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
