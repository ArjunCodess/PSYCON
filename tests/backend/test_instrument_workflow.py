"""Canonical API journeys use disposable PostgreSQL records and synthetic media only."""
import io
import pytest
import psycopg
from backend.instrument.app import create_app
from backend.instrument import answers,jobs
from backend.instrument.exports import study_export
from backend.instrument.import_jobs import process_import
from tests.backend.test_instrument import service,add
from tests.backend.test_instrument_training import setup_participant,upload

HEADERS={'X-PSYCON-Request':'research-instrument'}


def test_foreign_owner_records_are_not_visible_or_mutable(service):
    sid=add(service);participant,speaker=setup_participant(service,sid)
    upload(service.store,sid,participant['id'],score=0)
    service.store.execute("INSERT INTO users VALUES ('other','Synthetic other owner')")
    service.store.execute("UPDATE sessions SET owner_id='other' WHERE id=%s",(sid,))
    client=create_app(instrument=service,testing=True).test_client()
    assert client.get('/api/instrument/state').json['sessions']==[]
    assert client.get('/api/instrument/sessions/'+sid).status_code==404
    assert client.delete('/api/instrument/sessions/'+sid,headers=HEADERS).status_code==404
    assert client.get('/api/instrument/speakers/'+speaker['id']+'/predictions').status_code==404
    assert client.post('/api/instrument/speakers/'+speaker['id']+'/predict',headers=HEADERS,json={}).status_code==404
    assert client.get('/api/instrument/training/readiness').json['rows']==[]


def test_unreachable_postgresql_refuses_reads_and_never_creates_sqlite(tmp_path,monkeypatch):
    from backend.instrument.service import Instrument
    monkeypatch.setenv('PSYCON_DATABASE_URL','postgresql://synthetic:synthetic@127.0.0.1:9/unreachable?connect_timeout=1')
    instrument=Instrument(tmp_path)
    try:
        client=create_app(instrument=instrument,testing=True).test_client()
        assert client.get('/health').status_code==503
        response=client.get('/api/instrument/state')
        assert response.status_code==503 and 'fabricated' in response.json['error']
        assert not list(tmp_path.rglob('*.sqlite*'))
    finally:instrument.store.pool.close()


def test_scanned_source_template_and_durable_import_journey(service):
    sid=add(service);participant,speaker=setup_participant(service,sid)
    client=create_app(instrument=service,testing=True).test_client()
    template=client.get('/api/instrument/forms/at-4.0/template?format=xlsx')
    assert template.status_code==200 and template.data.startswith(b'PK')
    preview=client.post(f'/api/instrument/sessions/{sid}/answers/preview',headers=HEADERS,data={
        'answers':(io.BytesIO(b'item,score,fair_opportunity,confidence\nI,0,yes,3\n'),'rating.csv'),
        'options':__import__('json').dumps(dict(participant_id=participant['id'],reviewer_id='rater'))})
    assert preview.status_code==200
    queued=client.post(f'/api/instrument/sessions/{sid}/answers/commit',headers=HEADERS,json=dict(import_id=preview.json['import_id'],durable=True))
    assert queued.status_code==202
    assert not service.store.rows('SELECT * FROM annotation_submissions')
    process_import(service.store)
    assert client.get('/api/instrument/jobs/'+queued.json['id']).json['status']=='complete'
    saved=service.store.one('SELECT id FROM annotation_submissions')
    source=b'%PDF-1.4\n% synthetic retention fixture\n%%EOF'
    response=client.post('/api/instrument/submissions/'+saved['id']+'/attachments',headers=HEADERS,data={'attachment':(io.BytesIO(source),'Paper.PDF')})
    assert response.status_code==201
    assert client.get('/api/instrument/attachments/'+response.json['id']+'/source').data==source
    duplicate=client.post('/api/instrument/submissions/'+saved['id']+'/attachments',headers=HEADERS,data={'attachment':(io.BytesIO(source),'Paper.PDF')})
    assert duplicate.json['duplicate']
    bad=client.post('/api/instrument/submissions/'+saved['id']+'/attachments',headers=HEADERS,data={'attachment':(io.BytesIO(b'not a pdf'),'Paper.PDF')})
    assert bad.status_code==400
    import zipfile,json
    archive_response=client.get(f'/api/instrument/sessions/{sid}/export/zip')
    assert archive_response.status_code==200
    with zipfile.ZipFile(io.BytesIO(archive_response.data)) as archive:
        assert 'study/annotation_answers.csv' in archive.namelist()
        assert 'study/llm_claim_evidence.csv' in archive.namelist()
        attachment_path=next(name for name in archive.namelist() if name.startswith('sources/attachments/'))
        assert archive.read(attachment_path)==source
        assert 'source_base64' not in json.loads(archive.read('study.json'))['imports'][0]
    answers_export=client.get(f'/api/instrument/sessions/{sid}/export/answers')
    assert answers_export.status_code==200 and b'reviewer_id' in answers_export.data and b'rater' in answers_export.data
    exported=study_export(service.store,sid)
    assert len(exported['attachments'])==1 and len(exported['assets'])==2
    assert {a['original_filename'] for a in exported['assets']}=={'conversation.wav','normalized.wav'}
    with pytest.raises(psycopg.Error):service.store.execute('UPDATE annotation_attachments SET filename=%s',('replacement.pdf',))


