"""Participant, annotation, dataset and model actions in the canonical application."""
import csv
import io
import hashlib
from pathlib import PureWindowsPath
from flask import jsonify, request, Response, send_file
from psycopg.types.json import Jsonb
from .routes import api, instrument, json_body
from .store import uid, encode
from . import answers, datasets, training


def scoped_participant(sid,pid):
    return answers.participant(instrument().store,sid,pid)


@api.get('/forms')
def forms():
    store=instrument().store
    return jsonify(forms=store.rows('SELECT * FROM form_definitions ORDER BY id'),items=store.rows('SELECT * FROM form_items ORDER BY form_id,key'))


@api.get('/forms/<form_id>/template')
def template(form_id):
    store=instrument().store
    form=store.one('SELECT * FROM form_definitions WHERE id=%s',(form_id,))
    columns=['participant','item','score','fair_opportunity','confidence','reviewer_id','source_type','narrative','evidence','validity','context_flags','patterns','metadata','component','missing_reason']+sorted(answers.METADATA_FIELDS)+list(answers.FLAGS)
    items=store.rows('SELECT * FROM form_items WHERE form_id=%s ORDER BY key',(form_id,))
    if request.args.get('format')=='xlsx':
        from openpyxl import Workbook
        workbook=Workbook();sheet=workbook.active;sheet.title='Answers';sheet.append(columns)
        for item in items:
            sheet.append([item['key'] if c=='item' else 'observer' if c=='source_type' else 'audio' if c=='component' else '' for c in columns])
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        output=io.BytesIO();workbook.save(output);output.seek(0)
        return send_file(output,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name=f'{form_id}-answers.xlsx')
    output=io.StringIO(newline=''); writer=csv.DictWriter(output,fieldnames=columns); writer.writeheader()
    for item in items:
        writer.writerow(dict(item=item['key'],source_type='observer',component='audio'))
    return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="{form_id}-answers.csv"'})


@api.post('/submissions/<submission_id>/attachments')
def attach_source(submission_id):
    store=instrument().store
    store.one("SELECT s.id FROM annotation_submissions s JOIN session_participants p ON p.id=s.participant_id WHERE s.id=%s AND p.owner_id='local' AND p.withdrawn_at IS NULL",(submission_id,))
    source=request.files.get('attachment')
    if not source: raise ValueError('Select a scanned PDF, PNG, or JPEG source')
    filename=source.filename or ''
    if not filename or PureWindowsPath(filename).name!=filename or '/' in filename or len(filename)>256:
        raise ValueError('Use a plain source filename')
    data=source.stream.read(answers.MAX_BYTES+1)
    if not data or len(data)>answers.MAX_BYTES: raise ValueError('Scanned sources must be between 1 byte and 10 MiB')
    media=None
    if filename.lower().endswith('.pdf') and data.startswith(b'%PDF-'): media='application/pdf'
    if filename.lower().endswith('.png') and data.startswith(b'\x89PNG\r\n\x1a\n'): media='image/png'
    if filename.lower().endswith(('.jpg','.jpeg')) and data.startswith(b'\xff\xd8\xff'): media='image/jpeg'
    if not media: raise ValueError('File contents must match a supported PDF, PNG, or JPEG extension')
    digest=hashlib.sha256(data).hexdigest()
    with store.connect() as db:
        db.execute('SELECT id FROM annotation_submissions WHERE id=%s FOR UPDATE',(submission_id,))
        existing=db.execute('SELECT id FROM annotation_attachments WHERE submission_id=%s AND sha256=%s',(submission_id,digest)).fetchone()
        key=str(existing['id']) if existing else uid()
        if not existing:
            store.insert('annotation_attachments',dict(id=key,submission_id=submission_id,filename=filename,media_type=media,sha256=digest,source_bytes=data),db)
    return jsonify(id=key,sha256=digest,duplicate=bool(existing)),201


