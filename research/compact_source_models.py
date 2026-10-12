"""One disclosed compact/ordinal development experiment on existing source scores.

Policy is fixed before running this experiment. Prior outer results have already
been examined, so even nested group estimates remain retrospective development.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.ensemble import RandomForestRegressor,ExtraTreesRegressor
from backend.instrument.training import portable,infer
from backend.instrument.datasets import FEATURE_VERSION
from research.defensible_source_models import fit_candidate,score,matrix,measures,bootstrap_difference

CORE=('speaking_share','words_per_minute','mean_turn_duration','response_latency')
CONVERSATION=CORE+('question_rate','proposal_rate','acknowledgement_ratio','interruption_candidate_rate')
POLICY=dict(version='source-compact-1',seed=42,features={'core':CORE,'conversation':CONVERSATION},
 candidates=['median','mode','core-logistic-0.1-none','core-logistic-1-none',
             'compact-logistic-0.1-none','compact-logistic-0.1-balanced',
             'core-ridge-10','compact-ridge-10','compact-ordinal-0.1','compact-ordinal-1',
             'compact-forest','compact-extra'],
 objective='Lowest equal-group inner MAE subject to observed-class sensitivity guard',
 minimum_mae_gain=.025,maximum_sensitivity_loss=.02,min_train=12,min_groups=3,
 trees=64,max_depth=3,min_leaf=4,
 logistic_tie_tolerance=1e-12,
 status='Retrospective development after prior results; no independent final test',
 tie_break='Declaration order favors training references')


def fit(train,target,candidate):
    if candidate in ('median','mode'):return fit_candidate(train,target,candidate)
    feature_set=CORE if candidate.startswith('core-') else CONVERSATION
    names=[n for n in feature_set if any(e['features'].get(n,{}).get('value') is not None for e in train)]
    y=np.asarray([score(e,target) for e in train])
    if len(train)<12 or len({e['component'] for e in train})<3 or len(set(y))<2 or not names:
        m=fit_candidate(train,target,'median');m['fallback']=True;return m
    pre=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('scaler',StandardScaler())])
    x=pre.fit_transform(matrix(train,names)); im=pre.named_steps['imputer'];sc=pre.named_steps['scaler']
    base=dict(feature_version=FEATURE_VERSION,features=names,medians=im.statistics_.tolist(),
              indicator_features=im.indicator_.features_.tolist(),means=sc.mean_.tolist(),scales=sc.scale_.tolist(),
              method=candidate,fallback=False)
    if 'logistic' in candidate:
        pieces=candidate.split('-');est=LogisticRegression(C=float(pieces[2]),class_weight=None if pieces[3]=='none' else 'balanced',max_iter=2000,random_state=42)
        est.fit(x,y);pre.steps.append(('model',est));m=portable(pre,names);m['tie_tolerance']=1e-12
        probabilities=est.predict_proba(x)
        expected=np.asarray([est.classes_[np.flatnonzero(p>=max(p)-1e-12)[0]] for p in probabilities])
    elif 'ridge' in candidate:
        est=Ridge(alpha=float(candidate.split('-')[-1])).fit(x,y)
        m=dict(base,format='psycon-source-ridge-1',coefficients=est.coef_.tolist(),intercept=float(est.intercept_))
        expected=np.clip(np.floor(est.predict(x)+.5),0,4).astype(int)
    elif 'ordinal' in candidate:
        thresholds=[]; exceed=[]
        for k in range(4):
            binary=(y>k).astype(int)
            if len(set(binary))==1:
                thresholds.append({'constant':float(binary[0])});exceed.append(np.full(len(y),binary[0],dtype=float))
            else:
                est=LogisticRegression(C=float(candidate.split('-')[-1]),max_iter=2000,random_state=42).fit(x,binary)
                thresholds.append(dict(coefficients=est.coef_[0].tolist(),intercept=float(est.intercept_[0])))
                exceed.append(est.predict_proba(x)[:,1])
        m=dict(base,format='psycon-source-ordinal-1',thresholds=thresholds)
        expected=(np.minimum.accumulate(np.asarray(exceed),axis=0)>.5).sum(axis=0)
    else:
        cls=ExtraTreesRegressor if candidate.endswith('extra') else RandomForestRegressor
        est=cls(n_estimators=64,max_depth=3,min_samples_leaf=4,random_state=42,n_jobs=1).fit(x,y)
        trees=[]
        for estimator in est.estimators_:
            t=estimator.tree_;trees.append(dict(left=t.children_left.tolist(),right=t.children_right.tolist(),
                feature=t.feature.tolist(),threshold=t.threshold.tolist(),value=t.value[:,0,0].tolist()))
        m=dict(base,format='psycon-source-forest-1',trees=trees)
        expected=np.clip(np.floor(est.predict(x)+.5),0,4).astype(int)
    m.update(method=candidate,fallback=False)
    actual=[predict(m,e) for e in train]
    if not np.array_equal(actual,expected):raise ValueError('Portable model does not reproduce fitted predictions')
    return m


def predict(model,example):
    return infer(model,{n:f['value'] for n,f in example['features'].items()})[0]


def select(train,target,cache=None):
    groups=sorted({e['component'] for e in train});diagnostics={}
    for candidate in POLICY['candidates']:
        rows=[]
        for group in groups:
            inner=[e for e in train if e['component']!=group];validation=[e for e in train if e['component']==group]
            if not inner:continue
            key=(target,candidate,tuple(sorted(e['speaker_id'] for e in inner)))
            if cache is not None and key in cache:m=cache[key]
            else:
                m=fit(inner,target,candidate)
                if cache is not None:cache[key]=m
            rows.extend(dict(group=group,rating=score(e,target),prediction=predict(m,e)) for e in validation)
        diagnostics[candidate]=measures(rows) if rows else None
    if diagnostics['median'] is None:return 'median',diagnostics
    ref=diagnostics['median']
    allowed=[c for c in POLICY['candidates'] if diagnostics[c]['macro_sensitivity']>=ref['macro_sensitivity']-.02]
    chosen=min(allowed,key=lambda c:(diagnostics[c]['equal_group_mae'],POLICY['candidates'].index(c)))
    if ref['equal_group_mae']-diagnostics[chosen]['equal_group_mae']<.025:chosen='median'
    return chosen,diagnostics


def main():
    from backend.instrument.store import encode
    root=Path('.runtime/model-hardening');manifest=json.loads((root/'snapshot.json').read_text())
    snapshot_hash=(root/'snapshot-hash.txt').read_text().strip()
    assert hashlib.sha256(encode(manifest).encode()).hexdigest()==snapshot_hash
    (root/'policy-before-results.json').write_text(json.dumps(POLICY,indent=2),encoding='utf-8')
    examples=manifest['examples'];groups=sorted({e['component'] for e in examples});aliases={g:f'Group {i+1}' for i,g in enumerate(groups)}
    targets=sorted(json.loads(Path('.runtime/defensible-analysis/models.json').read_text()))
    rows=[];folds=[];models={};comparisons={c:[] for c in POLICY['candidates']};cache={}
    for target in targets:
        eligible=[e for e in examples if target in e['labels']]
        for group in groups:
            train=[e for e in eligible if e['component']!=group];test=[e for e in eligible if e['component']==group]
            if not test:continue
            chosen,inner=select(train,target,cache);m=fit(train,target,chosen);baseline=fit(train,target,'median')
            folds.append(dict(target=target,group=aliases[group],selected=chosen,served_method=m['method'],
                inner={c:None if d is None else {k:d[k] for k in ('equal_group_mae','macro_sensitivity','accuracy')} for c,d in inner.items()}))
            for e in test:rows.append(dict(target=target,speaker_id=e['speaker_id'],group=aliases[group],rating=score(e,target),
                prediction=predict(m,e),baseline=predict(baseline,e),selected=chosen,served_method=m['method'],fallback=m['fallback']))
            for c in POLICY['candidates']:
                diagnostic=fit(train,target,c)
                comparisons[c].extend(dict(target=target,speaker_id=e['speaker_id'],group=aliases[group],rating=score(e,target),prediction=predict(diagnostic,e)) for e in test)
        chosen,inner=select(eligible,target,cache);m=fit(eligible,target,chosen)
        m.update(target=target,snapshot_hash=snapshot_hash,train_n=len(eligible),train_groups=len({e['component'] for e in eligible}),
            label_status='unreviewed source scores',evaluation_status='exploratory',selection_objective=POLICY['objective'])
        models[target]=m;print(target,chosen,flush=True)
    original=json.loads(Path('.runtime/results-analysis/grouped-cv-predictions.json').read_text())
    keys={(r['target'],r['speaker_id']) for r in original if r['prediction'] is not None}
    common=[r for r in rows if (r['target'],r['speaker_id']) in keys]
    reference=[dict(r,prediction=r['baseline']) for r in rows]
    train_rows=[dict(group=e['component'],rating=score(e,t),prediction=predict(m,e)) for t,m in models.items() for e in examples if t in e['labels']]
    summary=dict(policy=POLICY,snapshot_hash=snapshot_hash,examples=len(examples),groups=len(groups),
        nested=measures(rows),median=measures(reference),common=measures(common),
        median_common=measures([dict(r,prediction=r['baseline']) for r in common]),
        per_target={t:measures([r for r in rows if r['target']==t]) for t in targets},
        fixed_candidate_diagnostics={c:measures(r) for c,r in comparisons.items()},
        paired_uncertainty=bootstrap_difference(rows),final_methods={t:m['method'] for t,m in models.items()},
        final_training_replay=measures(train_rows),independent_test={'n':0,'status':'Unavailable'},
        limitations=['Post-hoc development; policy fixed before this run is not preregistration',
            'Known groups only; unresolved identity overlap and unreviewed labels remain',
            'No calibrated confidence, psychologist consensus, personality validity or report benefit',
            'Fixed candidate outer diagnostics must not be used to choose a winner',
            'Minority sensitivity constraint applies to inner selection, not guaranteed outer performance'])
    for name,value in [('summary',summary),('predictions',rows),('models',models),('folds',folds),('candidate-predictions',comparisons)]:
        (root/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
    Path('docs/report_assets/compact-source-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary['common'],indent=2))


if __name__=='__main__':main()
