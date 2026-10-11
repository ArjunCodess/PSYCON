"""Real regularized ordinal approximations, portable artifacts, and deliberate serving."""
from collections import Counter
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
import numpy as np
from psycopg.types.json import Jsonb
from .assets import register, resolve
from .datasets import FEATURE_VERSION
from .jobs import enqueue, claim, lease, finish
from .store import uid, encode, StaleJob


def runtime_versions():
    versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=importlib.metadata.version('scikit-learn'))
    revision=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    versions['code_revision']=revision
    versions['code_hash']=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
    return versions


def snapshot_summary(snapshot):
    """Describe frozen target splits without fitting or consulting live labels."""
    examples=snapshot['manifest']['examples']; targets={}
    for target in sorted({t for e in examples for t in e['labels']}):
        rows=[e for e in examples if target in e['labels']]
        splits={}
        for split in ('train','validation','test'):
            selected=[e for e in rows if e['split']==split]
            splits[split]=dict(records=len(selected),groups=len({e['component'] for e in selected}),classes=sorted({e['labels'][target]['score'] for e in selected}))
        train=splits['train']; reasons=[]
        if train['records']<12 or train['groups']<3 or len(train['classes'])<2:
            reasons.append('Requires 12 training examples, three independent groups, and two observed classes')
        if not any(f['value'] is not None and ('__' not in n or n.startswith(target+'__')) for e in rows if e['split']=='train' for n,f in e['features'].items()):
            reasons.append('No supported measured predictors')
        targets[target]=dict(splits=splits,can_fit=not reasons,reasons=reasons)
    can_fit=any(t['can_fit'] for t in targets.values())
    return dict(targets=targets,can_fit=can_fit,status='Ready to fit' if can_fit else 'Insufficient training data')


def queue(store,snapshot_id,configuration=None):
    snapshot=store.one("SELECT * FROM training_snapshots WHERE id=%s AND owner_id='local'",(snapshot_id,))
    if store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot_id,)):
        raise ValueError('Snapshot was invalidated by corrections, withdrawal, or mappings')
    config=configuration or {}
    if set(config)-{'regularization','allow_exploratory'}:
        raise ValueError('Unknown training configuration')
    values=config.get('regularization',[.1,1.,10.])
    if not isinstance(values,list) or not values or any(type(x) not in (int,float) or not 0<x<=100 for x in values):
        raise ValueError('Regularization values must be finite numbers in (0,100]')
    key=uid()
    versions=runtime_versions()
    with store.connect() as db:
        job=enqueue(store,'training',key,1,db=db)
        store.insert('training_runs',dict(id=key,snapshot_id=snapshot_id,owner_id='local',job_id=job['id'],status='queued',configuration=dict(regularization=values,allow_exploratory=bool(config.get('allow_exploratory')),seed=snapshot['seed']),versions=versions),db)
    return store.one('SELECT * FROM training_runs WHERE id=%s',(key,))


def metric(y,p):
    from sklearn.metrics import mean_absolute_error, f1_score, balanced_accuracy_score, confusion_matrix, cohen_kappa_score
    kappa=cohen_kappa_score(y,p,labels=list(range(5)),weights='quadratic') if len(set(y))>1 else None
    return dict(mae=float(mean_absolute_error(y,p)),macro_f1=float(f1_score(y,p,labels=list(range(5)),average='macro',zero_division=0)),balanced_accuracy=float(balanced_accuracy_score(y,p)),confusion=confusion_matrix(y,p,labels=list(range(5))).tolist(),quadratic_kappa=float(kappa) if kappa is not None and np.isfinite(kappa) else None,coverage=1.,abstention_count=0,n=len(y))


def portable(pipeline,names):
    imputer=pipeline.named_steps['imputer']; scaler=pipeline.named_steps['scaler']; model=pipeline.named_steps['model']
    return dict(format='psycon-logistic-json-1',feature_version=FEATURE_VERSION,features=names,medians=imputer.statistics_.tolist(),indicator_features=imputer.indicator_.features_.tolist(),means=scaler.mean_.tolist(),scales=scaler.scale_.tolist(),coefficients=model.coef_.tolist(),intercept=model.intercept_.tolist(),classes=model.classes_.tolist())