def test_retry_preserves_reviewed_mapping_and_cited_evidence(service):
    sid=add(service);participant,speaker=setup_participant(service,sid)
    upload(service.store,sid,participant['id'])
    before={table:service.store.rows('SELECT id FROM '+table+' WHERE session_id=%s ORDER BY id',(sid,)) for table in ('speakers','utterances','evidence')}
    service.store.execute("UPDATE sessions SET status='failed',error='Synthetic interruption after analysis' WHERE id=%s",(sid,))
    service.retry(sid)
    assert service.process_next()['status']=='complete'
    for table,records in before.items():
        assert service.store.rows('SELECT id FROM '+table+' WHERE session_id=%s ORDER BY id',(sid,))==records
    assert service.store.rows('SELECT * FROM speaker_mappings') and service.store.rows('SELECT * FROM annotation_answers')


def test_transient_retry_has_budget_and_no_stale_publication(service):
    key=jobs.enqueue(service.store,'import','synthetic-retry',1)['id']
    for attempt in range(1,4):
        job=jobs.claim(service.store,'import')
        assert job['attempt']==attempt
        jobs.finish(service.store,job,error='Synthetic timeout',retry=True)
        state=service.store.one('SELECT * FROM jobs WHERE id=%s',(key,))
        assert state['status']==('queued' if attempt<3 else 'failed')
        with pytest.raises(__import__('backend.instrument.store',fromlist=['StaleJob']).StaleJob):jobs.finish(service.store,job,{})
        service.store.execute('UPDATE jobs SET available_at=now() WHERE id=%s',(key,))
    assert jobs.claim(service.store,'import') is None


def test_role_permissions_allow_workflows_and_deny_schema_or_label_training_writes(service):
    from pathlib import Path
    from backend.instrument.store import Store
    sid=add(service)
    schema=service.store.schema
    permissions=Path('backend/instrument/permissions.sql').read_text(encoding='utf-8-sig')
    permissions=permissions.replace('SCHEMA psycon ',f'SCHEMA {schema} ').replace('psycon.',schema+'.')
    with service.store.connect() as db:db.execute(permissions)
    web=Store(service.store.root,schema=schema,role='psycon_web')
    worker=Store(service.store.root,schema=schema,role='psycon_worker')
    trainer=Store(service.store.root,schema=schema,role='psycon_trainer')
    try:
        p=answers.add_participant(web,sid,dict(code='permission-fixture'))
        preview=answers.preview(web,sid,b'item,score\nA,N/O\n','role.csv',dict(participant_id=p['id']))
        queued=__import__('backend.instrument.import_jobs',fromlist=['queue_commit']).queue_commit(web,sid,preview['import_id'],'')
        result=process_import(worker)
        assert result['status']=='complete',result.get('error')
        assert web.rows('SELECT * FROM annotation_submissions')
        from types import SimpleNamespace
        from backend.instrument.annotations import annotate_behavior
        from backend.instrument.provenance import review_source
        from backend.instrument.research import queue_runs,process_run
        from tests.backend.test_instrument import Provider
        review_source(web,sid,dict(kind='independent',reviewer_id='permission-reviewer',reason='Synthetic original recording review'))
        evidence=web.one('SELECT id FROM evidence WHERE session_id=%s ORDER BY start_s LIMIT 1',(sid,))['id']
        reviewed=SimpleNamespace(store=web,report=service.report)
        annotate_behavior(reviewed,evidence,dict(kind='proposal',reviewer_id='permission-reviewer'))
        annotate_behavior(reviewed,evidence,dict(kind='proposal',reviewer_id='permission-reviewer',notes='Synthetic correction'))
        speaker=web.one('SELECT id FROM speakers WHERE session_id=%s ORDER BY label LIMIT 1',(sid,))['id']
        queue_runs(reviewed,speaker,conditions=['A'],provider=Provider())
        assert process_run(SimpleNamespace(store=worker),Provider())['status']=='complete'
        assert worker.rows('SELECT * FROM llm_generation_attempts')

        for store in (web,worker,trainer):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):store.execute('CREATE TABLE forbidden_role_table(id int)')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            trainer.execute("INSERT INTO annotation_answers(id,submission_id,item_key,state,missing_reason,narrative) VALUES (gen_random_uuid(),gen_random_uuid(),'A','missing','','')")
    finally:
        for store in (web,worker,trainer):store.pool.close()


