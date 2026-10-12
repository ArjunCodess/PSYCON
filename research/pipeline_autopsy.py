"""Read-only stage audit plus bounded nested feature-family ablations.

Private outputs only. Run --output with a new directory. No model activation.
"""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,csv,hashlib,json,os,platform,subprocess,time,wave
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression,Ridge
from research.emergency_audit import align,key,metrics
from research.maximum_defensible import audit_groups,filename,write_csv,dump,paired_bootstrap
from research.compact_source_models import CORE,CONVERSATION

FAMILIES=dict(participation=['speaking_time','speaking_share','turn_count','word_count','words_per_minute'],
    turn_structure=['mean_turn_duration','median_turn_duration','longest_turn','shortest_turn'],
    timing_overlap=['response_latency','overlap_time','interruption_candidate_rate'],
    linguistic=['question_rate','question_ratio','hedging_ratio','assertion_ratio','acknowledgement_ratio','proposal_rate','unhedged_proposal_ratio','disagreement_rate','reasoning_ratio','experimentation_ratio','concession_ratio','open_question_ratio','backchannel_candidate_rate'],
    context_quality=['context_meeting','context_group_discussion','context_interview','context_presentation','context_other','transcript_confidence'])
ALL=sum(FAMILIES.values(),[])
SETS={'full':ALL,'core':list(CORE),'compact':list(CONVERSATION),**FAMILIES,
      **{'without_'+f:[n for n in ALL if n not in names] for f,names in FAMILIES.items()},
      'clean':ALL,'log_transform':ALL,'winsorized':ALL}
CONFIGS=[dict(name=n+'|'+est,feature_set=n,estimator=est) for n in SETS for est in ('logistic_0.1','logistic_1','ridge_10')]
CONFIGS += [dict(name='full|logistic_1_balanced',feature_set='full',estimator='logistic_1_balanced'),
            dict(name='median',feature_set='none',estimator='median'),dict(name='mode',feature_set='none',estimator='mode')]
POLICY=dict(version='pipeline-autopsy-1',seed=42,families=FAMILIES,feature_sets=SETS,configurations=CONFIGS,
    protocol='Same five frozen connected groups; outer leave-one-group-out, inner leave-one-group-out; training-only feature selection and preprocessing',
    stage='Retrospective exploratory development after inspecting prior outer results; no independent external test',
    selection='Per-target inner equal-group MAE, constrained to no observed-class recall loss >.02 versus median on classes with support >=3; require .025 MAE gain over median; declaration-order tie break',
    transformations='Clean removes train-constant, >50% train-missing, or |training Pearson|>.9 redundant features in declared order. Log applies log1p to nonnegative non-context/non-proportion values. Winsorization clips to training 5/95 percentiles. No held-out feature selection.',
    promotion='Single nested procedure only: agreement gain >=.025 versus compact, MAE <=compact and mode, each observed-class recall >=compact-.02, all five group MAE <=compact, positive descriptive paired agreement lower bound vs mode. Otherwise retain compact research reference.',
    inference='Completed recording only. No observer notes/windows, target labels, future sessions or identities as predictors.',
    bounds='No adaptive reruns, searches or threshold changes based on outer diagnostics',activate=False)


