"""Mark a voice job interrupted after an operator verifies its worker stopped."""
from __future__ import annotations

import argparse
from uuid import UUID

from psycopg.types.json import Jsonb

from backend.app import create_app


def recover(database, job_id: str, worker_id: str, reason: str) -> str:
    with database.connection() as connection:
        job = connection.execute(
            "SELECT * FROM group_jobs WHERE id=%s AND locked_by=%s AND state='running' FOR UPDATE",
            (job_id, worker_id),
        ).fetchone()
        if not job or job["job_type"] not in {"process_psycon", "process_nvidia"}:
            raise ValueError("No running voice job matches that job and worker")
        method = "psycon" if job["job_type"] == "process_psycon" else "nvidia"
        session_id = job["group_session_id"]
        recording = connection.execute(
            "SELECT processing FROM recordings WHERE group_session_id=%s FOR UPDATE", (session_id,),
        ).fetchone()
        processing = dict(recording["processing"] or {})
        processing[f"{method}_matching"] = {
            **processing.get(f"{method}_matching", {}),
            "status": "failed", "ready_voices": 0, "reason": reason,
        }
        connection.execute("DELETE FROM voice_segments WHERE group_session_id=%s AND method=%s", (session_id, method))
        connection.execute("DELETE FROM voice_profiles WHERE group_session_id=%s AND method=%s", (session_id, method))
        connection.execute("UPDATE recordings SET processing=%s WHERE group_session_id=%s", (Jsonb(processing), session_id))
        connection.execute("UPDATE group_jobs SET state='failed', error=%s WHERE id=%s", (reason, job_id))
    return method


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True, type=UUID)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--worker-stopped", action="store_true")
    args = parser.parse_args()
    if not args.worker_stopped:
        parser.error("Verify the worker has stopped before using --worker-stopped")
    app = create_app()
    method = recover(app.extensions["psycon_db"], str(args.job_id), args.worker_id, args.reason)
    print(f"{method} job marked failed; it can be retried from the Faces tab")


if __name__ == "__main__":
    main()