def infer(artifact,values):
    x=np.asarray([values.get(n,np.nan) if values.get(n) is not None else np.nan for n in artifact['features']],dtype=float)
    missing=np.isnan(x); x=np.where(missing,np.asarray(artifact['medians']),x)
    x=np.concatenate([x,missing[np.asarray(artifact['indicator_features'],dtype=int)].astype(float)])
    x=(x-np.asarray(artifact['means']))/np.asarray(artifact['scales'])
    logits=np.asarray(artifact['coefficients'])@x+np.asarray(artifact['intercept'])
    if len(logits)==1:
        probability=1/(1+np.exp(-np.clip(logits[0],-700,700))); probs=np.asarray([1-probability,probability])
    else:
        logits-=max(logits); probs=np.exp(logits); probs/=sum(probs)
    distribution={str(k):float(v) for k,v in zip(artifact['classes'],probs)}
    return int(artifact['classes'][int(np.argmax(probs))]),distribution


def grouped_interval(y,p,groups,seed):
    unique=sorted(set(groups))
    if len(unique)<3:
        return dict(status='unavailable',reason='Fewer than three independent held-out groups')
    rng=np.random.default_rng(seed); samples=[]
    for _ in range(500):
        chosen=rng.choice(unique,size=len(unique),replace=True)
        indices=[i for g in chosen for i,x in enumerate(groups) if x==g]
        samples.append(float(np.mean(np.abs(np.asarray(y)[indices]-np.asarray(p)[indices]))))
    return dict(method='500 connected-session-group bootstrap draws',mae_95_interval=np.quantile(samples,[.025,.975]).tolist(),groups=len(unique))


