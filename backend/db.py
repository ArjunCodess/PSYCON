from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, database_url: str, *, open_pool: bool = True) -> None:
        self.pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=8,
            open=open_pool,
            kwargs={"row_factory": dict_row},
        )

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator:
        with self.pool.connection() as connection:
            yield connection

    def migrate(self) -> None:
        sql = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
        last_error: UniqueViolation | None = None
        for _ in range(2):
            with self.connection() as connection:
                try:
                    with connection.transaction():
                        # Hold the lock until this transaction commits so two Gunicorn
                        # workers cannot create the same table type at once.
                        connection.execute("SELECT pg_advisory_xact_lock(%s)", (0x50535943,))
                        connection.execute(sql)
                    return
                except UniqueViolation as exc:
                    last_error = exc
        if last_error is not None:
            raise last_error

    def ping(self) -> bool:
        try:
            with self.connection() as connection:
                return connection.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
        except Exception:
            return False
