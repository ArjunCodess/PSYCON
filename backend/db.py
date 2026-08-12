from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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
        with self.connection() as connection:
            # Gunicorn workers can import the application concurrently. A database-level
            # lock prevents two workers from racing while PostgreSQL creates table types.
            connection.execute("SELECT pg_advisory_lock(%s)", (0x50535943,))
            try:
                connection.execute(sql)
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (0x50535943,))

    def ping(self) -> bool:
        try:
            with self.connection() as connection:
                return connection.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
        except Exception:
            return False
