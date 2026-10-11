"""Durable commits of already validated, user-confirmed annotation previews."""
from .jobs import enqueue,claim,lease,finish,retryable
from .store import StaleJob
from .answers import commit


def queue_commit(store,sid,import_id,reason):
    row=store.one("SELECT * FROM annotation_imports WHERE id=%s AND session_id=%s AND owner_id='local'",(import_id,sid))
    if row['preview']['errors']: raise ValueError('Resolve import validation errors first')
    revision=store.session(sid)['input_revision']
    return enqueue(store,'import',str(import_id),revision,dict(session_id=sid,correction_reason=reason))


def process_import(store):
    job=claim(store,'import')
    if not job:return None
    try:
        with lease(store,job):
            try:
                result=commit(store,job['payload']['session_id'],job['subject_id'],job['payload']['correction_reason'])
                finish(store,job,result)
            except StaleJob:raise
            except Exception as exc:finish(store,job,error=str(exc)[:1500],retry=retryable(exc))
    except StaleJob:return None
    return store.one('SELECT id,status,error FROM jobs WHERE id=%s',(job['id'],))