def fit_model(train,target,c):
    y=np.asarray([e['labels'][target]['score'] for e in train]);counts=Counter(y.tolist())
    constant=min(counts,key=lambda k:(-counts[k],k)) if c['estimator']=='mode' else int(np.median(y))
    names=[n for n in SETS.get(c['feature_set'],[]) if any(e['features'].get(n,{}).get('value') is not None for e in train)]
    removed={n:'unavailable in training' for n in SETS.get(c['feature_set'],[]) if n not in names}
    if c['feature_set']=='clean':
        keep=[]
        for n in names:
            v=np.asarray([e['features'].get(n,{}).get('value',np.nan) for e in train],dtype=float)
            if np.isnan(v).mean()>.5:removed[n]='>50% missing in training';continue
            if len(set(v[np.isfinite(v)]))<2:removed[n]='constant in training';continue
            redundant=False
            for other in keep:
                w=np.asarray([e['features'].get(other,{}).get('value',np.nan) for e in train],dtype=float)
                common=np.isfinite(v)&np.isfinite(w)
                if common.sum()>=5 and np.std(w[common])>0 and abs(np.corrcoef(v[common],w[common])[0,1])>.9:
                    removed[n]='training redundancy with '+other;redundant=True;break
            if not redundant:keep.append(n)
        names=keep
    m=dict(names=names,removed=removed,constant=constant,fallback=c['estimator'] not in ('median','mode'),config=c)
    if c['estimator'] in ('median','mode') or len(train)<12 or len({e['component'] for e in train})<3 or len(counts)<2 or not names:return m
    x=raw_matrix(train,names);bounds=None;logs=[]
    if c['feature_set']=='log_transform':
        logs=[i for i,n in enumerate(names) if not n.startswith('context_') and not n.endswith(('_ratio','_share')) and np.nanmin(x[:,i])>=0]
        x[:,logs]=np.log1p(x[:,logs])
    if c['feature_set']=='winsorized':
        bounds=np.nanquantile(x,[.05,.95],axis=0);x=np.clip(x,bounds[0],bounds[1])
    est=Ridge(alpha=10) if c['estimator']=='ridge_10' else LogisticRegression(C=.1 if c['estimator']=='logistic_0.1' else 1,
        class_weight='balanced' if c['estimator'].endswith('balanced') else None,max_iter=2000,random_state=42)
    pipe=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('scaler',StandardScaler()),('model',est)])
    pipe.fit(x,y)
    if getattr(est,'n_iter_',None) is not None and np.any(est.n_iter_>=2000):raise RuntimeError('Fit did not converge')
    m.update(pipe=pipe,logs=logs,bounds=bounds,fallback=False)
    return m


def raw_matrix(examples,names):
    return np.asarray([[e['features'].get(n,{}).get('value') if e['features'].get(n,{}).get('value') is not None else np.nan for n in names] for e in examples],dtype=float)


def predictions(m,examples):
    if 'pipe' not in m:return np.full(len(examples),m['constant'],dtype=int)
    x=raw_matrix(examples,m['names']);x[:,m['logs']]=np.log1p(np.maximum(x[:,m['logs']],0))
    if m['bounds'] is not None:x=np.clip(x,m['bounds'][0],m['bounds'][1])
    p=m['pipe'].predict(x)
    return np.clip(np.floor(p+.5),0,4).astype(int) if m['config']['estimator']=='ridge_10' else p.astype(int)


def choose(d):
    ref=d['median'];allowed=[]
    for c in CONFIGS:
        m=d[c['name']]
        if all(z['support']<3 or m['per_class'][z['score']]['recall']>=z['recall']-.02 for z in ref['per_class'] if z['recall'] is not None):allowed.append(c['name'])
    best=min(allowed,key=lambda n:(d[n]['equal_group_mae'],next(i for i,c in enumerate(CONFIGS) if c['name']==n)))
    return best if ref['equal_group_mae']-d[best]['equal_group_mae']>=.025 else 'median'


def expanded(rows):
    m=metrics(rows)
    m.update(overpredictions=sum(r['prediction'] is not None and r['prediction']>r['rating'] for r in rows),
        underpredictions=sum(r['prediction'] is not None and r['prediction']<r['rating'] for r in rows),
        signed_error=float(np.mean([r['prediction']-r['rating'] for r in rows if r['prediction'] is not None])) if m['matched_predictions'] else None,
        quadratic_kappa_meaning='undefined if expected weighted disagreement is zero; otherwise descriptive, especially in small/mixed-target slices')
    return m


def normalized_path(media):
    """Current derived artifact, then the historical direct layout."""
    return next((p for p in (Path(media)/'derived'/'normalized.wav', Path(media)/'normalized.wav') if p.exists()), Path(media)/'derived'/'normalized.wav')