def test_original_video_registration_and_generated_text_are_idempotent(service,tmp_path):
    from pathlib import Path
    from backend.instrument.catalog import register_group_videos,normalize_retained_claims
    from backend.instrument.research import queue_runs,process_run
    sid=add(service)
    source=service.store.session(sid)
    originals=tmp_path/'group_discussions';originals.mkdir()
    original=originals/'Discussion.MOV'
    # Catalog registration hashes the original bytes without transcoding or renaming.
    original.write_bytes(Path(service.store.one('SELECT original_path FROM sessions WHERE id=%s',(sid,))['original_path']).read_bytes())
    service.store.execute('UPDATE sessions SET versions=versions || %s::jsonb WHERE id=%s',(__import__('json').dumps(dict(original_video=original.name)),sid))
    first=register_group_videos(service.store,originals)
    second=register_group_videos(service.store,originals)
    assert first['original_videos']==1 and first['new_analysis_links']==1 and second['new_analysis_links']==0
    assert original.exists() and original.name=='Discussion.MOV'
    asset=service.store.one("SELECT a.* FROM assets a JOIN session_assets s ON s.asset_id=a.id WHERE s.session_id=%s AND s.purpose='original group discussion video'",(sid,))
    assert asset['original_filename']=='Discussion.MOV'
    from tests.backend.test_instrument import Provider
    speaker=service.detail(sid)['speakers'][0]['id']
    run=queue_runs(service,speaker,conditions=['A'],provider=Provider())[0]
    assert process_run(service,Provider())['status']=='complete'
    stored=service.store.one('SELECT * FROM llm_runs WHERE id=%s',(run['id'],))
    assert stored['model']=='test-model' and stored['input'] and stored['output'] and stored['digest']=='synthetic-digest'
    claims=service.store.rows('SELECT * FROM llm_claims WHERE run_id=%s',(run['id'],))
    assert len(claims)==1
    citations=service.store.rows('SELECT * FROM llm_claim_evidence WHERE claim_id=%s',(claims[0]['id'],))
    assert citations and citations[0]['utterance_id']
    assert normalize_retained_claims(service.store)['normalized_claims']==0
    service.store.execute('DELETE FROM llm_claims WHERE run_id=%s',(run['id'],))
    assert normalize_retained_claims(service.store)['normalized_claims']==1
    assert normalize_retained_claims(service.store)['normalized_claims']==0
    exported=study_export(service.store,sid,include_source_bytes=False)
    assert exported['llm_runs'][0]['output']==stored['output'] and len(exported['llm_claim_evidence'])==1


