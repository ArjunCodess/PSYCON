"""Registered, exact-name local assets. Media and models never enter database bytes."""
import hashlib
import mimetypes
from pathlib import Path
from .store import uid


def hash_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def register(store,path,kind,*,root=None,db=None,digest=None):
    path=Path(path).resolve(strict=True); root=Path(root or path.parent).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Asset must be a file beneath its registered storage root')
    root_id=hashlib.sha256(str(root).encode()).hexdigest()
    row=dict(id=uid(),owner_id='local',kind=kind,root_id=root_id,relative_path=path.relative_to(root).as_posix(),original_filename=path.name,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',byte_size=path.stat().st_size,sha256=digest or hash_file(path))
    def save(connection):
        connection.execute('INSERT INTO storage_roots VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(root_id,str(root),'models' if kind=='model' else 'media'))
        existing=connection.execute('SELECT * FROM assets WHERE root_id=%s AND relative_path=%s',(root_id,row['relative_path'])).fetchone()
        if existing:
            if existing['sha256']!=row['sha256']:
                raise ValueError('Registered original changed; overwriting is prohibited')
            return dict(existing)
        store.insert('assets',row,connection)
        return row
    if db is not None:
        return save(db)
    with store.connect() as connection:
        return save(connection)


def resolve(store,asset_id,verify=False):
    asset=store.one("SELECT a.*,r.path AS root_path FROM assets a JOIN storage_roots r ON r.id=a.root_id WHERE a.id=%s AND a.owner_id='local'",(asset_id,))
    if asset['state']=='deleted': raise ValueError('Registered asset was deleted under its retention policy')
    root=store.local_path(asset['root_path']); path=(root/asset['relative_path']).resolve()
    if not path.is_relative_to(root) or path.name!=asset['original_filename']:
        raise ValueError('Asset path violates its registration')
    if not path.is_file() or path.stat().st_size!=asset['byte_size']:
        raise ValueError('Registered asset is unavailable')
    if verify and hash_file(path)!=asset['sha256']:
        raise ValueError('Asset hash verification failed')
    return path
