"""Reviewed recording ancestry keeps excerpts and re-encodings in one split group."""
from .store import uid


def source_groups(store):
    """Connected original/excerpt identities without longitudinal person grouping."""
    from .datasets import connected_components,latest
    rows=store.rows("SELECT s.id,s.sha256,s.versions,coalesce(array_agg(DISTINCT a.sha256) FILTER(WHERE a.sha256 IS NOT NULL),'{}') AS source_hashes FROM sessions s LEFT JOIN session_assets l ON l.session_id=s.id LEFT JOIN assets a ON a.id=l.asset_id GROUP BY s.id")
    reviews=latest(store.rows('SELECT * FROM source_reviews'),lambda r:r['session_id'],'revision')
    for row in rows:
        review=reviews.get(row['id'])
        if review and review['kind']!='uncertain':row['source_hashes'].append(review['source_hash'])
    return connected_components(rows,[])


def original_hash(store,sid,db):
    original=db.execute("SELECT a.sha256 FROM session_assets s JOIN assets a ON a.id=s.asset_id WHERE s.session_id=%s AND s.purpose='original group discussion video' ORDER BY a.id LIMIT 1",(sid,)).fetchone()
    return original['sha256'] if original else db.execute('SELECT sha256 FROM sessions WHERE id=%s',(sid,)).fetchone()['sha256']


def review_source(store,sid,body):
    kind=body.get('kind'); reviewer=str(body.get('reviewer_id','')).strip();reason=str(body.get('reason','')).strip()
    if kind not in ('independent','excerpt','derived','uncertain') or not reviewer or not reason:
        raise ValueError('Record the source relationship, reviewer, and the evidence used to check recording ancestry')
    source=body.get('source_session_id') or None
    if (kind in ('excerpt','derived')) != bool(source) or source==sid:
        raise ValueError('An excerpt or derived recording requires another original session; an independent or uncertain source must not select one')
    with store.connect() as db:
        session=db.execute("SELECT * FROM sessions WHERE id=%s AND owner_id='local' FOR UPDATE",(sid,)).fetchone()
        if not session:raise LookupError('Session not found')
        if session['status'] in ('queued','processing'):raise ValueError('Finish processing before reviewing recording ancestry')
        if source and not db.execute("SELECT id FROM sessions WHERE id=%s AND owner_id='local'",(source,)).fetchone():
            raise LookupError('Original source session not found')
        revision=db.execute('SELECT coalesce(max(revision),0)+1 AS n FROM source_reviews WHERE session_id=%s',(sid,)).fetchone()['n']
        row=dict(id=uid(),session_id=sid,revision=revision,kind=kind,source_session_id=source,source_hash=original_hash(store,source or sid,db),reviewer_id=reviewer,reason=reason)
        store.insert('source_reviews',row,db)
        # A newly recognized relationship can change every connected split. Invalidate
        # existing snapshots conservatively rather than leave fitted leakage in service.
        db.execute("INSERT INTO snapshot_invalidations(id,snapshot_id,reason) SELECT gen_random_uuid(),id,'Recording ancestry changed; freeze a new grouped snapshot' FROM training_snapshots")
        db.execute("UPDATE model_versions SET status='needs_retraining' WHERE status!='retired'")
        db.execute("UPDATE jobs SET status='canceled',error='Recording ancestry changed' WHERE kind='training' AND status IN ('queued','running')")
        db.execute("UPDATE training_runs SET status='canceled',error='Recording ancestry changed' WHERE status IN ('queued','training')")
        db.execute('DELETE FROM model_predictions')
        db.execute("UPDATE llm_runs SET status='stale',error='Supervised source ancestry changed' WHERE condition IN ('B','C') AND status IN ('queued','running','complete')")
    return row
