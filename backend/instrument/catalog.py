"""Idempotent registration of original group videos and retained model-generated text."""
from pathlib import Path
from uuid import NAMESPACE_URL,uuid5
from .assets import register
from .store import decode


def register_group_videos(store,directory=None):
    root=Path(directory or Path(__file__).resolve().parents[2]/'group_discussions').resolve(strict=True)
    sessions=store.rows('SELECT id,sha256,versions FROM sessions')
    registered=0;linked=0
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ('.mov','.mp4','.m4v','.avi','.mkv'):continue
        with store.connect() as db:
            asset=register(store,path,'media',root=root,db=db)
            registered+=1
            for session in sessions:
                if session['sha256']==asset['sha256'] or session['versions'].get('original_video')==path.name:
                    linked+=db.execute('INSERT INTO session_assets VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(session['id'],asset['id'],'original group discussion video')).rowcount
    return dict(original_videos=registered,new_analysis_links=linked,originals_renamed=False)


def normalize_retained_claims(store):
    inserted=0;unsupported=0
    with store.connect() as db:
        for run in db.execute("SELECT * FROM llm_runs WHERE status IN ('complete','stale') AND output IS NOT NULL").fetchall():
            output=decode(run['output'])
            for index,claim in enumerate(output.get('claims',[]) if isinstance(output,dict) else []):
                if db.execute('SELECT id FROM llm_claims WHERE run_id=%s AND claim_index=%s',(run['id'],index)).fetchone():continue
                fields=('speaker_id','observation','inference','confidence','limitation','suggestion')
                references=claim.get('evidence_ids',[]) if isinstance(claim,dict) else []
                if not isinstance(claim,dict) or not isinstance(references,list) or any(not isinstance(ref,str) for ref in references) or any(not isinstance(claim.get(k),str) for k in fields) or claim['speaker_id']!=run['speaker_id']:
                    unsupported+=1;continue
                resolved=[];own=False
                for ref in references:
                    evidence=db.execute('SELECT id,speaker_id FROM evidence WHERE id=%s AND session_id=%s',(ref,run['session_id'])).fetchone()
                    utterance=None if evidence else db.execute('SELECT id,speaker_id FROM utterances WHERE id=%s AND session_id=%s',(ref,run['session_id'])).fetchone()
                    if not evidence and not utterance:break
                    own=own or (evidence or utterance)['speaker_id']==run['speaker_id']
                    resolved.append(dict(evidence_id=ref if evidence else None,utterance_id=None if evidence else ref))
                if len(resolved)!=len(references) or not references or not own:
                    unsupported+=1;continue
                key=str(uuid5(NAMESPACE_URL,'psycon:retained-claim:'+run['id']+':'+str(index)))
                store.insert('llm_claims',dict(id=key,run_id=run['id'],claim_index=index,**{k:claim[k] for k in fields}),db)
                for ref in resolved:store.insert('llm_claim_evidence',dict(claim_id=key,**ref),db)
                inserted+=1
    return dict(normalized_claims=inserted,unsupported_retained_as_raw=unsupported)


def queue_group_videos(instrument,directory=None):
    """Queue new analyses once, preserving every existing citation identity."""
    store=instrument.store
    registered=register_group_videos(store,directory)
    from .reanalysis import queue_reanalysis
    results=[]
    roots=store.rows("SELECT * FROM sessions WHERE dataset='Group discussion videos - full audio pipeline' ORDER BY created_at")
    for session in roots:
        if session['status'] in ('queued','processing'):
            results.append(dict(session_id=session['id'],status=session['status']));continue
        result=queue_reanalysis(instrument,session['id'],dict(reviewer_id='local operator',reason='Original group video Docker processing batch v1',max_speakers=session['config'].get('max_speakers',12)))
        results.append(result)
    if not roots:
        raise ValueError('No retained full-video session metadata. Import verified recordings before queuing; recording dates and consent must not be guessed.')
    return dict(**registered,analyses=results)
