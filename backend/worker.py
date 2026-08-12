from __future__ import annotations

import argparse
import os
import socket
import time

from .app import create_app


def run_worker(*, once: bool = False, poll_seconds: float = 1.0) -> None:
    app = create_app()
    repository = app.extensions["psycon_repository"]
    processor = app.extensions["psycon_processor"]
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    while True:
        repository.heartbeat(worker_id)
        job = repository.claim_job(worker_id)
        if job is None:
            if once:
                return
            time.sleep(poll_seconds)
            continue
        repository.heartbeat(worker_id, job["id"])
        try:
            if job["job_type"] == "process_session":
                processor.process_session(job["session_id"])
            else:
                raise ValueError(f"unsupported job type: {job['job_type']}")
        except Exception as exc:
            repository.fail_job(job["id"], f"{type(exc).__name__}: {exc}")
        else:
            repository.complete_job(job["id"])
        repository.heartbeat(worker_id)
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PSYCON PostgreSQL-backed processing worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    run_worker(once=args.once, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
