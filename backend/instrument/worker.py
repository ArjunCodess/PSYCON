"""One local inference worker owns the model memory and interruption recovery."""
from contextlib import contextmanager
import os
import time


@contextmanager
def lock(root):
    path = root/"worker.lock"
    handle = path.open("a+b")
    handle.seek(0)
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError("A PSYCON research worker is already running for this data directory") from exc
    try:
        yield
    finally:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def run(service, once=False):
    from .research import process_run
    with lock(service.store.root):
        service.store.execute("UPDATE llm_runs SET status='failed',error='Worker was interrupted; queue a new run' WHERE status='running'")
        # The exclusive lock proves old audio jobs have no live owner. Resume immediately.
        service.store.execute("UPDATE sessions SET lease_until=0 WHERE status='processing'")
        while True:
            session = service.process_next()
            interpretation = process_run(service) if session is None else None
            if session:
                print(f"Session {session['id']}: {session['status']}", flush=True)
            if interpretation:
                print(f"Interpretation {interpretation['id']}: {interpretation['status']}", flush=True)
            if once:
                return
            if session is None and interpretation is None:
                time.sleep(1)
