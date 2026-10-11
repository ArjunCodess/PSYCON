"""Short queue transactions, renewable leases, and fenced result publication."""
from contextlib import contextmanager
from datetime import datetime, timezone
import threading
from uuid import uuid4

from .store import uid, public, StaleJob


def enqueue(store, kind, subject, revision, payload=None, db=None):
    def save(connection):
        return connection.execute("INSERT INTO jobs(id,kind,subject_id,owner_id,input_revision,payload) VALUES (%s,%s,%s,'local',%s,%s) "
                                  'ON CONFLICT(kind,subject_id,input_revision) DO UPDATE SET subject_id=excluded.subject_id RETURNING *',
                                  (uid(),kind,subject,revision, __import__('psycopg').types.json.Jsonb(payload or {}))).fetchone()
    if db is not None:
        return public(save(db))
    with store.connect() as connection:
        return public(save(connection))


def claim(store, kind, owner=None, seconds=120):
    owner=owner or str(uuid4())
    with store.connect() as db:
        db.execute("UPDATE jobs j SET status='failed',error='Retry budget exhausted',finished_at=now() WHERE kind=%s AND status='running' AND lease_until<now() AND attempt>=max_attempts AND NOT EXISTS (SELECT 1 FROM worker_heartbeats w WHERE w.owner=j.owner AND w.seen_at>now()-interval '120 seconds')", (kind,))
        row=db.execute("SELECT * FROM jobs j WHERE kind=%s AND attempt<max_attempts AND available_at<=now() AND "
                       "(status='queued' OR (status='running' AND lease_until<now() AND NOT EXISTS "
                       "(SELECT 1 FROM worker_heartbeats w WHERE w.owner=j.owner AND w.seen_at>now()-interval '120 seconds'))) "
                       'ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED', (kind,)).fetchone()
        if not row:
            return None
        db.execute('INSERT INTO worker_heartbeats VALUES (%s,now()) ON CONFLICT(owner) DO UPDATE SET seen_at=now()', (owner,))
        return public(db.execute("UPDATE jobs SET status='running',owner=%s,attempt=attempt+1,lease_until=now()+%s*interval '1 second',heartbeat_at=now(),error=NULL WHERE id=%s RETURNING *", (owner,seconds,row['id'])).fetchone())


def cancel(store, job_id):
    store.execute("UPDATE jobs SET status='canceled',finished_at=now() WHERE id=%s AND status IN ('queued','running')", (job_id,))


@contextmanager
def lease(store, job, *, gpu=False):
    owner=job['owner']; stop=threading.Event()
    if gpu:
        with store.connect() as db:
            got=db.execute("INSERT INTO resource_leases VALUES ('gpu',%s,now()+interval '120 seconds') ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,lease_until=excluded.lease_until WHERE resource_leases.lease_until<now() RETURNING name", (owner,)).fetchone()
            if not got:
                db.execute("UPDATE jobs SET status='queued',owner=NULL,lease_until=NULL,heartbeat_at=NULL,available_at=now()+interval '5 seconds',attempt=attempt-1 WHERE id=%s AND owner=%s", (job['id'],owner))
        if not got:
            raise StaleJob('GPU is leased by another worker; job remains queued')
    def beat():
        while not stop.wait(20):
            try:
                with store.connect() as db:
                    db.execute("UPDATE jobs SET lease_until=now()+interval '120 seconds',heartbeat_at=now() WHERE id=%s AND owner=%s AND attempt=%s AND status='running'", (job['id'],owner,job['attempt']))
                    db.execute('UPDATE worker_heartbeats SET seen_at=now() WHERE owner=%s',(owner,))
                    if gpu:
                        db.execute("UPDATE resource_leases SET lease_until=now()+interval '120 seconds' WHERE name='gpu' AND owner=%s", (owner,))
            except Exception:
                return  # Loss of DB cannot authorize later publication.
    thread=threading.Thread(target=beat,daemon=True); thread.start()
    store.fence=(job['id'],owner,job['attempt'],job['input_revision'])
    try:
        yield
    finally:
        store.fence=None
        stop.set(); thread.join(timeout=1)
        if gpu:
            with store.connect() as db:
                db.execute("DELETE FROM resource_leases WHERE name='gpu' AND owner=%s", (owner,))


def retryable(error):
    import psycopg
    from urllib.error import URLError,HTTPError
    if isinstance(error,HTTPError): return error.code in (408,429,500,502,503,504)
    if isinstance(error,(TimeoutError,ConnectionError,psycopg.OperationalError,URLError)): return True
    cause=error.__cause__
    return retryable(cause) if cause is not None and cause is not error else False


def finish(store, job, result=None, error=None, retry=False):
    from psycopg.types.json import Jsonb
    with store.connect() as db:
        requeue=bool(error and retry and job['attempt']<job['max_attempts'])
        status='queued' if requeue else 'failed' if error else 'complete'
        count=db.execute("UPDATE jobs SET status=%s,result=%s,error=%s,finished_at=CASE WHEN %s THEN NULL ELSE now() END,available_at=now()+%s*interval '1 second',lease_until=NULL WHERE id=%s AND owner=%s AND attempt=%s AND input_revision=%s AND status='running' AND lease_until>now()", (status,Jsonb(result) if result is not None else None,error,requeue,min(60,5*2**job['attempt']) if requeue else 0,job['id'],job['owner'],job['attempt'],job['input_revision'])).rowcount
        if not count:
            raise StaleJob('Stale completion withheld')
