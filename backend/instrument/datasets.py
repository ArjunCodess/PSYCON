"""Eligibility and immutable, connected-person/source dataset snapshots."""
from collections import defaultdict
import hashlib
import math
import random
from psycopg.types.json import Jsonb
from .store import uid, public, encode, external_row
from .forms import TRAITS
from .features import DICTIONARY

FEATURE_VERSION='conversation-2'


def latest(rows,key,time='created_at'):
    out={}
    for row in sorted(rows,key=lambda r:(int(r.get(time,0)) if time=='revision' else str(r.get(time,'')),str(r.get('id','')))):
        out[key(row)]=row
    return out


def collect(db):
    names=('sessions','session_participants','people','consent_records','speaker_mappings','annotation_submissions','annotation_answers','annotation_evidence','annotation_reviews','annotation_adjudications','annotation_validity_checks','annotation_context_flags','annotation_pattern_summaries','features','utterances','evidence','assets','session_assets','form_definitions','source_reviews')
    data={name:[external_row(r) if name=='utterances' else public(dict(r)) for r in db.execute('SELECT * FROM '+name)] for name in names}
    data['sessions']=[s for s in data['sessions'] if s['owner_id']=='local']
    session_ids={s['id'] for s in data['sessions']}
    data['session_participants']=[p for p in data['session_participants'] if p['owner_id']=='local' and p['session_id'] in session_ids]
    data['people']=[p for p in data['people'] if p['owner_id']=='local']
    participant_ids={p['id'] for p in data['session_participants']}
    data['annotation_submissions']=[s for s in data['annotation_submissions'] if s['participant_id'] in participant_ids]
    data['annotation_imports']=[public(dict(r)) for r in db.execute('SELECT id,sha256,filename,mapping FROM annotation_imports')]
    return data


def connected_components(sessions,participants):
    parent={s['id']:s['id'] for s in sessions}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def join(a,b):
        a,b=find(a),find(b)
        parent[max(a,b)]=min(a,b)
    sources={}; people={}
    for s in sorted(sessions,key=lambda r:r['id']):
        hashes=[s['sha256'],s.get('versions',{}).get('source_recording_sha256'),*s.get('source_hashes',[])]
        for sha in filter(None,hashes):
            if sha in sources:
                join(s['id'],sources[sha])
            sources[sha]=s['id']
    for p in participants:
        if p['person_id'] and p['session_id'] in parent:
            if p['person_id'] in people:
                join(p['session_id'],people[p['person_id']])
            people[p['person_id']]=p['session_id']
    return {sid:find(sid) for sid in parent}


def window_features(data,speaker,windows):
    values={}
    for kind in ('same_session_baseline','response'):
        selected=[w for w in windows if w['kind']==kind]
        if not selected:
            continue
        merged=[]
        for window in sorted(selected,key=lambda w:w['start_s']):
            if merged and window['start_s']<=merged[-1][1]: merged[-1][1]=max(merged[-1][1],window['end_s'])
            else: merged.append([window['start_s'],window['end_s']])
        utterances=[u for u in data['utterances'] if u['speaker_id']==speaker and any(u['start']>=a and u['end']<=b for a,b in merged)]
        word_count=sum(len(u['text'].split()) for u in utterances)
        exposure=sum(b-a for a,b in merged)
        speech=sum(u['end']-u['start'] for u in utterances)
        values[kind+'_word_rate']=word_count/exposure*60
        values[kind+'_speech_fraction']=min(1,speech/exposure)
        values[kind+'_utterances']=len(utterances)
    if all(k+'_word_rate' in values for k in ('same_session_baseline','response')):
        values['word_rate_change']=values['response_word_rate']-values['same_session_baseline_word_rate']
        values['speech_fraction_change']=values['response_speech_fraction']-values['same_session_baseline_speech_fraction']
    return values


def contextual_features(session,utterances,speaker_id):
    categories=('meeting','group discussion','interview','presentation')
    context=str(session['context']).strip().lower().replace('_',' ')
    features={'context_'+name.replace(' ','_'):int(context==name) for name in categories}
    features['context_other']=int(context not in categories)
    selected=[u for u in utterances if u['speaker_id']==speaker_id]
    confidence=[u['confidence'] for u in selected if u['confidence'] is not None]
    features['transcript_confidence']=sum(confidence)/len(confidence) if confidence else None
    return features


