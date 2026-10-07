"""Queryable local storage, short transactions, and durable worker leases."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "psycon.sqlite3"
        with self.connect() as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
            columns = {r[1] for r in db.execute("PRAGMA table_info(llm_runs)")}
            for column in ("system_prompt", "configuration"):
                if column not in columns:
                    db.execute(f"ALTER TABLE llm_runs ADD COLUMN {column} TEXT")
            db.execute("INSERT OR IGNORE INTO users VALUES (?,?)", ("local", "Local researcher"))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, params=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        if not rows:
            raise LookupError("Record not found")
        return rows[0]

    def execute(self, sql, params=()):
        with self.connect() as db:
            db.execute(sql, params)

    def insert(self, table, row, db=None):
        # Table names and columns come only from internal code.
        sql = f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})"
        if db is not None:
            db.execute(sql, tuple(row.values()))
        else:
            self.execute(sql, tuple(row.values()))

    def session(self, session_id):
        row = self.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        for key in ("config", "versions", "participant_ids"):
            row[key] = json.loads(row[key])
        row.pop("original_path", None)
        return row

    def stage(self, session_id, name, status, output=None, error=None):
        self.execute(
            "INSERT INTO stages VALUES (?,?,?,?,?,?,?) ON CONFLICT(session_id,name) DO UPDATE SET "
            "status=excluded.status, finished_at=excluded.finished_at, output=excluded.output, error=excluded.error",
            (session_id, name, status, now(), now() if status != "running" else None,
             encode(output) if output is not None else None, error),
        )

    def claim(self, worker_id, lease_seconds=120):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM sessions WHERE status='queued' OR "
                             "(status='processing' AND lease_until < ?) ORDER BY recorded_at,created_at LIMIT 1",
                             (time.time(),)).fetchone()
            if row:
                db.execute("UPDATE sessions SET status='processing',worker_id=?,lease_until=?,error=NULL WHERE id=?",
                           (worker_id, time.time()+lease_seconds, row[0]))
                return row[0]
        return None

    def heartbeat(self, session_id, worker_id):
        self.execute("UPDATE sessions SET lease_until=? WHERE id=? AND worker_id=? AND status='processing'",
                     (time.time()+120, session_id, worker_id))

    def invalidate(self):
        """Identity edits/deletion make derived history stale; rebuild from retained evidence."""
        with self.connect() as db:
            db.execute("DELETE FROM baseline_profiles")
            db.execute("DELETE FROM comparisons")
            db.execute("UPDATE llm_runs SET status='stale',error='History or identity changed; queue a new run' "
                       "WHERE condition='C' AND status IN ('complete','queued','running')")