@api.get('/attachments/<attachment_id>/source')
def attachment_download(attachment_id):
    row=instrument().store.one("SELECT a.* FROM annotation_attachments a JOIN annotation_submissions s ON s.id=a.submission_id JOIN session_participants p ON p.id=s.participant_id WHERE a.id=%s AND p.owner_id='local'",(attachment_id,))
    return send_file(io.BytesIO(bytes(row['source_bytes'])),mimetype=row['media_type'],as_attachment=True,download_name=row['filename'])


@api.post('/people')
def create_person():
    body=json_body(); code=str(body.get('code','')).strip()
    if not code or len(code)>100: raise ValueError('Use an anonymous person code of 1–100 characters')
    row=dict(id=uid(),owner_id='local',code=code)
    with instrument().store.connect() as db:
        instrument().store.insert('people',row,db)
        instrument().store.insert('profiles',dict(id=row['id'],user_id='local',label=code,created_at=__import__('backend.instrument.store',fromlist=['now']).now()),db)
    return jsonify(row),201


@api.get('/sessions/<sid>/participants')
def participants(sid):
    store=instrument().store; store.session(sid)
    rows=store.rows("SELECT * FROM session_participants WHERE session_id=%s AND owner_id='local' ORDER BY created_at",(sid,))
    return jsonify(consents=store.rows("SELECT c.* FROM consent_records c JOIN session_participants p ON p.id=c.participant_id WHERE p.session_id=%s AND p.owner_id='local' ORDER BY c.created_at,c.id",(sid,)),participants=rows,mappings=store.rows('SELECT * FROM speaker_mappings WHERE session_id=%s ORDER BY revision',(sid,)),people=store.rows("SELECT * FROM people WHERE owner_id='local'"))


@api.post('/sessions/<sid>/participants')
def create_participant(sid):
    return jsonify(answers.add_participant(instrument().store,sid,json_body())),201


@api.post('/sessions/<sid>/participants/<pid>/mapping')
def participant_mapping(sid,pid):
    return jsonify(answers.map_participant(instrument().store,sid,pid,json_body())),201


@api.post('/sessions/<sid>/participants/<pid>/consent')
def participant_consent(sid,pid):
    store=instrument().store; scoped_participant(sid,pid); body=json_body()
    if body.get('status') not in ('documented','withdrawn','not documented') or type(body.get('training_allowed')) is not bool or not body.get('recorded_by') or not body.get('source'):
        raise ValueError('Record consent status, training permission, recorder, and source')
    with store.connect() as db:
        store.insert('consent_records',dict(id=uid(),participant_id=pid,**{k:body[k] for k in ('status','training_allowed','recorded_by','source')}),db)
        if body['status']!='documented' or not body['training_allowed']: answers.invalidate_participant(store,pid,'Consent withdrawn or unavailable',db)
    return jsonify(status='saved'),201


@api.post('/sessions/<sid>/answers/preview')
def preview_answers(sid):
    source=request.files.get('answers')
    if not source: raise ValueError('Select a CSV or XLSX answer file')
    import json
    options=json.loads(request.form.get('options','{}'))
    if not isinstance(options,dict): raise ValueError('Import options must be an object')
    data=source.stream.read(answers.MAX_BYTES+1)
    return jsonify(answers.preview(instrument().store,sid,data,source.filename or '',options))


@api.post('/sessions/<sid>/answers/commit')
def commit_answers(sid):
    body=json_body()
    if body.get('durable') is True:
        from .import_jobs import queue_commit
        return jsonify(queue_commit(instrument().store,sid,body.get('import_id'),str(body.get('correction_reason','')))),202
    return jsonify(answers.commit(instrument().store,sid,body.get('import_id'),str(body.get('correction_reason',''))))