def eligible(data,family):
    form='at-4.0' if family=='at' else 'communication-1'
    sessions={r['id']:r for r in data['sessions']}; participants={r['id']:r for r in data['session_participants']}
    source_reviews=latest(data.get('source_reviews',[]),lambda r:r['session_id'],'revision')
    maps=latest(data['speaker_mappings'],lambda r:r['participant_id'],'revision')
    consent=latest(data['consent_records'],lambda r:r['participant_id'])
    reviews=latest(data['annotation_reviews'],lambda r:r['submission_id'])
    adjudications=latest(data['annotation_adjudications'],lambda r:r['answer_id'])
    submissions=latest([r for r in data['annotation_submissions'] if r['form_id']==form],lambda r:(r['participant_id'],r['source_type'],r['reviewer_id']),'revision')
    answers=defaultdict(list); windows=defaultdict(list); validity=defaultdict(dict)
    for a in data['annotation_answers']: answers[a['submission_id']].append(a)
    for e in data['annotation_evidence']: windows[e['answer_id']].append(e)
    for v in data['annotation_validity_checks']: validity[v['submission_id']][v['name']]=v['category']
    result=[]
    sources={r['id']:r for r in data.get('annotation_imports',[])}
    definitions={r['id']:r for r in data.get('form_definitions',[])}
    paired=defaultdict(list)
    for sub in submissions.values():
        if sub['source_type']=='self_report': continue
        for a in answers[sub['id']]:
            paired[(sub['participant_id'],a['item_key'])].append(a['score'])
    for sub in sorted(submissions.values(),key=lambda r:r['id']):
        p=participants[sub['participant_id']]; s=sessions[p['session_id']]; mapping=maps.get(p['id']); c=consent.get(p['id'])
        common=[]
        source_review=source_reviews.get(s['id'])
        if not source_review or source_review['kind']=='uncertain': common.append('Recording ancestry needs review for excerpts, re-encodings, and duplicate sources')
        if p['withdrawn_at']: common.append('Participant withdrawn')
        if p['person_id'] and next((r['withdrawn_at'] for r in data['people'] if r['id']==p['person_id']),None): common.append('Person withdrawn')
        if s['consent'] not in ('documented','public licensed','self recording') or not c or c['status']!='documented' or not c['training_allowed']: common.append('Training consent unavailable')
        if not mapping or mapping['status']!='confirmed': common.append('Needs reviewed speaker mapping')
        if s['status']!='complete': common.append('Incomplete processing')
        if s['split']=='reference': common.append('Reference corpus is excluded from fitting and evaluation')
        if sub['source_type']=='self_report': common.append('Self-report is separate from observer training targets')
        if not sub['reviewer_id']: common.append('Original reviewer provenance missing')
        if not reviews.get(sub['id']) or reviews[sub['id']]['decision']!='approved': common.append('Needs independent review')
        v=validity[sub['id']]
        if v.get('speaker_identity')!='Yes' or v.get('recording_support')!='Yes': common.append('Speaker identity and recording validity must be affirmed')
        for answer in answers[sub['id']]:
            reasons=list(common); key=answer['item_key']; ew=windows[answer['id']]
            if answer['state']!='scored': reasons.append('N/O' if answer['state']=='not_observed' else 'Missing answer')
            if answer['fair_opportunity'] is not True: reasons.append('Fair opportunity unconfirmed')
            if answer['confidence'] is None: reasons.append('Observer confidence missing')
            if answer['score'] and not ew: reasons.append('Positive rating lacks timestamped evidence')
            if mapping and any(w.get('evidence_id') and not any(e['id']==w['evidence_id'] and e['speaker_id']==mapping['speaker_id'] for e in data['evidence']) for w in ew): reasons.append('Evidence belongs to another speaker')
            if answer['score'] and any(not w['context'].strip() for w in ew if w['kind']=='support'): reasons.append('Positive evidence needs the surrounding observable context')
            if family=='at' and (key=='K' or key>='M'):
                kinds={w['kind'] for w in ew}
                if not {'event','response'}<=kinds: reasons.append('Event and response windows required')
                if key>='Q' and 'same_session_baseline' not in kinds: reasons.append('Earlier same-session baseline required')
                if key=='S': reasons.append('Vocal-change acoustic features unavailable in current extractor')
                if answer['component'] not in ('audio','participation'): reasons.append('Visual behavior is unsupported by audio-first training')
                baseline=[w for w in ew if w['kind']=='same_session_baseline']; events=[w for w in ew if w['kind']=='event']
                if baseline and events and max(w['end_s'] for w in baseline)>min(w['start_s'] for w in events): reasons.append('Same-session baseline must precede the event')
                responses=[w for w in ew if w['kind']=='response']
                if responses and events and min(w['start_s'] for w in responses)<min(w['start_s'] for w in events):reasons.append('Response must not precede the event')
                if any(not w['context'].strip() for w in ew):reasons.append('Event-linked windows need observable context')
            supports=sorted([w for w in ew if w['kind']=='support'],key=lambda w:w['start_s'])
            distinct=len(supports)>=2 and any(a['end_s']<=b['start_s'] for a,b in zip(supports,supports[1:]))
            if family=='communication' and answer['score'] and not distinct: reasons.append('Independent communication rating requires at least two non-overlapping contextual moments')
            adj=adjudications.get(answer['id'])
            if len({x for x in paired[(p['id'],key)] if x is not None})>1 and not adj: reasons.append('Conflicting reviewer ratings need adjudication')
            result.append(dict(participant_id=p['id'],participant_code=p['code'],session_id=s['id'],target=key,answer_id=answer['id'],submission_id=sub['id'],label_revision=sub['revision'],reviewer_id=sub['reviewer_id'],source_type=sub['source_type'],form_id=sub['form_id'],form_hash=definitions.get(sub['form_id'],{}).get('source_hash'),import_id=sub['import_id'],annotation_source_hash=sources.get(sub['import_id'],{}).get('sha256'),mapping_revision=mapping['revision'] if mapping else None,consent_id=c['id'] if c else None,review_id=reviews[sub['id']]['id'] if reviews.get(sub['id']) else None,mapping_id=mapping['id'] if mapping else None,speaker_id=mapping['speaker_id'] if mapping else None,score=adj['score'] if adj else answer['score'],observer_confidence=answer['confidence'],fair_opportunity=answer['fair_opportunity'],adjudication_id=adj['id'] if adj else None,eligible=not reasons,reasons=reasons,windows=ew))
            result[-1]['annotation_context']=dict(metadata=sub['metadata'],validity=[r for r in data['annotation_validity_checks'] if r['submission_id']==sub['id']],flags=[r for r in data.get('annotation_context_flags',[]) if r['submission_id']==sub['id']],patterns=[r for r in data.get('annotation_pattern_summaries',[]) if r['submission_id']==sub['id']])
    return result


