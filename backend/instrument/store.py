"""PostgreSQL storage. Schema changes are an explicit operator command."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import time
import threading
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def decode(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def public(value):
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [public(v) for v in value]
    return value


def encode(value):
    return json.dumps(public(value), ensure_ascii=False, allow_nan=False, sort_keys=True)


def external_row(row):
    result=public(dict(row))
    # Deliberate database-to-transcript contract, not a SQL rewrite.
    if 'start_s' in result and 'end_s' in result and ('speaker_id' in result or 'utterance_id' in result):
        result['start']=result.pop('start_s')
        result['end']=result.pop('end_s')
    elif 'start_s' in result and 'kind' in result and 'source' in result:
        result['start']=result.pop('start_s')
    return result


JSON_COLUMNS = {'sessions': {'participant_ids', 'config', 'versions'}, 'stages': {'output'},
                'evidence': {'context'}, 'baseline_profiles': {'source_sessions', 'statistics'},
                'archetype_features': {'distribution'}, 'comparisons': {'dimensions'},
                'llm_runs': {'input', 'output', 'configuration'}, 'llm_generation_attempts': {'output'}}


class StaleJob(RuntimeError):
    pass


class Store:
    def __init__(self, root, database_url=None, schema=None, role=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.url = database_url or os.getenv('PSYCON_DATABASE_URL')
        if not self.url or not self.url.startswith(('postgresql://', 'postgres://')):
            raise RuntimeError('PSYCON_DATABASE_URL must explicitly identify PostgreSQL; no fallback is available')
        self.schema = schema or os.getenv('PSYCON_DATABASE_SCHEMA', 'psycon')
        if not re.fullmatch(r'psycon(?:_test_[a-z0-9]+)?', self.schema):
            raise ValueError('Use the canonical psycon schema or an isolated psycon_test_ schema')
        self.role=role or os.getenv('PSYCON_DATABASE_ROLE')
        if self.role and self.role not in ('psycon_web','psycon_worker','psycon_trainer'):
            raise ValueError('Unknown application database role')
        # Transaction poolers reject startup options and may change backends
        # between transactions. Apply every setting inside each transaction.
        self.pool = ConnectionPool(self.url, min_size=0, max_size=8, timeout=15, open=True,
                                   kwargs={'connect_timeout': 8, 'row_factory': dict_row,
                                           'prepare_threshold': None})
        self._local = threading.local()

    def local_path(self, value):
        """Resolve registered host paths through explicit container mount mappings."""
        mappings=json.loads(os.getenv('PSYCON_PATH_MAP','{}'))
        for source,target in mappings.items():
            path=PureWindowsPath(value); root=PureWindowsPath(source)
            if path.is_relative_to(root):
                relative=path.relative_to(root)
                if '..' in relative.parts: raise ValueError('Registered path escapes its mount')
                return Path(target).joinpath(*relative.parts).resolve()
        if os.name!='nt' and PureWindowsPath(value).drive:
            raise ValueError('Registered Windows path needs PSYCON_PATH_MAP')
        return Path(value).resolve()

    @property
    def fence(self):
        return getattr(self._local, 'fence', None)

    @fence.setter
    def fence(self, value):
        self._local.fence = value

    @contextmanager
    def connect(self):
        with self.pool.connection() as db:
            db.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(self.schema)))
            db.execute('SET LOCAL statement_timeout = 30000')
            if self.role:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(self.role)))
            if self.fence:
                job, owner, attempt, revision = self.fence
                current = db.execute('SELECT * FROM jobs WHERE id=%s FOR UPDATE', (job,)).fetchone()
                if (not current or current['status'] != 'running' or current['owner'] != owner
                        or current['attempt'] != attempt or current['input_revision'] != revision
                        or current['lease_until'] < datetime.now(timezone.utc)):
                    raise StaleJob('Job lease expired, canceled, or superseded; result withheld')
            yield db

    def migrate(self):
        with self.connect() as db:
            db.execute('SELECT pg_advisory_xact_lock(%s)', (0x50535944,))
            db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            for path in sorted(Path(__file__).with_name('migrations').glob('*.sql')):
                body = path.read_text(encoding='utf-8-sig')
                digest = hashlib.sha256(body.encode()).hexdigest()
                old = db.execute('SELECT sha256 FROM schema_migrations WHERE version=%s', (path.name,)).fetchone()
                if old:
                    if old['sha256'] != digest:
                        raise RuntimeError(f'Applied migration changed: {path.name}')
                    continue
                db.execute(body)
                db.execute('INSERT INTO schema_migrations(version,sha256) VALUES (%s,%s)', (path.name,digest))
            if self.schema=='psycon':
                db.execute(Path(__file__).with_name('permissions.sql').read_text(encoding='utf-8-sig'))

    def ready(self):
        try:
            return self.one('SELECT count(*) AS n FROM schema_migrations')['n'] == len(list(Path(__file__).with_name('migrations').glob('*.sql')))
        except (psycopg.Error, PoolTimeout, TimeoutError):
            return False

    def rows(self, query, params=()):
        with self.connect() as db:
            return [external_row(r) for r in db.execute(query, params)]

    def one(self, query, params=()):
        rows = self.rows(query, params)
        if not rows:
            raise LookupError('Record not found')
        return rows[0]

    def execute(self, query, params=()):
        with self.connect() as db:
            return db.execute(query, params).rowcount

    def insert(self, table, row, db=None):
        if table in ('turns','utterances','words','evidence','interactions'):
            row={('start_s' if k=='start' else 'end_s' if k=='end' else k):v for k,v in row.items()}
        values = [Jsonb(decode(v)) if k in JSON_COLUMNS.get(table, set()) and v is not None
                  else Jsonb(v) if isinstance(v, (dict,list)) else v for k,v in row.items()]
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            sql.Identifier(self.schema, table), sql.SQL(',').join(map(sql.Identifier,row)),
            sql.SQL(',').join(sql.Placeholder() for _ in row))
        if db is not None:
            db.execute(query, values)
        else:
            self.execute(query, values)

    def session(self, session_id):
        row = self.one("SELECT * FROM sessions WHERE id=%s AND owner_id='local'", (session_id,))
        row.pop('original_path', None)
        return row

    def stage(self, session_id, name, status, output=None, error=None):
        self.execute('INSERT INTO stages VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(session_id,name) DO UPDATE SET '
                     'status=excluded.status, finished_at=excluded.finished_at, output=excluded.output, error=excluded.error',
                     (session_id,name,status,now(),now() if status!='running' else None,
                      Jsonb(output) if output is not None else None,error))

    def claim(self, worker_id, lease_seconds=120):
        with self.connect() as db:
            row = db.execute("SELECT id FROM sessions WHERE status='queued' OR (status='processing' AND lease_until < %s) "
                             'ORDER BY recorded_at,created_at LIMIT 1 FOR UPDATE SKIP LOCKED', (time.time(),)).fetchone()
            if row:
                db.execute("UPDATE sessions SET status='processing',worker_id=%s,lease_until=%s,error=NULL WHERE id=%s",
                           (worker_id,time.time()+lease_seconds,row['id']))
                return row['id']
        return None

    def heartbeat(self, session_id, worker_id):
        return self.execute("UPDATE sessions SET lease_until=%s WHERE id=%s AND worker_id=%s AND status='processing'",
                            (time.time()+120,session_id,worker_id))

    def invalidate(self):
        with self.connect() as db:
            db.execute('DELETE FROM baseline_profiles')
            db.execute('DELETE FROM comparisons')
            db.execute("UPDATE llm_runs SET status='stale',error='History or identity changed; queue a new run' WHERE condition='C' AND status IN ('complete','queued','running')")
