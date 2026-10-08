"""Coordinated PostgreSQL/local-file backups with verified disposable restoration."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit,unquote,parse_qs
import psycopg
from psycopg import sql
from .store import encode,uid
from .assets import hash_file,resolve


def inventory(url,schemas=('public','psycon')):
    with psycopg.connect(url,connect_timeout=5) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        tables=db.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema=ANY(%s) ORDER BY table_schema,table_name",(list(schemas),)).fetchall()
        results={}
        for schema,table in tables:
            query=sql.SQL('SELECT row_to_json(t)::text FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(table))
            # Digest complete logical rows independent of physical ordering.
            hashes=sorted(hashlib.sha256(r[0].encode()).hexdigest() for r in db.execute(query))
            results[schema+'.'+table]=dict(count=len(hashes),sha256=hashlib.sha256(''.join(hashes).encode()).hexdigest())
        return results


def tool_command(name,url):
    parsed=urlsplit(url)
    binary=shutil.which(name)
    environment=os.environ.copy();environment['PGPASSWORD']=unquote(parsed.password or '')
    settings=parse_qs(parsed.query)
    environment['PGSSLMODE']=settings.get('sslmode',['prefer'])[0]
    environment['PGCHANNELBINDING']=settings.get('channel_binding',['prefer'])[0]
    if binary:
        return [binary,'-h',parsed.hostname,'-p',str(parsed.port or 5432),'-U',unquote(parsed.username or ''),'-d',parsed.path.lstrip('/')],environment
    if parsed.hostname in ('localhost','127.0.0.1') and (parsed.port or 5432)==5432:
        return ['docker','exec','-i','psycon-week4-postgres-1',name,'-U',unquote(parsed.username or ''),'-d',parsed.path.lstrip('/')],environment
    host='host.docker.internal' if parsed.hostname in ('localhost','127.0.0.1') else parsed.hostname
    return ['docker','run','--rm','-i','--env','PGPASSWORD','--env','PGSSLMODE','--env','PGCHANNELBINDING',os.getenv('PSYCON_POSTGRES_TOOLS_IMAGE','postgres:18-alpine'),name,'-h',host,'-p',str(parsed.port or 5432),'-U',unquote(parsed.username or ''),'-d',parsed.path.lstrip('/')],environment


def database_backup(url,directory,schemas=('public','psycon'),*,verification_url=None):
    destination=Path(directory).resolve(); destination.mkdir(parents=True,exist_ok=True)
    target=destination/'postgres.dump'
    if target.exists(): raise ValueError('Backup dump already exists; use a new backup directory')
    before=inventory(url,schemas)
    command,env=tool_command('pg_dump',url)
    with target.open('xb') as output:
        subprocess.run(command+['-Fc']+[arg for schema in schemas for arg in ('--schema',schema)],stdout=output,stderr=subprocess.PIPE,env=env,check=True)
    after=inventory(url,schemas)
    if before!=after: raise ValueError('Database changed during backup; pause writers and repeat')
    name='psycon_restore_'+uid().replace('-','')
    verification_url=verification_url or os.getenv('PSYCON_BACKUP_VERIFY_DATABASE_URL') or url
    with psycopg.connect(verification_url,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    parsed=urlsplit(verification_url);restore_url=parsed._replace(path='/'+name).geturl()
    try:
        if 'public' in schemas:
            with psycopg.connect(restore_url) as disposable:
                disposable.execute('DROP SCHEMA public')
        command,env=tool_command('pg_restore',restore_url)
        with target.open('rb') as source:
            subprocess.run(command+['--exit-on-error','--no-owner','--no-privileges'],stdin=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=True)
        restored=inventory(restore_url,schemas)
        if before!=restored: raise ValueError('Restored database counts or row hashes differ')
    finally:
        with psycopg.connect(verification_url,autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
    result=dict(database=before,schemas=list(schemas),dump_sha256=hash_file(target),restoration_verified=True)
    (destination/'database-verification.json').write_text(encode(result),encoding='utf-8')
    return result


def coordinated_backup(store,directory):
    destination=Path(directory).resolve()
    if destination.is_relative_to(store.root): raise ValueError('Backup must be outside the active store')
    assets=store.rows("SELECT * FROM assets WHERE state!='deleted' ORDER BY id");unique={}
    for asset in assets:
        unique.setdefault(asset['sha256'],asset)
    required=sum(a['byte_size'] for a in unique.values())
    destination.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(destination).free<required+512*1024*1024: raise ValueError('Backup destination lacks room for registered originals and models')
    db=database_backup(store.url,destination,schemas=(store.schema,));manifest=[]
    folder=destination/'assets';folder.mkdir()
    for digest,asset in unique.items():
        source=resolve(store,asset['id'],verify=True); copy=folder/digest/asset['original_filename'];copy.parent.mkdir()
        shutil.copyfile(source,copy)
        if hash_file(copy)!=digest: raise ValueError('Copied asset failed restore hash verification')
    for asset in assets:
        canonical=unique[asset['sha256']]
        manifest.append(dict(**asset,backup_path='assets/'+asset['sha256']+'/'+canonical['original_filename']))
    result=dict(schema=store.schema,database=db,assets=manifest,asset_restoration_verified=True,retention='Until withdrawal; never restore a revoked source without replaying deletion tombstones')
    (destination/'manifest.json').write_text(encode(result),encoding='utf-8')
    return result


def restore_backup(url,directory,local_destination):
    """Restore only to an empty database and a new local root, never overwrite active originals."""
    source=Path(directory).resolve(strict=True)
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('asset_restoration_verified') or not manifest['database'].get('restoration_verified'):
        raise ValueError('Backup lacks verified restoration metadata')
    dump=source/'postgres.dump'
    if hash_file(dump)!=manifest['database']['dump_sha256']:raise ValueError('Database dump hash mismatch')
    if inventory(url):raise ValueError('Restore destination must contain no application tables')
    destination=Path(local_destination).resolve()
    if destination.exists():raise ValueError('Local restore destination must be a new directory')
    destination.mkdir(parents=True)
    for asset in manifest['assets']:
        backup=(source/asset['backup_path']).resolve()
        if not backup.is_relative_to(source):raise ValueError('Backup path escapes its manifest root')
        root=destination/asset['root_id'];target=(root/asset['relative_path']).resolve()
        if not target.is_relative_to(root) or target.name!=asset['original_filename']:raise ValueError('Restored asset path violates its original registration')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output,backup.open('rb') as data:shutil.copyfileobj(data,output,1024*1024)
        if hash_file(target)!=asset['sha256']:raise ValueError('Restored local asset hash mismatch')
    command,env=tool_command('pg_restore',url)
    with dump.open('rb') as data:subprocess.run(command+['--exit-on-error','--no-owner'],stdin=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=True)
    if inventory(url,manifest['database'].get('schemas',['psycon']))!=manifest['database']['database']:raise ValueError('Restored database row hashes differ')
    with psycopg.connect(url) as db:
        for root_id in {a['root_id'] for a in manifest['assets']}:
            db.execute(sql.SQL('UPDATE {}.storage_roots SET path=%s WHERE id=%s').format(sql.Identifier(manifest.get('schema','psycon'))),(str(destination/root_id),root_id))
        for session_id,asset_id in db.execute(sql.SQL('SELECT id,asset_id FROM {}.sessions WHERE asset_id IS NOT NULL').format(sql.Identifier(manifest.get('schema','psycon')))).fetchall():
            asset=next(a for a in manifest['assets'] if a['id']==str(asset_id))
            db.execute(sql.SQL('UPDATE {}.sessions SET original_path=%s WHERE id=%s').format(sql.Identifier(manifest.get('schema','psycon'))),(str(destination/asset['root_id']/asset['relative_path']),session_id))
    return dict(database_restored=True,asset_count=len(manifest['assets']),local_root=str(destination),original_filenames_preserved=True)
