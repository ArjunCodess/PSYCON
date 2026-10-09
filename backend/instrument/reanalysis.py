"""A reviewed diarization correction creates new evidence, never replaces old IDs."""
import hashlib
import math
from .assets import resolve
from .store import uid,now,encode
from .jobs import enqueue
from .provenance import original_hash


def queue_reanalysis(instrument,sid,body):
    store=instrument.store
    reviewer=str(body.get('reviewer_id','')).strip();reason=str(body.get('reason','')).strip()
    maximum=body.get('max_speakers',12);turns=body.get('reviewed_turns',[])
    if not reviewer or not reason or type(maximum) is not int or not 1<=maximum<=12:
        raise ValueError('Specify a reviewer, correction reason, and maximum speaker count from 1 to 12')
    if not isinstance(turns,list) or len(turns)>20000:
        raise ValueError('Reviewed diarization must be a list of at most 20,000 intervals')
    parent=store.one("SELECT * FROM sessions WHERE id=%s AND owner_id='local'",(sid,))
    if parent['status'] in ('queued','processing'):raise ValueError('Finish or cancel current processing before a separate analysis')
    if not parent['asset_id']:raise ValueError('Register the source asset before reanalysis')
    for turn in turns:
        if not isinstance(turn,dict) or set(turn)-{'speaker','start','end'} or not isinstance(turn.get('speaker'),str) or not 1<=len(turn['speaker'])<=100:
            raise ValueError('Each reviewed interval needs an anonymous cluster label, start, and end')
        if any(type(turn.get(k)) not in (int,float) or not math.isfinite(turn[k]) for k in ('start','end')) or not parent['duration'] or not 0<=turn['start']<turn['end']<=parent['duration']:
            raise ValueError('Reviewed intervals must lie inside the measured recording')
    if len({t['speaker'] for t in turns})>maximum:raise ValueError('Reviewed cluster count exceeds the chosen maximum')
    original=resolve(store,parent['asset_id'],verify=True)
    if str(original)!=str(store.local_path(parent['original_path'])):raise ValueError('Original path differs from its registered asset')
    request_hash=hashlib.sha256(encode(dict(parent_revision=parent['input_revision'],reviewer=reviewer,reason=reason,max_speakers=maximum,reviewed_turns=turns)).encode()).hexdigest()
    with store.connect() as db:
        current=db.execute("SELECT input_revision,status FROM sessions WHERE id=%s AND owner_id='local' FOR UPDATE",(sid,)).fetchone()
        if not current or current['input_revision']!=parent['input_revision'] or current['status'] in ('queued','processing'):
            raise ValueError('Original analysis changed; review it again before creating a correction')
        existing=db.execute('SELECT session_id FROM reanalysis_requests WHERE parent_session_id=%s AND request_hash=%s',(sid,request_hash)).fetchone()
        if existing:return dict(session_id=existing['session_id'],duplicate=True,status='already queued or processed')
        key=uid()
        fields=('filename','sha256','original_path','recorded_at','context','topic','split','consent','conditions','asset_id')
        config=dict(parent['config'],max_speakers=maximum,reviewed_diarization=turns,transcription_compute_type=__import__('os').getenv('PSYCON_WHISPER_COMPUTE_TYPE','int8_float16' if parent['config']['device']=='cuda' else 'int8'))
        from .audio import model_versions
        versions=dict({**parent['versions'],**model_versions(config)},analysis_parent=sid,diarization_source='human-reviewed intervals' if turns else 'new automatic diarization',correction_reviewer=reviewer,correction_reason=reason)
        store.insert('sessions',dict(id=key,**{k:parent[k] for k in fields},created_at=now(),dataset='Reviewed reanalysis',participant_ids=[],status='queued',config=config,versions=versions),db)
        for link in db.execute('SELECT asset_id,purpose FROM session_assets WHERE session_id=%s',(sid,)).fetchall():
            store.insert('session_assets',dict(session_id=key,**dict(link)),db)
        from .service import STAGES
        for stage in STAGES:store.insert('stages',dict(session_id=key,name=stage,status='pending'),db)
        store.insert('source_reviews',dict(id=uid(),session_id=key,revision=1,kind='derived',source_session_id=sid,source_hash=original_hash(store,sid,db),reviewer_id=reviewer,reason=reason),db)
        store.insert('reanalysis_requests',dict(id=uid(),parent_session_id=sid,session_id=key,request_hash=request_hash,reviewer_id=reviewer,reason=reason),db)
        job=enqueue(store,'speech',key,1,db=db)
    return dict(session_id=key,job_id=job['id'],duplicate=False,status='queued',note='Original analysis and citations retained; review new participant mappings separately')
