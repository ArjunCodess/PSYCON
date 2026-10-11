"""Queryable study lineage exports. Source bytes are separately downloadable."""
import base64
from .store import public


def study_export(store,sid,*,include_source_bytes=True):
    store.session(sid)
    query_tables={
        'participants':('session_participants','session_id'), 'speaker_mappings':('speaker_mappings','session_id'),
        'imports':('annotation_imports','session_id'), 'predictions':('model_predictions','session_id')}
    result={name:store.rows('SELECT * FROM '+table+' WHERE '+column+'=%s',(sid,)) for name,(table,column) in query_tables.items() if name!='imports'}
    with store.connect() as db:
        sources=[]
        columns='*' if include_source_bytes else 'id,session_id,owner_id,filename,media_type,sha256,mapping,preview,status,created_at'
        for row in db.execute('SELECT '+columns+' FROM annotation_imports WHERE session_id=%s',(sid,)):
            item=dict(row)
            if include_source_bytes:
                item['source_base64']=base64.b64encode(bytes(item['source_bytes'])).decode() if item['source_bytes'] is not None else None
                item.pop('source_bytes')
            sources.append(public(item))
        result['imports']=sources
        attachments=[]
        columns='a.*' if include_source_bytes else 'a.id,a.submission_id,a.filename,a.media_type,a.sha256'
        for row in db.execute('SELECT '+columns+' FROM annotation_attachments a JOIN annotation_submissions s ON s.id=a.submission_id JOIN session_participants p ON p.id=s.participant_id WHERE p.session_id=%s',(sid,)):
            item=dict(row)
            if include_source_bytes:item['source_base64']=base64.b64encode(bytes(item.pop('source_bytes'))).decode()
            attachments.append(public(item))
        result['attachments']=attachments
    for table in ('consent_records','annotation_submissions'):
        result[table]=store.rows('SELECT t.* FROM '+table+' t JOIN session_participants p ON p.id=t.participant_id WHERE p.session_id=%s',(sid,))
    for table in ('annotation_answers','annotation_context_flags','annotation_validity_checks','annotation_pattern_summaries','annotation_reviews'):
        result[table]=store.rows('SELECT t.* FROM '+table+' t JOIN annotation_submissions s ON s.id=t.submission_id JOIN session_participants p ON p.id=s.participant_id WHERE p.session_id=%s',(sid,))
    for table in ('annotation_evidence','annotation_adjudications'):
        result[table]=store.rows('SELECT t.* FROM '+table+' t JOIN annotation_answers a ON a.id=t.answer_id JOIN annotation_submissions s ON s.id=a.submission_id JOIN session_participants p ON p.id=s.participant_id WHERE p.session_id=%s',(sid,))
    result['form_definitions']=store.rows('SELECT * FROM form_definitions');result['form_items']=store.rows('SELECT * FROM form_items')
    result['snapshots']=store.rows('SELECT DISTINCT s.* FROM training_snapshots s JOIN training_examples e ON e.snapshot_id=s.id WHERE e.session_id=%s',(sid,))
    result['split_assignments']=store.rows('SELECT a.*,e.snapshot_id,e.participant_id FROM split_assignments a JOIN training_examples e ON e.id=a.example_id WHERE e.session_id=%s',(sid,))
    result['models']=store.rows('SELECT DISTINCT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id JOIN training_examples e ON e.snapshot_id=r.snapshot_id WHERE e.session_id=%s',(sid,))
    result['evaluations']=store.rows('SELECT DISTINCT v.* FROM model_evaluations v JOIN model_versions m ON m.id=v.model_id JOIN training_runs r ON r.id=m.run_id JOIN training_examples e ON e.snapshot_id=r.snapshot_id WHERE e.session_id=%s',(sid,))
    result['reanalysis_requests']=store.rows('SELECT * FROM reanalysis_requests WHERE session_id=%s OR parent_session_id=%s',(sid,sid))
    result['source_reviews']=store.rows('SELECT * FROM source_reviews WHERE session_id=%s ORDER BY revision',(sid,))
    result['llm_runs']=store.rows('SELECT * FROM llm_runs WHERE session_id=%s ORDER BY created_at',(sid,))
    result['llm_generation_attempts']=store.rows('SELECT a.* FROM llm_generation_attempts a JOIN llm_runs r ON r.id=a.run_id WHERE r.session_id=%s ORDER BY a.created_at',(sid,))
    result['report_review_revisions']=store.rows('SELECT a.* FROM report_review_revisions a JOIN llm_runs r ON r.id=a.run_id WHERE r.session_id=%s',(sid,))
    result['behavior_review_revisions']=store.rows('SELECT a.* FROM behavior_review_revisions a JOIN evidence e ON e.id=a.evidence_id WHERE e.session_id=%s',(sid,))
    result['llm_claims']=store.rows('SELECT c.* FROM llm_claims c JOIN llm_runs r ON r.id=c.run_id WHERE r.session_id=%s',(sid,))
    result['llm_claim_evidence']=store.rows('SELECT e.* FROM llm_claim_evidence e JOIN llm_claims c ON c.id=e.claim_id JOIN llm_runs r ON r.id=c.run_id WHERE r.session_id=%s',(sid,))
    result['assets']=store.rows('SELECT a.* FROM assets a JOIN session_assets s ON s.asset_id=a.id WHERE s.session_id=%s',(sid,))
    return result
