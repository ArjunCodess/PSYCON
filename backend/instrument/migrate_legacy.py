"""Explicit read-only SQLite import. This is the sole permitted SQLite dependency."""
import hashlib
import json
from pathlib import Path
import sqlite3
from psycopg import sql
from psycopg.types.json import Jsonb
from .assets import register,hash_file
from .store import uid,encode,decode,public,JSON_COLUMNS

TABLES=('users','workspace_settings','profiles','sessions','stages','speakers','turns','utterances','words','evidence','interactions','features','baseline_profiles','baseline_features','baseline_sessions','archetypes','archetype_features','traits','session_traits','trait_evidence','comparisons','llm_runs','evaluations','reviewer_annotations','behavior_annotations')


def read_source(path):
    path=Path(path).resolve(strict=True)
    if path.name!='psycon.sqlite3' or path.parent.name!='instrument' or 'verification' in str(path).lower():
        raise ValueError('Only the active instrument source is eligible; never import smoke verification stores')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def source_inventory(path):
    with read_source(path) as db:
        return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in TABLES}


def backup_source(path,destination):
    dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=True)
    backup=dest/'source.sqlite3'
    if backup.exists(): raise ValueError('Backup destination already contains a source snapshot')
    with read_source(path) as source,sqlite3.connect(backup) as target:
        source.backup(target)
    with sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True) as restored,read_source(path) as source:
        if restored.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Restored source failed integrity verification')
        for t in TABLES:
            left=sorted(encode(list(r)) for r in source.execute('SELECT * FROM '+t))
            right=sorted(encode(list(r)) for r in restored.execute('SELECT * FROM '+t))
            if left!=right: raise ValueError('Source backup restore mismatch: '+t)
    marker=dict(source=str(Path(path).resolve()),backup_sha256=hash_file(backup),counts=source_inventory(path),restoration_verified=True)
    (dest/'source-verification.json').write_text(encode(marker),encoding='utf-8')
    return marker


def migrate_source(store,path,verification):
    verification=Path(verification).resolve(strict=True)
    marker=json.loads(Path(verification).read_text(encoding='utf-8'))
    backup=Path(verification).parent/'source.sqlite3'
    if not marker.get('restoration_verified') or hash_file(backup)!=marker['backup_sha256'] or marker['counts']!=source_inventory(path):
        raise ValueError('A verified, unchanged source backup is required before import')
    if Path(marker['source']).resolve()!=Path(path).resolve():
        raise ValueError('Backup verification belongs to another source')
    with read_source(path) as current,sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True) as restored:
        for table in TABLES:
            def digest(db):
                hashes=sorted(hashlib.sha256(encode(list(row)).encode()).hexdigest() for row in db.execute('SELECT * FROM '+table))
                return hashlib.sha256(''.join(hashes).encode()).hexdigest()
            if digest(current)!=digest(restored): raise ValueError('Source changed since verified backup: '+table)
    if store.rows("SELECT id FROM deletion_tombstones WHERE kind='session' LIMIT 1"):
        raise ValueError('Session deletions exist; source replay is disabled to prevent resurrection')
    source_hash=hash_file(path);counts={};verification_result={}
    with read_source(path) as source,store.connect() as db:
        if not db.execute('SELECT id FROM migration_runs LIMIT 1').fetchone() and not db.execute('SELECT id FROM sessions LIMIT 1').fetchone():
            # Migration-seeded workspace defaults are not prior user data.
            for setting in source.execute('SELECT * FROM workspace_settings'):
                db.execute('UPDATE workspace_settings SET value=%s WHERE name=%s',(setting['value'],setting['name']))
        for table in TABLES:
            rows=[dict(r) for r in source.execute('SELECT * FROM '+table)]; counts[table]=len(rows)
            keys=[c['column_name'] for c in db.execute("SELECT k.column_name FROM information_schema.table_constraints t JOIN information_schema.key_column_usage k USING(constraint_catalog,constraint_schema,constraint_name) WHERE t.constraint_type='PRIMARY KEY' AND t.table_schema=%s AND t.table_name=%s ORDER BY k.ordinal_position",(store.schema,table))]
            for row in rows:
                for key in JSON_COLUMNS.get(table,set()):
                    if row.get(key) is not None: row[key]=decode(row[key])
                if table in ('turns','utterances','words','evidence','interactions'):
                    row={('start_s' if k=='start' else 'end_s' if k=='end' else k):v for k,v in row.items()}
                columns=list(row)
                values=[Jsonb(v) if isinstance(v,(dict,list)) else v for v in row.values()]
                query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING').format(sql.Identifier(store.schema,table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
                db.execute(query,values)
                # Compare every preserved source column, including nulls and source/citation IDs.
                where=sql.SQL(' AND ').join(sql.SQL('{} IS NOT DISTINCT FROM %s').format(sql.Identifier(k)) for k in keys)
                saved=db.execute(sql.SQL('SELECT {} FROM {} WHERE {}').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(store.schema,table),where),[row[k] for k in keys]).fetchone()
                if not saved: raise ValueError('Missing migrated key: '+table)
                for key,value in row.items():
                    actual=public(saved[key])
                    if key.endswith('_at') and value:
                        from datetime import datetime,timezone
                        value=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
                    if actual!=value:
                        # Defaults created by migration may only differ for the local display label.
                        if table=='users' and key=='label' and row['id']=='local': continue
                        raise ValueError(f'Migration conflict in {table}.{key}; existing destination will not be overwritten')
            verification_result[table]=dict(source_count=len(rows),keys_verified=len(rows),columns_verified=True)
        for session in source.execute('SELECT * FROM sessions'):
            path_value=Path(session['original_path'])
            if not path_value.is_file():
                verification_result.setdefault('missing_media',[]).append(session['id']);continue
            asset=register(store,path_value,'media',root=path_value.parent,db=db)
            if asset['sha256']!=session['sha256']: raise ValueError('Existing media hash mismatch')
            db.execute('UPDATE sessions SET asset_id=%s WHERE id=%s AND asset_id IS NULL',(asset['id'],session['id']))
            db.execute('INSERT INTO session_assets VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(session['id'],asset['id'],'original analysis input'))
        store.insert('migration_runs',dict(id=uid(),source_hash=source_hash,counts=counts,verification=verification_result),db)
    return dict(counts=counts,verification=verification_result,source_retained=True)