def test_unknown_and_reviewed_excerpt_sources_cannot_leak_across_roles(service):
    from backend.instrument.provenance import review_source
    from backend.instrument import datasets
    first=add(service,day=1,phase=.1)
    second=add(service,day=2,phase=.2,split='evaluation')
    p,speaker=setup_participant(service,first)
    upload(service.store,first,p['id'])
    other=answers.add_participant(service.store,second,dict(code='P02'))
    other_speaker=service.store.one('SELECT id FROM speakers WHERE session_id=%s ORDER BY label LIMIT 1',(second,))['id']
    answers.map_participant(service.store,second,other['id'],dict(speaker_id=other_speaker,status='confirmed',reviewer_id='mapper',reason='Synthetic mapping'))
    service.store.insert('consent_records',dict(id=__import__('backend.instrument.store',fromlist=['uid']).uid(),participant_id=other['id'],status='documented',training_allowed=True,recorded_by='test',source='Synthetic consent'))
    upload(service.store,second,other['id'])
    readiness=datasets.readiness(service.store,'at')
    row=next(r for r in readiness['rows'] if r['participant_id']==other['id'])
    assert not row['eligible'] and any('ancestry' in reason for reason in row['reasons'])
    review=review_source(service.store,second,dict(kind='excerpt',source_session_id=first,reviewer_id='source-reviewer',reason='Synthetic excerpt relationship; different bytes must not create a new split group'))
    snapshot=datasets.freeze(service.store,'at')
    assert not snapshot['manifest']['examples']
    assert all(any('incompatible' in reason for reason in row['reasons']) for row in snapshot['manifest']['exclusions'])
    with pytest.raises(psycopg.Error):service.store.execute("UPDATE source_reviews SET kind='independent' WHERE id=%s",(review['id'],))
    with pytest.raises(ValueError):review_source(service.store,second,dict(kind='excerpt',reviewer_id='source-reviewer',reason='Missing original'))


def test_generation_retries_retain_each_error_and_output(service):
    from tests.backend.test_instrument import Provider
    from backend.instrument.research import queue_runs,process_run
    sid=add(service);speaker=service.detail(sid)['speakers'][0]['id']
    class TransientProvider(Provider):
        def generate(self,packet,digest):raise TimeoutError('Synthetic local model timeout')
    run=queue_runs(service,speaker,conditions=['A'],provider=TransientProvider())[0]
    assert process_run(service,TransientProvider())['status']=='failed'
    service.store.execute("UPDATE jobs SET available_at=now() WHERE subject_id=%s",(run['id'],))
    assert process_run(service,Provider())['status']=='complete'
    attempts=service.store.rows('SELECT * FROM llm_generation_attempts WHERE run_id=%s ORDER BY attempt',(run['id'],))
    assert [a['status'] for a in attempts]==['failed','complete']
    assert 'timeout' in attempts[0]['error'] and attempts[0]['output'] is None
    assert attempts[1]['output']['summary']=='Test report'
    with pytest.raises(psycopg.Error):service.store.execute('UPDATE llm_generation_attempts SET error=NULL WHERE id=%s',(attempts[0]['id'],))
    exported=study_export(service.store,sid,include_source_bytes=False)
    assert len(exported['llm_generation_attempts'])==2


def test_malformed_and_truncated_model_text_is_logged_and_withheld(service):
    from tests.backend.test_instrument import Provider
    from backend.instrument.research import queue_runs,process_run,LocalGenerationError
    sid=add(service);speaker=service.detail(sid)['speakers'][0]['id']
    class Malformed(Provider):
        def generate(self,packet,digest):return 'Synthetic incomplete model text {'
    class Truncated(Provider):
        def generate(self,packet,digest):raise LocalGenerationError('Synthetic output limit','Synthetic partial output')
    for provider,raw in [(Malformed(),'Synthetic incomplete model text {'),(Truncated(),'Synthetic partial output')]:
        run=queue_runs(service,speaker,conditions=['A'],provider=provider)[0]
        assert process_run(service,provider)['status']=='failed'
        row=service.store.one('SELECT * FROM llm_generation_attempts WHERE run_id=%s',(run['id'],))
        assert row['status']=='failed' and row['output']==raw
        assert not service.store.rows('SELECT * FROM llm_claims WHERE run_id=%s',(run['id'],))
        response=create_app(instrument=service,testing=True).test_client().get('/api/instrument/runs/'+run['id'])
        assert response.status_code==200 and response.json['output']==raw