def readiness(store,family):
    if family not in ('at','communication'): raise ValueError('Choose at or communication')
    with store.connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        data=collect(db)
    rows=eligible(data,family)
    targets=defaultdict(lambda:dict(eligible=0,excluded=0))
    for row in rows: targets[row['target']]['eligible' if row['eligible'] else 'excluded']+=1
    return dict(family=family,rows=rows,targets=dict(targets),status='Eligible' if any(r['eligible'] for r in rows) else 'Insufficient data')


def freeze(store,family,seed=42,study='unseen_participant'):
    if type(seed) is not int or study not in ('unseen_participant','longitudinal'): raise ValueError('Invalid snapshot protocol')
    task=store.one('SELECT * FROM training_tasks WHERE id=%s',(family,))
    with store.connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        data=collect(db); rows=eligible(data,family)
        rubric=next(f for f in data['form_definitions'] if f['id']==task['form_id'])
        asset_hashes={r['id']:r['sha256'] for r in data['assets']}
        source_reviews=latest(data['source_reviews'],lambda r:r['session_id'],'revision')
        for session in data['sessions']:
            session['source_hashes']=sorted({asset_hashes[r['asset_id']] for r in data['session_assets'] if r['session_id']==session['id']})
            review=source_reviews.get(session['id'])
            if review and review['kind']!='uncertain':session['source_hashes']=sorted(set(session['source_hashes']+[review['source_hash']]))
            linked=[r for r in data['session_assets'] if r['session_id']==session['id'] and r['purpose']=='original group discussion video']
            if linked:
                session['versions']=dict(session['versions'],source_recording_sha256=asset_hashes[linked[0]['asset_id']])
        components=connected_components(data['sessions'],data['session_participants'] if study=='unseen_participant' else [])
        sessions={r['id']:r for r in data['sessions']}
        roles=defaultdict(set)
        for s in data['sessions']: roles[components[s['id']]].add(s['split'])
        examples={}; exclusions=[r for r in rows if not r['eligible']]
        for row in rows:
            if not row['eligible']: continue
            s=sessions[row['session_id']]; comp=components[s['id']]
            if len(roles[comp])>1:
                exclusions.append(dict(**{k:v for k,v in row.items() if k not in ('reasons','eligible')},eligible=False,reasons=['Connected person/source component spans incompatible dataset roles']))
                continue
            example=examples.setdefault(row['participant_id'],dict(participant_id=row['participant_id'],session_id=s['id'],speaker_id=row['speaker_id'],mapping_id=row['mapping_id'],submission_id=row['submission_id'],source_hash=s['sha256'],role=s['split'],component=comp,features={},labels={},metadata=dict(recorded_at=s['recorded_at'],context=s['context'],conditions=s['conditions'],versions=s['versions'],source_review=source_reviews.get(s['id']),source_hashes=s['source_hashes'])))
            if row['target'] in example['labels']:
                continue  # Reviewer repetitions are not independent samples.
            example['labels'][row['target']]=row
            for f in data['features']:
                if f['speaker_id']==row['speaker_id'] and f['name'] in DICTIONARY:
                    example['features'][f['name']]=dict(value=f['value'],unit=f['unit'],status=f['status'],denominator=f['denominator'])
            for name,value in contextual_features(s,data['utterances'],row['speaker_id']).items():
                example['features'][name]=dict(value=value,unit='context category' if name.startswith('context_') else 'uncalibrated transcript confidence',status='recorded context' if name.startswith('context_') else 'estimated',denominator=None)
            if family=='at' and (row['target']=='K' or row['target']>='M'):
                for name,value in window_features(data,row['speaker_id'],row['windows']).items():
                    example['features'][row['target']+'__'+name]=dict(value=value,unit='window measurement',status='observed',denominator=None)
        development=sorted({e['component'] for e in examples.values() if e['role']=='development'})
        random.Random(seed).shuffle(development)
        split_map={component:'train' for component in development}
        if study=='unseen_participant' and len(development)>=5 and not any(e['role']=='validation' for e in examples.values()): split_map[development[-1]]='validation'
        if study=='unseen_participant' and len(development)>=5 and not any(e['role']=='evaluation' for e in examples.values()): split_map[development[-2]]='test'
        for e in examples.values():
            e['split']={'validation':'validation','evaluation':'test'}.get(e['role'],split_map.get(e['component'],'train'))
        if study=='longitudinal':
            # Explicit roles and chronology are required; never randomize a within-person time study.
            if any(e['role']=='development' and e['split']!='train' for e in examples.values()):
                raise ValueError('Longitudinal snapshots require explicit training/validation/evaluation roles')
            times={split:[e['metadata']['recorded_at'] for e in examples.values() if e['split']==split] for split in ('train','validation','test')}
            if not all(times.values()) or max(times['train'])>=min(times['validation']) or max(times['validation'])>=min(times['test']):
                raise ValueError('Longitudinal role cutoffs must be strictly forward in time')
        manifest=dict(seed=seed,feature_version=FEATURE_VERSION,task_definition=task['definition'],study=study,source_policy='source-review-1: unknown ancestry excluded; reviewed excerpts and derivatives share the original source group',grouping='Confirmed person, registered hashes, and reviewed original-source connected components; no reference overlap',exclusions=exclusions,counts=dict(examples=len(examples),sessions=len({e['session_id'] for e in examples.values()}),groups=len({e['component'] for e in examples.values()})),examples=list(examples.values()))
        manifest['rubric']={k:rubric[k] for k in ('id','version','source_hash','definition')}
        digest=hashlib.sha256(encode(manifest).encode()).hexdigest(); snapshot=uid()
        store.insert('training_snapshots',dict(id=snapshot,owner_id='local',task_id=family,sha256=digest,seed=seed,protocol=dict(study=study,roles='development/validation/evaluation/reference',grouping='person/source components',cutoff='strictly earlier history'),manifest=manifest),db)
        for e in examples.values():
            eid=uid(); store.insert('training_examples',dict(id=eid,snapshot_id=snapshot,feature_version=FEATURE_VERSION,**{k:e[k] for k in ('participant_id','session_id','speaker_id','mapping_id','submission_id','source_hash','role','metadata')}),db)
            store.insert('split_assignments',dict(example_id=eid,component=e['component'],split=e['split']),db)
            for name,f in e['features'].items(): store.insert('training_example_features',dict(example_id=eid,name=name,**f),db)
            for target,label in e['labels'].items(): store.insert('training_example_labels',dict(example_id=eid,target=target,**{k:label[k] for k in ('answer_id','score','adjudication_id','label_revision','form_id','form_hash','import_id','annotation_source_hash','reviewer_id','source_type','observer_confidence','fair_opportunity','mapping_revision','consent_id','review_id')}),db)
    return store.one('SELECT * FROM training_snapshots WHERE id=%s',(snapshot,))
