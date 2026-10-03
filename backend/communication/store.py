"""PostgreSQL persistence and a matching deterministic test store."""
from __future__ import annotations

import copy
import threading
from contextlib import contextmanager

from psycopg.types.json import Jsonb


class PostgresCommunicationStore:
    def __init__(self, database):
        self.database = database
        self.local = threading.local()

    def get(self, kind, key):
        with self.database.connection() as connection:
            row = connection.execute("SELECT body FROM communication_records WHERE kind=%s AND id=%s", (kind, key)).fetchone()
        return row["body"] if row else None

    def put(self, kind, row):
        with self.database.connection() as connection:
            connection.execute("""INSERT INTO communication_records(kind,id,profile_id,body)
                VALUES(%s,%s,%s,%s) ON CONFLICT(kind,id) DO UPDATE SET body=EXCLUDED.body""",
                (kind, row["id"], row.get("profile_id", row["id"]), Jsonb(row)))
        return copy.deepcopy(row)

    def rows(self, kind, profile_id=None):
        with self.database.connection() as connection:
            rows = connection.execute("SELECT body FROM communication_records WHERE kind=%s AND (%s::text IS NULL OR profile_id=%s) ORDER BY id", (kind, profile_id, profile_id)).fetchall()
        return [row["body"] for row in rows]

    def delete(self, kind, key):
        with self.database.connection() as connection:
            connection.execute("DELETE FROM communication_records WHERE kind=%s AND id=%s", (kind, key))

    @contextmanager
    def lock(self, key):
        held = getattr(self.local, "held", set())
        if key in held:
            yield
            return
        # Session locks serialize profile mutations and GPU jobs across worker processes.
        with self.database.connection() as connection:
            connection.execute("SELECT pg_advisory_lock(hashtextextended(%s, 17))", (key,))
            self.local.held = held | {key}
            try:
                yield
            finally:
                self.local.held = held
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 17))", (key,))


class MemoryCommunicationStore:
    def __init__(self):
        self.records = {}
        self.mutex = threading.RLock()

    def get(self, kind, key):
        return copy.deepcopy(self.records.get((kind, key)))

    def put(self, kind, row):
        self.records[kind, row["id"]] = copy.deepcopy(row)
        return copy.deepcopy(row)

    def rows(self, kind, profile_id=None):
        return [copy.deepcopy(row) for (table, _), row in self.records.items()
                if table == kind and (profile_id is None or row.get("profile_id", row["id"]) == profile_id)]

    def delete(self, kind, key):
        self.records.pop((kind, key), None)

    @contextmanager
    def lock(self, key):
        with self.mutex:
            yield