def test_report_and_behavior_corrections_preserve_review_history(service):
    from tests.backend.test_instrument import Provider
    from backend.instrument.research import queue_runs,process_run,annotate,CRITERIA
    from backend.instrument.annotations import annotate_behavior
    from backend.instrument import datasets
    sid=add(service);p,speaker=setup_participant(service,sid)
    upload(service.store,sid,p['id'])
    run=queue_runs(service,speaker['id'],conditions=['A'],provider=Provider())[0]
    process_run(service,Provider())
    body=dict(reviewer_id='independent-report-rater',claim_index=0,notes='Original synthetic review',**{c:1 for c in CRITERIA})
    annotate(service.store,run['blind_id'],body)
    annotate(service.store,run['blind_id'],dict(body,grounding=2,notes='Corrected synthetic review'))
    archived=service.store.one('SELECT * FROM report_review_revisions')
    assert archived['previous_annotation']['grounding']==1 and archived['previous_annotation']['notes']=='Original synthetic review'
    snapshot=datasets.freeze(service.store,'at')
    evidence=service.store.one('SELECT id FROM evidence WHERE speaker_id=%s ORDER BY start_s LIMIT 1',(speaker['id'],))['id']
    event=dict(kind='proposal',reviewer_id='event-rater',notes='Original synthetic event')
    annotate_behavior(service,evidence,event)
    annotate_behavior(service,evidence,dict(event,notes='Corrected event context'))
    assert service.store.one('SELECT * FROM behavior_review_revisions')['previous_annotation']['notes']=='Original synthetic event'
    assert service.store.rows('SELECT * FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],))


def test_reviewed_merge_split_reanalysis_preserves_originals_and_citations(service):
    from pathlib import Path
    from backend.instrument.reanalysis import queue_reanalysis
    from backend.instrument.assets import hash_file
    from backend.instrument import datasets
    sid=add(service);p,speaker=setup_participant(service,sid)
    upload(service.store,sid,p['id'])
    original=Path(service.store.one('SELECT original_path FROM sessions WHERE id=%s',(sid,))['original_path'])
    digest=hash_file(original)
    old_evidence={r['id'] for r in service.store.rows('SELECT id FROM evidence WHERE session_id=%s',(sid,))}
    merged=dict(reviewer_id='synthetic-correction-reviewer',reason='Synthetic reviewed merge',max_speakers=2,reviewed_turns=[dict(speaker='ONE',start=.1,end=5.9)])
    first=queue_reanalysis(service,sid,merged)
    assert queue_reanalysis(service,sid,merged)['duplicate']
    assert service.process_next()['status']=='complete'
    assert len(service.detail(first['session_id'])['speakers'])==1
    assert hash_file(original)==digest
    assert {r['id'] for r in service.store.rows('SELECT id FROM evidence WHERE session_id=%s',(sid,))}==old_evidence
    split=dict(merged,reason='Synthetic reviewed split',reviewed_turns=[dict(speaker='ONE',start=.1,end=2.8),dict(speaker='TWO',start=3.,end=5.9)])
    second=queue_reanalysis(service,first['session_id'],split)
    assert service.process_next()['status']=='complete'
    assert len(service.detail(second['session_id'])['speakers'])==2
    assert not service.store.rows('SELECT * FROM session_participants WHERE session_id=%s',(second['session_id'],))
    assert service.store.one('SELECT * FROM source_reviews WHERE session_id=%s',(second['session_id'],))['kind']=='derived'
    with pytest.raises(ValueError):queue_reanalysis(service,sid,dict(merged,reviewed_turns=[dict(speaker='ONE',start=-1,end=2)]))
    service.delete(sid)
    assert original.exists() and hash_file(original)==digest
    client=create_app(instrument=service,testing=True).test_client()
    assert client.get('/api/instrument/sessions/'+second['session_id']+'/audio').status_code==200


def test_normalization_cannot_overwrite_an_original_named_normalized(service):
    from tests.backend.test_instrument import recording
    from pathlib import Path
    from backend.instrument.assets import hash_file
    from backend.instrument.store import now
    source=service.ingest(io.BytesIO(recording()),'normalized.wav',dict(recorded_at=now(),consent='documented'))
    path=Path(service.store.one('SELECT original_path FROM sessions WHERE id=%s',(source['id'],))['original_path'])
    digest=hash_file(path)
    assert service.process_next()['status']=='complete'
    assert hash_file(path)==digest and path.read_bytes()==recording()
    assert (path.parent/'derived'/'normalized.wav').is_file()


def test_reanalysis_does_not_count_its_own_source_as_personal_history(service):
    from tests.backend.test_instrument import person
    from backend.instrument.reanalysis import queue_reanalysis
    sid=add(service,day=1)
    profile=person(service)
    speaker=service.detail(sid)['speakers'][0]['id']
    service.map_speaker(speaker,dict(profile_id=profile,reviewer_id='history-reviewer'))
    child=queue_reanalysis(service,sid,dict(reviewer_id='history-reviewer',reason='Synthetic same-source reanalysis',max_speakers=2))
    service.process_next()
    new_speaker=service.detail(child['session_id'])['speakers'][0]['id']
    service.map_speaker(new_speaker,dict(profile_id=profile,reviewer_id='history-reviewer'))
    service.edit_metadata(child['session_id'],dict(recorded_at='2026-09-02T10:00:00+00:00'))
    assert service.report(new_speaker)['baseline']['sample_count']==0
    history=service.profile(profile)
    assert history['session_count']==2 and history['independent_recording_count']==1
    assert not history['recurring_traits']


def test_transaction_settings_reset_and_explicit_mount_mapping(service,monkeypatch,tmp_path):
    import json
    store=service.store
    with store.connect() as db:
        assert db.execute('SHOW search_path').fetchone()['search_path']==store.schema
        assert db.execute('SHOW statement_timeout').fetchone()['statement_timeout']=='30s'
    with store.pool.connection() as db:
        assert db.execute('SHOW search_path').fetchone()['search_path']!=store.schema
    monkeypatch.setenv('PSYCON_PATH_MAP',json.dumps({'C:/Research/PSYCON':str(tmp_path)}))
    assert store.local_path('c:/research/psycon/group_discussions/Original.MOV')==tmp_path/'group_discussions'/'Original.MOV'
    with pytest.raises(ValueError,match='escapes'):
        store.local_path('C:/Research/PSYCON/../private')


def test_docker_gateway_requires_explicit_network_configuration(service,monkeypatch):
    client=create_app(instrument=service,testing=True).test_client()
    monkeypatch.delenv('PSYCON_LOCAL_NETWORKS',raising=False)
    assert client.get('/api/instrument/state',environ_base={'REMOTE_ADDR':'172.18.0.1'}).status_code==403
    monkeypatch.setenv('PSYCON_LOCAL_NETWORKS','172.18.0.0/16')
    assert client.get('/api/instrument/state',environ_base={'REMOTE_ADDR':'172.18.0.1'}).status_code==200
    assert client.get('/api/instrument/state',environ_base={'REMOTE_ADDR':'203.0.113.1'}).status_code==403


def test_original_video_batch_preserves_citations_and_is_idempotent(service,tmp_path):
    from backend.instrument.catalog import queue_group_videos
    sid=add(service)
    session=service.store.one('SELECT * FROM sessions WHERE id=%s',(sid,))
    source=service.store.local_path(session['original_path'])
    original=tmp_path/'group_discussions';original.mkdir()
    (original/'Original.MOV').write_bytes(source.read_bytes())
    service.store.execute("UPDATE sessions SET dataset='Group discussion videos - full audio pipeline' WHERE id=%s",(sid,))
    evidence=service.store.rows('SELECT id FROM evidence WHERE session_id=%s ORDER BY id',(sid,))
    first=queue_group_videos(service,original)
    replay=queue_group_videos(service,original)
    assert first['original_videos']==1
    assert replay['analyses'][0]['duplicate']
    assert replay['analyses'][0]['session_id']==first['analyses'][0]['session_id']
    assert service.store.rows('SELECT id FROM evidence WHERE session_id=%s ORDER BY id',(sid,))==evidence
    assert service.store.one("SELECT count(*) n FROM jobs WHERE kind='speech' AND status='queued'")['n']==1


def test_gpu_contention_commits_requeue_without_spending_retry_budget(service):
    from backend.instrument.jobs import enqueue,claim,lease
    from backend.instrument.store import StaleJob
    first=enqueue(service.store,'speech','synthetic-first',1)
    second=enqueue(service.store,'speech','synthetic-second',1)
    active=claim(service.store,'speech')
    assert active['id']==first['id']
    with lease(service.store,active,gpu=True):
        # Independent checkout/thread has no publication fence for the first job.
        from backend.instrument.store import Store
        other=Store(service.store.root,schema=service.store.schema)
        try:
            waiting=claim(other,'speech')
            with pytest.raises(StaleJob,match='remains queued'):
                with lease(other,waiting,gpu=True): pass
            row=other.one('SELECT * FROM jobs WHERE id=%s',(second['id'],))
            assert row['status']=='queued' and row['attempt']==0 and row['owner'] is None
            assert row['lease_until'] is None
        finally:other.pool.close()


def test_whisper_failure_unloads_weights_and_preserves_explicit_precision(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    from backend.instrument.audio import WhisperAdapter
    unloaded=[];options=[]
    class FailingModel:
        def __init__(self,*args,**kwargs):
            options.append(kwargs);self.model=self
        def transcribe(self,*args,**kwargs):
            def segments():
                raise RuntimeError('synthetic GPU failure')
                yield
            return segments(),SimpleNamespace(language='en',language_probability=.9)
        def unload_model(self):unloaded.append(True)
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=FailingModel))
    adapter=WhisperAdapter(dict(transcription_model='large-v3',device='cuda',transcription_compute_type='int8_float16'))
    with pytest.raises(RuntimeError,match='synthetic GPU failure'):
        adapter.transcribe(np.ones(16000,dtype=np.int16),16000)
    assert unloaded==[True] and options[0]['compute_type']=='int8_float16'