def quality_audit(out,examples):
    import av
    from backend.instrument.audio import preprocess
    rows=[]
    for sid in sorted({e['session_id'] for e in examples}):
        e=next(e for e in examples if e['session_id']==sid);name=filename(e);raw=Path('group_discussions')/name
        normalized=normalized_path(Path('instance/instrument/media')/sid);r=dict(session_id=sid,recording=name,group=e['component'])
        if raw.exists():
            with av.open(str(raw)) as container:
                stream=next(s for s in container.streams if s.type=='audio')
                r.update(raw_rate=stream.codec_context.sample_rate,raw_channels=stream.codec_context.layout.nb_channels,
                    raw_audio_duration=float(stream.duration*stream.time_base) if stream.duration is not None else None)
        else:r['raw_status']='unavailable'
        if normalized.exists():
            with wave.open(str(normalized),'rb') as w:
                rate=w.getframerate();channels=w.getnchannels();data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
                r.update(normalized_duration=w.getnframes()/rate,normalized_rate=rate,normalized_channels=channels)
            usable=data[:len(data)//320*320].reshape(-1,320)
            rms=np.sqrt((usable**2).mean(axis=1));r.update(clipping_fraction=float((abs(data)>=.999).mean()),silence_fraction=float((rms<.003162).mean()))
            r['duration_difference']=r['normalized_duration']-r['raw_audio_duration'] if r.get('raw_audio_duration') is not None else None
            r['quality']='clipping_gt_5pct' if r['clipping_fraction']>.05 else 'below_clipping_gate'
        else:r['normalized_status']='unavailable'
        rows.append(r);print('Audio provenance checked:',name,flush=True)
    dump(out,'audio_quality.json',rows)
    # Canonical database is optional and read-only. Do not substitute the old SQLite mirror.
    from ml.src.environment import load_project_environment
    from backend.instrument.store import public,external_row
    load_project_environment(override=False)
    import psycopg
    from psycopg.rows import dict_row
    status={}
    try:
        with psycopg.connect(os.getenv('PSYCON_DATABASE_URL'),connect_timeout=5,row_factory=dict_row) as db:
            db.execute('SET TRANSACTION READ ONLY');db.execute("SET statement_timeout='10000ms'")
            ids=sorted({e['session_id'] for e in examples})
            stages=db.execute('SELECT * FROM stages WHERE session_id=ANY(%s::uuid[])',(ids,)).fetchall()
            status=dict(status='read_only_snapshot',stages=public(stages))
            for sid in ids:
                turns=[external_row(r) for r in db.execute('SELECT * FROM turns WHERE session_id=%s ORDER BY start_s,end_s',(sid,))]
                utterances=[external_row(r) for r in db.execute('SELECT * FROM utterances WHERE session_id=%s ORDER BY start_s,end_s',(sid,))]
                speakers=[public(r) for r in db.execute('SELECT * FROM speakers WHERE session_id=%s',(sid,))]
                dump(out,'raw-stage-'+sid+'.json',dict(turns=turns,utterances=utterances,speakers=speakers))
    except Exception as exc:
        status=dict(status='unavailable',exception_type=type(exc).__name__,reason='Canonical read-only stage export unavailable; no mirror substituted and no live-state claim')
    dump(out,'canonical_stage_audit.json',status)
    return {r['session_id']:r for r in rows}


def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False);dump(out,'policy-before-results.json',POLICY)
    source=Path('.runtime/model-hardening/snapshot.json');initial=hashlib.sha256(source.read_bytes()).hexdigest();manifest=json.loads(source.read_text());examples=manifest['examples']
    targets=sorted(json.loads(Path('.runtime/model-hardening/models.json').read_text()))
    group_audit=audit_groups(examples,json.loads(Path('docs/research/PARTICIPANT_OVERLAP.json').read_text()),json.loads(Path('.runtime/participant-overlap/applied.json').read_text()))
    dump(out,'group_integrity.json',group_audit)
    preserved_paths=[source,Path('.runtime/model-hardening/models.json'),Path('.runtime/model-hardening/predictions.json'),
        Path('.runtime/results-analysis/grouped-cv-predictions.json'),Path('.runtime/emergency-audit-2026-10-12/evaluation_results.json'),
        Path('.runtime/emergency-audit-2026-10-12/paired_predictions.json')]
    preserved={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved_paths}
    dump(out,'reference_hashes.json',preserved)
    alias={g:'Group '+str(i+1) for i,g in enumerate(sorted({e['component'] for e in examples}))}
    refs=[dict(target=t,speaker_id=e['speaker_id'],group=alias[e['component']],rating=e['labels'][t]['score']) for e in examples for t in targets if t in e['labels']]
    original=align(refs,json.loads(Path('.runtime/results-analysis/grouped-cv-predictions.json').read_text()));compact=align(refs,json.loads(Path('.runtime/model-hardening/predictions.json').read_text()))
    common={key(r) for r in original if r['prediction'] is not None}
    common_rows=lambda r:[x for x in r if key(x) in common]
    dump(out,'baseline_before.json',dict(original=expanded(original),compact_common=expanded(common_rows(compact)),compact_all=expanded(compact),source_sha256=initial))
    quality=quality_audit(out,examples)
    cache={};log=[];result=defaultdict(list);folds=[]
    def model(train,t,c):
        k=(t,c['name'],tuple(sorted(e['speaker_id'] for e in train)))
        if k not in cache:
            start=time.perf_counter();entry=dict(target=t,configuration=c,train_n=len(train),train_ids=list(k[2]),train_groups=sorted({alias[e['component']] for e in train}),seed=42)
            try:
                cache[k]=fit_model(train,t,c);entry.update(status='success',retained=cache[k]['names'],removed=cache[k]['removed'],fallback=cache[k]['fallback'])
            except Exception as exc:entry.update(status='failed',error=repr(exc));raise
            finally:
                entry['seconds']=time.perf_counter()-start;log.append(entry)
                if entry['status']=='failed':write_csv(out,'experiment_log.csv',log)
        return cache[k]
    def evaluate(train,test,t,c):
        m=model(train,t,c);p=predictions(m,test)
        return [dict(target=t,speaker_id=e['speaker_id'],group=alias[e['component']],rating=e['labels'][t]['score'],prediction=int(v),fallback=m['fallback']) for e,v in zip(test,p)]
    for t in targets:
        eligible=[e for e in examples if t in e['labels']]
        for g in alias:
            train=[e for e in eligible if e['component']!=g];test=[e for e in eligible if e['component']==g]
            if not test:continue
            inner={}
            for c in CONFIGS:
                val=[]
                for ig in sorted({e['component'] for e in train}):
                    tr=[e for e in train if e['component']!=ig];te=[e for e in train if e['component']==ig]
                    val.extend(evaluate(tr,te,t,c))
                inner[c['name']]=expanded(val)
                outer=evaluate(train,test,t,c);result[c['name']].extend(outer)
                log.append(dict(status='success',stage='outer_diagnostic',target=t,outer=alias[g],configuration=c,train_n=len(train),test_n=len(test),metrics=expanded(outer)))
            selected=choose(inner);c=next(c for c in CONFIGS if c['name']==selected);result['nested'].extend(dict(r,selected=selected) for r in evaluate(train,test,t,c))
            folds.append(dict(target=t,outer=alias[g],selected=selected,inner=inner,train_ids=[e['speaker_id'] for e in train],test_ids=[e['speaker_id'] for e in test]))
        write_csv(out,'experiment_log.csv',log);dump(out,'folds.json',folds)
        print('Ablations completed:',t,flush=True)
    result.update(original=original,compact=compact)
    comparisons=[];slices={};matrices={};all_predictions=[];meta={e['speaker_id']:e for e in examples}
    for name,rows in result.items():
        extras={key(r):{k:r[k] for k in ('selected','fallback') if k in r} for r in rows}
        rows=align(refs,rows)
        all_predictions.extend(dict(r,**extras.get(key(r),{}),procedure=name,answer_id=meta[r['speaker_id']]['labels'][r['target']]['answer_id'],session_id=meta[r['speaker_id']]['session_id']) for r in rows)
        for cohort,rr in [('common_402',common_rows(rows)),('all_423',rows)]:
            m=expanded(rr);comparisons.append(dict(procedure=name,cohort=cohort,**m));matrices[name+'|'+cohort]=m['confusion']
        if name not in ('original','compact','nested','median','mode','full|logistic_1_balanced'):continue
        slices[name]={}
        for cohort,rr in [('common_402',common_rows(rows)),('all_423',rows)]:
            for dimension in ('target','score','recording','participant_session','group','direction','speech_quantity','duration','audio_clipping','silence','transcript_confidence'):
                groups=defaultdict(list)
                for r in rr:
                    e=meta[r['speaker_id']];q=quality[e['session_id']];f=e['features'];speech=f.get('speaking_time',{}).get('value');conf=f.get('transcript_confidence',{}).get('value');duration=q.get('normalized_duration');silence=q.get('silence_fraction')
                    value=r['target'] if dimension=='target' else str(r['rating']) if dimension=='score' else filename(e) if dimension=='recording' else r['group'] if dimension=='group' else ('abstention' if r['prediction'] is None else 'over' if r['prediction']>r['rating'] else 'under' if r['prediction']<r['rating'] else 'correct') if dimension=='direction' else ('unknown' if speech is None else '<60s' if speech<60 else '60-180s' if speech<180 else '>=180s') if dimension=='speech_quantity' else ('unknown' if duration is None else '<300s' if duration<300 else '300-900s' if duration<900 else '>=900s') if dimension=='duration' else q.get('quality','unknown') if dimension=='audio_clipping' else ('unknown' if silence is None else '<20pct' if silence<.2 else '20-50pct' if silence<.5 else '>=50pct') if dimension=='silence' else ('unknown' if conf is None else '<.75' if conf<.75 else '.75-.9' if conf<.9 else '>=.9')
                    if dimension=='participant_session':value=r['speaker_id']
                    groups[value].append(r)
                if dimension=='score':
                    for score in range(5):groups.setdefault(str(score),[])
                slices[name][cohort+'|'+dimension]={v:expanded(rrr) for v,rrr in groups.items()}
    write_csv(out,'ablation_comparison.csv',comparisons);write_csv(out,'predictions.csv',all_predictions);dump(out,'slices.json',slices);dump(out,'confusion_matrices.json',matrices)
    nested=expanded(common_rows(result['nested']));ref=expanded(common_rows(compact));mode=expanded(common_rows(result['mode']))
    uncertainty=paired_bootstrap(common_rows(result['nested']),common_rows(result['mode']))
    group_regressions=[g for g in alias.values() if expanded([r for r in common_rows(result['nested']) if r['group']==g])['mae']>expanded([r for r in common_rows(compact) if r['group']==g])['mae']]
    gates=dict(agreement=nested['exact_agreement']>=ref['exact_agreement']+.025,mae=nested['mae']<=min(ref['mae'],mode['mae']),
        class_recall=all(nested['per_class'][k]['recall']>=ref['per_class'][k]['recall']-.02 for k in range(1,5)),groups=not group_regressions,paired=uncertainty['agreement_interval'][0]>0)
    final={'promote':all(gates.values()),'gates':gates,'nested_common':nested,'nested_all':expanded(result['nested']),
        'retained':'compact research reference' if not all(gates.values()) else 'nested exploratory candidate for review',
        'retained_features':list(CONVERSATION),'removed_from_working_model':[], 'uncertainty_vs_mode':uncertainty,'group_mae_regressions':group_regressions}
    dump(out,'decision.json',final)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==initial
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in preserved.items())
    dump(out,'receipt.json',dict(source_sha256=initial,source_preserved=True,seed=42,python=platform.python_version(),sklearn=__import__('sklearn').__version__,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),configurations=len(CONFIGS),fit_log_records=len(log),
        command=f'.runtime/venv/Scripts/python.exe -m research.pipeline_autopsy --output {output}',no_live_writes=True))
    print('Nested result',nested['correct'],nested['matched_predictions'],nested['mae'],'promotion',final['promote'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(p.parse_args().output)