@api.post('/sessions/<sid>/participants/<pid>/answers')
def enter_answers(sid,pid):
    scoped_participant(sid,pid); body=json_body()
    if not isinstance(body.get('rows'),list): raise ValueError('Provide form answer rows')
    fields=sorted({k for row in body['rows'] for k in row})
    output=io.StringIO(newline=''); writer=csv.DictWriter(output,fieldnames=fields); writer.writeheader()
    for row in body['rows']:
        writer.writerow({k:encode(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    preview=answers.preview(instrument().store,sid,output.getvalue().encode(),'entered-answers.csv',dict(participant_id=pid,form_id=body.get('form_id','at-4.0'),source_type=body.get('source_type','observer'),reviewer_id=body.get('reviewer_id')))
    if preview['errors']: return jsonify(preview),400
    return jsonify(answers.commit(instrument().store,sid,preview['import_id'],str(body.get('correction_reason','')))),201


@api.get('/sessions/<sid>/participants/<pid>/answers')
def participant_answers(sid,pid):
    scoped_participant(sid,pid); store=instrument().store
    submissions=store.rows('SELECT * FROM annotation_submissions WHERE participant_id=%s ORDER BY revision DESC,created_at DESC',(pid,))
    attachments=store.rows('SELECT a.id,a.submission_id,a.filename,a.media_type,a.sha256 FROM annotation_attachments a JOIN annotation_submissions s ON s.id=a.submission_id WHERE s.participant_id=%s',(pid,))
    history={table:store.rows('SELECT t.* FROM '+table+' t JOIN annotation_submissions s ON s.id=t.submission_id WHERE s.participant_id=%s',(pid,)) for table in ('annotation_context_flags','annotation_validity_checks','annotation_pattern_summaries')}
    return jsonify(context_history=history,attachments=attachments,submissions=submissions,answers=store.rows('SELECT a.* FROM annotation_answers a JOIN annotation_submissions s ON s.id=a.submission_id WHERE s.participant_id=%s',(pid,)),evidence=store.rows('SELECT e.* FROM annotation_evidence e JOIN annotation_answers a ON a.id=e.answer_id JOIN annotation_submissions s ON s.id=a.submission_id WHERE s.participant_id=%s',(pid,)),reviews=store.rows('SELECT r.* FROM annotation_reviews r JOIN annotation_submissions s ON s.id=r.submission_id WHERE s.participant_id=%s',(pid,)))


@api.get('/sessions/<sid>/imports/<iid>/source')
def source_download(sid,iid):
    row=instrument().store.one("SELECT * FROM annotation_imports WHERE id=%s AND session_id=%s AND owner_id='local'",(iid,sid))
    if row['source_bytes'] is None: raise ValueError('Original source bytes were removed after a participant deletion; normalized surviving answers retain their provenance')
    return send_file(io.BytesIO(bytes(row['source_bytes'])),mimetype=row['media_type'],as_attachment=True,download_name=row['filename'])


@api.post('/submissions/<submission_id>/review')
def review_submission(submission_id):
    store=instrument().store; body=json_body()
    sub=store.one("SELECT s.* FROM annotation_submissions s JOIN session_participants p ON p.id=s.participant_id WHERE s.id=%s AND p.owner_id='local'",(submission_id,))
    reviewer=str(body.get('reviewer_id','')).strip()
    if not reviewer or reviewer==sub['reviewer_id'] or body.get('decision') not in ('approved','rejected','needs_review'):
        raise ValueError('An independent reviewer and review decision are required')
    with store.connect() as db:
        store.insert('annotation_reviews',dict(id=uid(),submission_id=submission_id,reviewer_id=reviewer,decision=body['decision'],notes=str(body.get('notes',''))),db)
        answers.invalidate_participant(store,sub['participant_id'],'Annotation review changed',db)
    return jsonify(status='saved'),201


@api.post('/answers/<aid>/adjudicate')
def adjudicate(aid):
    body=json_body(); store=instrument().store
    if type(body.get('score')) is not int or not 0<=body['score']<=4 or not body.get('reviewer_id') or not body.get('rationale'): raise ValueError('Adjudication requires score 0–4, reviewer, and rationale')
    row=store.one("SELECT s.participant_id FROM annotation_answers a JOIN annotation_submissions s ON s.id=a.submission_id JOIN session_participants p ON p.id=s.participant_id WHERE a.id=%s AND p.owner_id='local' AND p.withdrawn_at IS NULL",(aid,))
    with store.connect() as db:
        store.insert('annotation_adjudications',dict(id=uid(),answer_id=aid,**{k:body[k] for k in ('score','reviewer_id','rationale')}),db)
        answers.invalidate_participant(store,row['participant_id'],'Adjudication changed',db)
    return jsonify(status='saved'),201


@api.get('/training/readiness')
def readiness():
    return jsonify(datasets.readiness(instrument().store,request.args.get('family','at')))


@api.post('/training/snapshots')
def freeze():
    body=json_body()
    return jsonify(datasets.freeze(instrument().store,body.get('family','at'),body.get('seed',42),body.get('study','unseen_participant'))),201


@api.post('/training/runs')
def queue_training():
    body=json_body()
    return jsonify(training.queue(instrument().store,body.get('snapshot_id'),body.get('configuration'))),201


@api.get('/training')
def training_state():
    store=instrument().store
    snapshots=store.rows("SELECT * FROM training_snapshots WHERE owner_id='local' ORDER BY created_at DESC")
    for snapshot in snapshots:
        snapshot['readiness']=training.snapshot_summary(snapshot)
    return jsonify(prediction_speakers=store.rows("SELECT p.id,p.display_name,p.session_id,s.filename,s.recorded_at FROM speakers p JOIN sessions s ON s.id=p.session_id WHERE s.owner_id='local' AND s.status='complete' ORDER BY s.recorded_at DESC,p.label"),tasks=store.rows('SELECT * FROM training_tasks'),snapshots=snapshots,invalidations=store.rows("SELECT i.* FROM snapshot_invalidations i JOIN training_snapshots s ON s.id=i.snapshot_id WHERE s.owner_id='local'"),runs=store.rows("SELECT * FROM training_runs WHERE owner_id='local' ORDER BY created_at DESC"),events=store.rows("SELECT e.* FROM training_run_events e JOIN training_runs r ON r.id=e.run_id WHERE r.owner_id='local' ORDER BY e.created_at"),models=store.rows("SELECT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE r.owner_id='local' ORDER BY m.created_at DESC"),evaluations=store.rows("SELECT e.* FROM model_evaluations e JOIN model_versions m ON m.id=e.model_id JOIN training_runs r ON r.id=m.run_id WHERE r.owner_id='local'"),deployments=store.rows("SELECT d.* FROM model_deployments d JOIN model_versions m ON m.id=d.model_id JOIN training_runs r ON r.id=m.run_id WHERE r.owner_id='local' ORDER BY d.created_at DESC"))


@api.post('/jobs/<jid>/cancel')
def cancel_job(jid):
    from .jobs import cancel
    store=instrument().store; store.one("SELECT id FROM jobs WHERE id=%s AND owner_id='local'",(jid,)); cancel(store,jid)
    store.execute("UPDATE training_runs SET status='canceled' WHERE job_id=%s",(jid,))
    return jsonify(status='canceled')


@api.get('/jobs/<jid>')
def job_state(jid):
    return jsonify(instrument().store.one("SELECT id,kind,status,attempt,max_attempts,available_at,error,result FROM jobs WHERE id=%s AND owner_id='local'",(jid,)))


@api.post('/models/<mid>/<action>')
def deploy(mid,action):
    if action not in ('activate','rollback'): raise ValueError('Choose activate or rollback')
    body=json_body()
    return jsonify(training.activate(instrument().store,mid,body.get('operator_id'),body.get('reason'),exploratory=body.get('acknowledge_exploratory') is True,rollback=action=='rollback'))


@api.post('/speakers/<speaker_id>/predict')
def prediction(speaker_id):
    return jsonify(training.predict(instrument().store,speaker_id,json_body().get('context_windows')))


@api.get('/speakers/<speaker_id>/predictions')
def predictions(speaker_id):
    store=instrument().store; store.one('SELECT id FROM speakers WHERE id=%s',(speaker_id,))
    store.one("SELECT s.id FROM sessions s JOIN speakers p ON p.session_id=s.id WHERE p.id=%s AND s.owner_id='local'",(speaker_id,))
    return jsonify(predictions=store.rows('SELECT p.*,m.family,m.target,m.evaluation_status FROM model_predictions p JOIN model_versions m ON m.id=p.model_id WHERE speaker_id=%s ORDER BY p.created_at DESC',(speaker_id,)),evidence=store.rows('SELECT e.* FROM prediction_evidence e JOIN model_predictions p ON p.id=e.prediction_id WHERE p.speaker_id=%s',(speaker_id,)))


@api.post('/sessions/<sid>/participants/<pid>/withdraw')
def withdraw(sid,pid):
    scoped_participant(sid,pid); store=instrument().store
    with store.connect() as db:
        answers.invalidate_participant(store,pid,'Participant withdrawn',db)
        db.execute('UPDATE session_participants SET withdrawn_at=now() WHERE id=%s',(pid,))
        db.execute('UPDATE speakers SET profile_id=NULL WHERE id IN (SELECT speaker_id FROM speaker_mappings WHERE participant_id=%s)',(pid,))
    return jsonify(status='withdrawn',note='Dependent models need retirement or retraining; deleting source data does not erase its influence from weights')


@api.delete('/sessions/<sid>/participants/<pid>')
def delete_participant(sid,pid):
    from .deletion import delete_participant
    delete_participant(instrument().store,sid,pid)
    return jsonify(status='deleted',note='Affected model weights removed; affected backup generations must be purged before restoration')


@api.get('/training/agreement')
def agreement():
    from .agreement import agreement
    family=request.args.get('family','at')
    if family not in ('at','communication'): raise ValueError('Choose at or communication')
    return jsonify(agreement(instrument().store,family))


@api.get('/sessions/<sid>/source-reviews')
def source_reviews(sid):
    store=instrument().store
    store.one("SELECT id FROM sessions WHERE id=%s AND owner_id='local'",(sid,))
    return jsonify(reviews=store.rows('SELECT * FROM source_reviews WHERE session_id=%s ORDER BY revision DESC',(sid,)),sources=store.rows("SELECT id,filename,recorded_at FROM sessions WHERE owner_id='local' AND id!=%s ORDER BY recorded_at",(sid,)))


@api.post('/sessions/<sid>/source-reviews')
def review_source(sid):
    from .provenance import review_source
    return jsonify(review_source(instrument().store,sid,json_body())),201


@api.get('/training/snapshots/<snapshot_id>/export')
def snapshot_export(snapshot_id):
    row=instrument().store.one("SELECT * FROM training_snapshots WHERE id=%s AND owner_id='local'",(snapshot_id,))
    return Response(encode(row),mimetype='application/json',headers={'Content-Disposition':f'attachment; filename="snapshot-{snapshot_id}.json"'})


@api.get('/models/<mid>')
def model_record(mid):
    store=instrument().store
    row=store.one("SELECT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE m.id=%s AND r.owner_id='local'",(mid,))
    return jsonify(model=row,run=store.one('SELECT * FROM training_runs WHERE id=%s',(row['run_id'],)),evaluations=store.rows('SELECT * FROM model_evaluations WHERE model_id=%s',(mid,)),artifacts=store.rows('SELECT a.* FROM assets a JOIN model_artifacts m ON m.asset_id=a.id WHERE m.model_id=%s',(mid,)))


@api.get('/models/<mid>/artifact')
def model_artifact(mid):
    store=instrument().store
    model=store.one("SELECT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE m.id=%s AND r.owner_id='local'",(mid,))
    if model['status'] in ('retired','needs_retraining'):raise ValueError('This model is retired or invalidated; its weights cannot be served')
    training.load(store,model)
    asset=store.one('SELECT asset_id FROM model_artifacts WHERE model_id=%s',(mid,))
    from .assets import resolve
    return send_file(resolve(store,asset['asset_id'],verify=True),mimetype='application/json',as_attachment=True,download_name=f'model-{mid}.json')


@api.post('/sessions/<sid>/reanalysis')
def reanalysis(sid):
    from .reanalysis import queue_reanalysis
    return jsonify(queue_reanalysis(instrument(),sid,json_body())),202