def test_session_report_reads_do_not_scale_with_anonymous_speaker_count(service,monkeypatch):
    sid=add(service)
    from backend.instrument.store import uid
    for index in range(10):
        service.store.insert('speakers',dict(id=uid(),session_id=sid,label='SYNTHETIC_EXTRA_'+str(index),display_name='Anonymous synthetic speaker'))
    calls=[]
    original=service.store.rows
    def counted(query,params=()):
        calls.append(query)
        return original(query,params)
    monkeypatch.setattr(service.store,'rows',counted)
    detail=service.detail(sid)
    assert len(detail['reports'])==12
    assert len(calls)<=24
    assert len([q for q in calls if 'FROM archetype_features' in q])==1
    assert len([q for q in calls if 'FROM trait_evidence' in q])==1
    assert service.store.one('SELECT count(*) n FROM comparisons WHERE session_id=%s',(sid,))['n']==sum(len(r['archetypes']) for r in detail['reports'])
    assert {e for report in detail['reports'] for trait in report['traits'] for e in trait['evidence_ids']} <= {e['id'] for e in detail['evidence']}


def test_behavior_report_preserves_states_reviewers_and_research_inputs(service):
    from backend.instrument.research import packets
    from backend.instrument.store import uid
    sid=add(service);p,speaker=setup_participant(service,sid)
    before=packets(service,speaker['id'])
    options=dict(participant_id=p['id'],reviewer_id='psychologist')
    preview=answers.preview(service.store,sid,b'item,score,fair_opportunity,confidence\nA,0,yes,3\nB,N/O,no,1\nC,,,\n','synthetic-sheet.csv',options)
    saved=answers.commit(service.store,sid,preview['import_id'])
    service.store.insert('annotation_reviews',dict(id=uid(),submission_id=saved['submissions'][0],reviewer_id='second-reviewer',decision='approved',notes='Synthetic fixture'))
    report=service.report(speaker['id'])
    observed={r['item_key']:r for r in report['human_observations']}
    assert observed['A']['score']==0 and observed['B']['state']=='not_observed' and observed['C']['state']=='missing'
    assert all(r['reviewer_id']=='psychologist' and r['independent_reviewer_id']=='second-reviewer' and r['review_status']=='approved' for r in observed.values())
    assert all(r['description'] for r in observed.values())
    assert packets(service,speaker['id'])==before  # Human report data never enter held-out A/B/C inputs.
    correction=answers.preview(service.store,sid,b'item,score\nA,2\n','synthetic-correction.csv',options)
    answers.commit(service.store,sid,correction['import_id'],'Synthetic reviewed correction')
    report=service.report(speaker['id'])
    assert len(report['human_observations'])==3
    assert next(r for r in report['human_observations'] if r['item_key']=='A')['score']==2
    assert all(r['label_revision']==2 and r['review_status']=='needs_review' for r in report['human_observations'])


def test_behavior_report_never_reuses_superseded_mapping_or_withdrawn_answers(service):
    sid=add(service);p,speaker=setup_participant(service,sid)
    upload(service.store,sid,p['id'])
    assert service.report(speaker['id'])['human_observations']
    answers.map_participant(service.store,sid,p['id'],dict(speaker_id=speaker['id'],status='uncertain',reviewer_id='mapper',reason='Synthetic uncertainty'))
    assert service.report(speaker['id'])['human_observations']==[]
    assert service.store.rows('SELECT * FROM annotation_answers')
    answers.map_participant(service.store,sid,p['id'],dict(speaker_id=speaker['id'],status='confirmed',reviewer_id='mapper',reason='Synthetic re-review'))
    service.store.execute('UPDATE session_participants SET withdrawn_at=now() WHERE id=%s',(p['id'],))
    assert service.report(speaker['id'])['human_observations']==[]