def fit(store,run):
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    snapshot=store.one('SELECT * FROM training_snapshots WHERE id=%s',(run['snapshot_id'],))
    if store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],)):
        raise StaleJob('Snapshot invalidated before fitting')
    if hashlib.sha256(encode(snapshot['manifest']).encode()).hexdigest()!=snapshot['sha256']:
        raise ValueError('Frozen manifest hash mismatch')
    examples=snapshot['manifest']['examples']; targets=sorted({target for e in examples for target in e['labels']})
    models=[]; unsupported={}; definition=snapshot['manifest']['task_definition']
    for target in targets:
        store.one('SELECT id FROM jobs WHERE id=%s',(run['job_id'],))  # Lease guard before each target.
        retained=store.rows('SELECT * FROM model_versions WHERE run_id=%s AND target=%s',(run['id'],target))
        if retained:
            for model in retained: load(store,model)
            models.extend(model['id'] for model in retained)
            continue
        rows=[e for e in examples if target in e['labels']]
        by_split={split:[e for e in rows if e['split']==split] for split in ('train','validation','test')}
        train=by_split['train']; labels=[e['labels'][target]['score'] for e in train]
        if len(train)<definition['min_train'] or len({e['component'] for e in train})<definition['min_groups'] or len(set(labels))<2:
            unsupported[target]='Requires at least 12 training participants, three independent groups, and two observed score classes'
            continue
        names=sorted({n for e in train for n,f in e['features'].items() if (('__' not in n) or n.startswith(target+'__')) and f['value'] is not None})
        if not names:
            unsupported[target]='No supported measured predictors'
            continue
        def matrix(records):
            return np.asarray([[e['features'].get(n,{}).get('value') if e['features'].get(n,{}).get('value') is not None else np.nan for n in names] for e in records],dtype=float)
        x=matrix(train); y=np.asarray(labels)
        median=int(np.median(y)); best=None; best_mae=float('inf'); selected_c=None
        for c in run['configuration']['regularization']:
            pipeline=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('scaler',StandardScaler()),('model',LogisticRegression(C=c,class_weight='balanced',max_iter=2000,random_state=run['configuration']['seed']))])
            pipeline.fit(x,y)
            validation=by_split['validation']
            score=float(np.mean(np.abs(pipeline.predict(matrix(validation))-np.asarray([e['labels'][target]['score'] for e in validation])))) if validation else 0
            if best is None or score<best_mae:
                best= pipeline; best_mae=score; selected_c=c
            if not validation: break  # No hyperparameter search without validation.
        artifact=portable(best,names)
        if not np.allclose([infer(artifact,dict(zip(names,row)))[0] for row in x],best.predict(x)):
            raise ValueError('Portable model differs from fitted estimator')
        mid=uid(); folder=store.root/'models'/mid; folder.mkdir(parents=True,exist_ok=False)
        path=folder/'model.json'; path.write_text(encode(artifact),encoding='utf-8')
        evaluations=[]
        for split in ('validation','test'):
            records=by_split[split]
            if not records: continue
            truth=[e['labels'][target]['score'] for e in records]; predictions=best.predict(matrix(records)).tolist()
            metrics=metric(truth,predictions)
            slices={}
            for context in sorted({e['metadata']['context'] for e in records}):
                indices=[i for i,e in enumerate(records) if e['metadata']['context']==context]
                groups={records[i]['component'] for i in indices}
                slices[context]=dict(n=len(indices),groups=len(groups),metrics=metric([truth[i] for i in indices],[predictions[i] for i in indices]) if len(groups)>=3 else None,reason=None if len(groups)>=3 else 'Fewer than three independent held-out recording groups')
            metrics['context_slices']=slices
            probs=best.predict_proba(matrix(records)); classes=best.named_steps['model'].classes_
            onehot=np.asarray([[int(v==c) for c in classes] for v in truth]); metrics['multiclass_brier']=float(np.mean(np.sum((probs-onehot)**2,axis=1)))
            metrics['probability_status']='Uncalibrated classifier probabilities; no calibrated confidence claim'
            baseline=metric(truth,[median]*len(truth)); baseline['majority_class']=Counter(labels).most_common(1)[0][0]
            evaluations.append(dict(id=uid(),model_id=mid,split=split,n=len(truth),metrics=metrics,baseline=baseline,uncertainty=grouped_interval(truth,predictions,[e['component'] for e in records],run['configuration']['seed'])))
        val=next((r for r in evaluations if r['split']=='validation'),None); test=next((r for r in evaluations if r['split']=='test'),None)
        evaluated=bool(val and test and val['n']>=definition['min_validation'] and test['n']>=definition['min_test'] and val['metrics']['mae']<val['baseline']['mae'] and test['metrics']['mae']<test['baseline']['mae'])
        limitations=['Ordinal scores approximated with multinomial logistic regression','Operational behavior annotations, not psychological diagnoses','Uncalibrated probabilities']
        if not evaluated: limitations.append('Exploratory model: prespecified held-out criteria were not satisfied')
        with store.connect() as db:
            if db.execute('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],)).fetchone(): raise StaleJob('Snapshot invalidated during fitting')
            asset=register(store,path,'model',root=folder,db=db)
            store.insert('model_versions',dict(id=mid,run_id=run['id'],family=snapshot['task_id'],target=target,status='candidate',evaluation_status='evaluated' if evaluated else 'exploratory',feature_schema=dict(version=FEATURE_VERSION,names=names),manifest=dict(rubric=snapshot['manifest'].get('rubric'),snapshot_hash=snapshot['sha256'],seed=snapshot['seed'],regularization=selected_c,versions=run['versions'],train_n=len(train),train_groups=len({e['component'] for e in train}),pass_criteria=definition['pass_criteria']),limitations=limitations),db)
            store.insert('model_artifacts',dict(id=uid(),model_id=mid,asset_id=asset['id'],format=artifact['format']),db)
            for evaluation in evaluations: store.insert('model_evaluations',evaluation,db)
            store.insert('training_run_events',dict(id=uid(),run_id=run['id'],message=f'Fitted {target}: {len(train)} training records; '+('evaluated' if evaluated else 'exploratory')),db)
        models.append(mid)
    return dict(models=models,unsupported_targets=unsupported,status='complete' if models else 'insufficient_data')


def process_training(store):
    store.execute("UPDATE training_runs r SET status=j.status,error=COALESCE(j.error,r.error) FROM jobs j WHERE r.job_id=j.id AND r.owner_id='local' AND r.status IN ('queued','training') AND j.status IN ('failed','canceled')")
    job=claim(store,'training')
    if not job: return None
    run=store.one('SELECT * FROM training_runs WHERE id=%s',(job['subject_id'],))
    try:
        with lease(store,job):
            try:
                actual=runtime_versions(); previous=run['versions']
                if previous.get('execution_runtime') and previous['execution_runtime']!=actual:
                    raise ValueError('Retry runtime differs from the original fitting runtime; queue a new reproducible run')
                versions=dict(actual,enqueue_runtime=previous.get('enqueue_runtime',previous),execution_runtime=actual)
                run['versions']=versions
                store.execute("UPDATE training_runs SET status='training',versions=%s,error=NULL WHERE id=%s",(Jsonb(versions),run['id']))
                result=fit(store,run)
                store.execute('UPDATE training_runs SET status=%s WHERE id=%s',(result['status'],run['id']))
                store.insert('training_run_events',dict(id=uid(),run_id=run['id'],message=encode(result)))
                finish(store,job,result)
            except StaleJob: raise
            except Exception as exc:
                from .jobs import retryable
                retry=retryable(exc)
                status='queued' if retry and job['attempt']<job['max_attempts'] else 'failed'
                store.execute('UPDATE training_runs SET status=%s,error=%s WHERE id=%s',(status,str(exc)[:1500],run['id']))
                finish(store,job,error=str(exc)[:1500],retry=retry)
    except StaleJob:
        return None
    return store.one('SELECT * FROM training_runs WHERE id=%s',(run['id'],))


def load(store,model):
    artifact=store.one('SELECT asset_id FROM model_artifacts WHERE model_id=%s',(model['id'],))
    path=resolve(store,artifact['asset_id'],verify=True)
    result=json.loads(path.read_text(encoding='utf-8'))
    if result['format']!='psycon-logistic-json-1' or result['feature_version']!=FEATURE_VERSION or result['features']!=model['feature_schema']['names']:
        raise ValueError('Model feature schema is incompatible')
    return result


def activate(store,mid,operator,reason,*,exploratory=False,rollback=False):
    if not operator or not reason: raise ValueError('Operator and activation reason are required')
    model=store.one("SELECT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE m.id=%s AND r.owner_id='local'",(mid,))
    if model['status']=='needs_retraining': raise ValueError('Model depends on withdrawn or corrected data')
    if model['evaluation_status']!='evaluated' and not exploratory: raise ValueError('Explicit exploratory acknowledgment is required')
    load(store,model)
    with store.connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(%s)',(0x50535945,))
        current=db.execute('SELECT * FROM model_versions WHERE id=%s FOR UPDATE',(mid,)).fetchone()
        if current['status']=='needs_retraining': raise ValueError('Model was invalidated during activation')
        invalid=db.execute('SELECT i.id FROM snapshot_invalidations i JOIN training_runs r ON r.snapshot_id=i.snapshot_id WHERE r.id=%s',(model['run_id'],)).fetchone()
        if invalid: raise ValueError('Model snapshot is invalidated')
        if rollback and not db.execute("SELECT id FROM model_deployments WHERE model_id=%s AND action IN ('activate','rollback')",(mid,)).fetchone(): raise ValueError('Rollback requires a previously deployed version; activate a new candidate explicitly')
        previous=db.execute("SELECT id FROM model_versions WHERE family=%s AND target=%s AND status='active'",(model['family'],model['target'])).fetchone()
        db.execute("UPDATE model_versions SET status='candidate' WHERE family=%s AND target=%s AND status='active'",(model['family'],model['target']))
        db.execute("UPDATE model_versions SET status='active' WHERE id=%s",(mid,))
        store.insert('model_deployments',dict(id=uid(),model_id=mid,previous_model_id=previous['id'] if previous else None,action='rollback' if rollback else 'activate',operator_id=operator,reason=reason),db)
    return store.one('SELECT * FROM model_versions WHERE id=%s',(mid,))


def predict(store,speaker_id,context_windows=None):
    speaker=store.one('SELECT * FROM speakers WHERE id=%s',(speaker_id,)); session=store.session(speaker['session_id'])
    values={f['name']:f['value'] for f in store.rows('SELECT * FROM features WHERE speaker_id=%s',(speaker_id,)) if f['value'] is not None}
    from .datasets import contextual_features
    measured_names=set(values)
    values.update(contextual_features(session,store.rows('SELECT * FROM utterances WHERE speaker_id=%s',(speaker_id,)),speaker_id))
    models=store.rows("SELECT m.* FROM model_versions m JOIN training_runs r ON r.id=m.run_id WHERE m.status='active' AND r.owner_id='local' ORDER BY m.family,m.target")
    results=[]
    for model in models:
        abstention=None; score=None; distribution=None
        model_values=dict(values)
        try:
            artifact=load(store,model)
            if session['status']!='complete': abstention='Processing is incomplete'
            if model['family']=='at' and (model['target']=='K' or model['target']>='M'):
                windows=(context_windows or {}).get(model['target'],[])
                if not windows:
                    abstention='Reviewed independent event/response context is required; global features cannot establish event-linked change'
                else:
                    for w in windows:
                        if not isinstance(w,dict) or type(w.get('start_s')) not in (int,float) or type(w.get('end_s')) not in (int,float) or not 0<=w['start_s']<w['end_s']<=session['duration'] or not w.get('reviewer_id') or not w.get('context'):
                            raise ValueError('Inference context needs a reviewer, observable event, and valid recording windows')
                    kinds={w.get('kind') for w in windows}
                    if not {'event','response'}<=kinds or (model['target']>='Q' and 'same_session_baseline' not in kinds):
                        raise ValueError('Event-linked prediction lacks event/response or same-session baseline')
                    baseline=[w for w in windows if w['kind']=='same_session_baseline']; events=[w for w in windows if w['kind']=='event']
                    if baseline and max(w['end_s'] for w in baseline)>min(w['start_s'] for w in events): raise ValueError('Baseline must precede the same-session event')
                    responses=[w for w in windows if w['kind']=='response']
                    if min(w['start_s'] for w in responses)<min(w['start_s'] for w in events): raise ValueError('Response must not precede the event')
                    from .datasets import window_features
                    measured=window_features(dict(utterances=store.rows('SELECT * FROM utterances WHERE speaker_id=%s',(speaker_id,))),speaker_id,windows)
                    model_values.update({model['target']+'__'+k:v for k,v in measured.items()})
            if not any(n in measured_names for n in artifact['features']): abstention='Measured conversational predictors unavailable'
            if not abstention: score,distribution=infer(artifact,model_values)
        except (ValueError,LookupError,OSError) as exc:
            abstention=str(exc)
        row=dict(id=uid(),model_id=model['id'],session_id=session['id'],speaker_id=speaker_id,input_revision=session['input_revision'],score=score,distribution=distribution,uncertainty=dict(status='uncalibrated',evaluation_status=model['evaluation_status'],limitations=model['limitations']),abstention=abstention,inputs=dict(feature_version=FEATURE_VERSION,features=model_values,context_windows=context_windows or {},session_context={k:session[k] for k in ('context','topic','conditions','recorded_at')}))
        with store.connect() as db:
            store.insert('model_predictions',row,db)
            for e in db.execute('SELECT id FROM evidence WHERE speaker_id=%s ORDER BY start_s LIMIT 24',(speaker_id,)):
                store.insert('prediction_evidence',dict(prediction_id=row['id'],evidence_id=e['id']),db)
        results.append(dict(row,family=model['family'],target=model['target'],evaluation_status=model['evaluation_status'],lineage=dict(snapshot_hash=model['manifest']['snapshot_hash'],feature_schema=model['feature_schema'],versions=model['manifest']['versions'])))
    return dict(status='available' if models else 'No active trained model',predictions=results)
