"""Nested group model selection for the frozen, unreviewed source-score task.

No observation, approval, or source mapping is created. The outer labels never
enter inner selection. This retrospective development exercise is not a new
independent test, even though all preprocessing is fitted within training folds.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import warnings

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import confusion_matrix

from backend.instrument.training import portable, infer
from backend.instrument.datasets import FEATURE_VERSION

POLICY = {
    'version': 'source-nested-1', 'seed': 42,
    'objective': 'equal-group mean absolute error, within each target',
    'minimum_inner_gain': .05,
    'candidates': ['median', 'mode', 'logistic-0.01-none', 'logistic-0.1-none',
                   'logistic-1-none', 'logistic-0.01-balanced',
                   'logistic-0.1-balanced', 'ridge-10', 'ridge-100'],
    'min_train': 12, 'min_groups': 3,
    'fallback': 'training median; population reference, not individualized prediction',
    'status': 'Retrospective development after prior grouped results were examined',
}


def score(e, target):
    return int(e['labels'][target]['score'])


def eligible_names(train, target):
    return sorted({n for e in train for n, f in e['features'].items()
                   if ('__' not in n or n.startswith(target+'__')) and f['value'] is not None})


def matrix(records, names):
    return np.asarray([[e['features'].get(n, {}).get('value')
                        if e['features'].get(n, {}).get('value') is not None else np.nan
                        for n in names] for e in records], dtype=float)


def fit_candidate(train, target, candidate):
    y = np.array([score(e, target) for e in train])
    if not len(y):
        raise ValueError('No training labels')
    counts = Counter(y.tolist())
    median = int(np.median(y))
    if candidate in ('median', 'mode'):
        constant = median if candidate == 'median' else min(counts, key=lambda k: (-counts[k], k))
        return dict(format='psycon-source-constant-1', feature_version=FEATURE_VERSION, features=[], score=constant,
                    distribution={str(k): v/len(y) for k, v in sorted(counts.items())},
                    method=candidate, fallback=False)
    names = eligible_names(train, target)
    if (len(train) < POLICY['min_train'] or
            len({e['component'] for e in train}) < POLICY['min_groups'] or
            len(counts) < 2 or not names):
        artifact = fit_candidate(train, target, 'median')
        artifact['fallback'] = True
        return artifact
    steps = [('imputer', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
             ('scaler', StandardScaler())]
    if candidate.startswith('logistic'):
        _, c, weighting = candidate.split('-')
        estimator = LogisticRegression(C=float(c), class_weight=None if weighting == 'none' else weighting,
                                       max_iter=2000, random_state=42)
    else:
        estimator = Ridge(alpha=float(candidate.split('-')[1]))
    pipe = Pipeline(steps+[('model', estimator)])
    pipe.fit(matrix(train, names), y)
    if candidate.startswith('logistic'):
        artifact = portable(pipe, names)
    else:
        imputer, scaler = pipe.named_steps['imputer'], pipe.named_steps['scaler']
        artifact = dict(format='psycon-source-ridge-1', feature_version=FEATURE_VERSION, features=names,
                        medians=imputer.statistics_.tolist(), indicator_features=imputer.indicator_.features_.tolist(),
                        means=scaler.mean_.tolist(), scales=scaler.scale_.tolist(),
                        coefficients=estimator.coef_.tolist(), intercept=float(estimator.intercept_))
    artifact.update(method=candidate, fallback=False)
    expected = pipe.predict(matrix(train, names))
    if candidate.startswith('ridge'):
        expected = np.clip(np.floor(expected+.5), 0, 4).astype(int)
    actual = [predict(artifact, e)[0] for e in train]
    if not np.array_equal(expected, actual):
        raise ValueError('Portable predictions do not reproduce fitted model')
    return artifact


def predict(artifact, example):
    return infer_source(artifact, {n: f['value'] for n, f in example['features'].items()})


def infer_source(artifact, values):
    return infer(artifact, values)


def select(train, target):
    groups = sorted({e['component'] for e in train})
    losses = {}
    for candidate in POLICY['candidates']:
        group_losses = []
        for group in groups:
            development = [e for e in train if e['component'] != group]
            validation = [e for e in train if e['component'] == group]
            if not development:
                continue
            assert not {e['component'] for e in development} & {e['component'] for e in validation}
            model = fit_candidate(development, target, candidate)
            group_losses.append(float(np.mean([abs(predict(model, e)[0]-score(e, target)) for e in validation])))
        losses[candidate] = float(np.mean(group_losses)) if group_losses else None
    if losses['median'] is None:
        return 'median', losses
    best = min(POLICY['candidates'], key=lambda c: (losses[c], POLICY['candidates'].index(c)))
    if losses['median']-losses[best] < POLICY['minimum_inner_gain']:
        best = 'median'
    return best, losses


def measures(rows):
    y = np.array([r['rating'] for r in rows]); p = np.array([r['prediction'] for r in rows])
    cm = confusion_matrix(y, p, labels=range(5))
    recalls = []; classes = []
    for k in range(5):
        tp = int(cm[k, k]); fn = int(cm[k].sum()-tp); fp = int(cm[:, k].sum()-tp)
        tn = int(cm.sum()-tp-fn-fp)
        sensitivity = tp/(tp+fn) if tp+fn else None
        precision = tp/(tp+fp) if tp+fp else None
        specificity = tn/(tn+fp) if tn+fp else None
        if sensitivity is not None:
            recalls.append(sensitivity)
        classes.append(dict(score=k, support=tp+fn, predicted=tp+fp, sensitivity=sensitivity,
                            precision=precision, specificity=specificity, tp=tp, fn=fn, fp=fp, tn=tn))
    groups = sorted({r['group'] for r in rows})
    return dict(n=len(rows), correct=int((y==p).sum()), accuracy=float(np.mean(y==p)),
                mae=float(np.mean(abs(y-p))), within_one=float(np.mean(abs(y-p)<=1)),
                macro_sensitivity=float(np.mean(recalls)), confusion=cm.tolist(), by_score=classes,
                equal_group_mae=float(np.mean([np.mean([abs(r['rating']-r['prediction']) for r in rows if r['group']==g]) for g in groups])))


def bootstrap_difference(rows, draws=2000):
    """Paired resampling of five known groups; descriptive, unstable with few groups."""
    groups = sorted({r['group'] for r in rows}); rng = np.random.default_rng(42); delta = []
    for _ in range(draws):
        chosen = rng.choice(groups, len(groups), replace=True)
        sampled = [r for g in chosen for r in rows if r['group']==g]
        delta.append(float(np.mean([abs(r['rating']-r['prediction'])-abs(r['rating']-r['baseline']) for r in sampled])))
    return dict(method='paired known-group bootstrap', draws=draws, groups=len(groups),
                model_minus_median_mae_95_percentile=np.quantile(delta, [.025, .975]).tolist(),
                limitation='Exploratory interval; five groups, unresolved overlaps, no population validity or significance claim')


def run_analysis(examples, targets, output, snapshot_hash):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    groups = sorted({e['component'] for e in examples}); aliases = {g: f'Group {i+1}' for i,g in enumerate(groups)}
    rows = []; folds = []; final = {}; selected_counts = Counter()
    for target in targets:
        eligible = [e for e in examples if target in e['labels']]
        for omitted in groups:
            train = [e for e in eligible if e['component'] != omitted]
            test = [e for e in eligible if e['component'] == omitted]
            if not test: continue
            assert not {e['component'] for e in train} & {e['component'] for e in test}
            chosen, inner = select(train, target)
            model = fit_candidate(train, target, chosen)
            baseline = fit_candidate(train, target, 'median')
            selected_counts[model['method']] += 1
            folds.append(dict(target=target,omitted=aliases[omitted],train_n=len(train),test_n=len(test),
                              selected=chosen,served_method=model['method'],fallback=model['fallback'],inner_group_mae=inner))
            for e in test:
                rows.append(dict(target=target,group=aliases[omitted],speaker_id=e['speaker_id'],
                                 rating=score(e,target),prediction=predict(model,e)[0],baseline=predict(baseline,e)[0],
                                 selected=chosen,served_method=model['method'],fallback=model['fallback']))
        chosen, inner = select(eligible, target)
        model = fit_candidate(eligible, target, chosen)
        model.update(target=target, snapshot_hash=snapshot_hash, selection=inner,
                     label_status='unreviewed source scores', evaluation_status='exploratory',
                     train_n=len(eligible), train_groups=len({e['component'] for e in eligible}))
        final[target] = model
        print(target, 'final method', model['method'], flush=True)
    baseline_rows = [dict(r,prediction=r['baseline']) for r in rows]
    original = json.loads(Path('.runtime/results-analysis/grouped-cv-predictions.json').read_text())
    original = [r for r in original if r['prediction'] is not None]
    original_keys = {(r['target'],r['speaker_id']) for r in original}
    common = [r for r in rows if (r['target'],r['speaker_id']) in original_keys]
    summary = dict(policy=POLICY,snapshot_hash=snapshot_hash,examples=len(examples),known_groups=len(groups),
                   labels=len(rows),nested=measures(rows),median=measures(baseline_rows),
                   common_original_coverage=dict(n=len(common),original=measures(original),
                                                revised=measures(common),median=measures([dict(r,prediction=r['baseline']) for r in common])),
                   paired_uncertainty=bootstrap_difference(rows),fold_method_counts=dict(selected_counts),
                   final_methods={t:m['method'] for t,m in final.items()},
                   per_target={t:measures([r for r in rows if r['target']==t]) for t in targets},folds=folds,
                   independent_final_test=dict(n=0,status='Unavailable; all source groups already examined'),
                   limitations=['Retrospective development, not preregistered or independently confirmed',
                                'Raw source scores, not validated personality or psychologist consensus',
                                'Known groups only; unknown participant overlap remains',
                                'Class sensitivity is one-versus-rest exact score recall, not clinical sensitivity',
                                'Constant fallback is a population reference, not individualized behavior prediction',
                                'P1-P12 dominate; pooled targets are not a single validated construct'])
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'nested-predictions.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (output/'models.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    return summary


def main():
    import argparse
    from ml.src.environment import load_project_environment
    from backend.instrument.store import Store, encode
    load_project_environment(override=False)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register-candidates',action='store_true',help='Register final fits as exploratory candidates, never activate them')
    args=parser.parse_args()
    store = Store('instance/instrument')
    try:
        run = store.one('SELECT * FROM training_runs WHERE id=%s',('b207e378-0698-47f7-bdd4-d50e9ebbb982',))
        snapshot = store.one('SELECT * FROM training_snapshots WHERE id=%s',(run['snapshot_id'],))
        assert not store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],))
        assert hashlib.sha256(encode(snapshot['manifest']).encode()).hexdigest()==snapshot['sha256']
        targets = [m['target'] for m in store.rows('SELECT target FROM model_versions WHERE run_id=%s ORDER BY target',(run['id'],))]
    finally:
        store.pool.close()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        summary=run_analysis(snapshot['manifest']['examples'],targets,'.runtime/defensible-analysis',snapshot['sha256'])
    public = {k:v for k,v in summary.items() if k!='folds'}
    Path('docs/report_assets/defensible-source-summary.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
    if args.register_candidates:
        register_candidates(run['snapshot_id'],summary)
    print(json.dumps({k:summary[k] for k in ['nested','median','final_methods','paired_uncertainty']},indent=2))


def register_candidates(snapshot_id, summary):
    """Record final fits without silently promoting a below-baseline system."""
    from backend.instrument.store import Store, uid, encode
    from backend.instrument.assets import register
    from backend.instrument.training import runtime_versions
    store=Store('instance/instrument'); run_id=uid(); models=json.loads(Path('.runtime/defensible-analysis/models.json').read_text())
    rows=json.loads(Path('.runtime/defensible-analysis/nested-predictions.json').read_text())
    versions=runtime_versions()
    versions['selection_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        with store.connect() as db:
            if db.execute('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot_id,)).fetchone():
                raise ValueError('Snapshot was invalidated; candidates withheld')
            store.insert('training_runs',dict(id=run_id,snapshot_id=snapshot_id,owner_id='local',job_id=None,
                         status='complete',configuration=POLICY,versions=versions,error=None),db)
            for target, artifact in models.items():
                mid=uid();folder=store.root/'models'/mid;folder.mkdir(parents=True,exist_ok=False)
                path=folder/'model.json';path.write_text(encode(artifact),encoding='utf-8')
                asset=register(store,path,'model',root=folder,db=db)
                limitations=summary['limitations']+['Candidate only: nested procedure remains below median baseline overall',
                              'Empirical class frequencies are not calibrated individual confidence; ridge provides no class probabilities']
                if artifact['format']=='psycon-source-constant-1':
                    limitations.append('Population reference constant, not an individualized trained behavior estimate')
                manifest=dict(snapshot_hash=summary['snapshot_hash'],versions=versions,train_n=artifact['train_n'],
                              train_groups=artifact['train_groups'],selected_method=artifact['method'],policy=POLICY,
                              label_policy='Unreviewed raw source-form ratings',validation_status='Retrospective nested group diagnostics; no independent final test')
                store.insert('model_versions',dict(id=mid,run_id=run_id,family='source-v5-exploratory',target=target,
                             status='candidate',evaluation_status='exploratory',feature_schema=dict(version=FEATURE_VERSION,names=artifact['features']),
                             manifest=manifest,limitations=limitations),db)
                store.insert('model_artifacts',dict(id=uid(),model_id=mid,asset_id=asset['id'],format=artifact['format']),db)
                store.insert('model_evaluations',dict(id=uid(),model_id=mid,split='retrospective_nested_cv',
                             n=summary['per_target'][target]['n'],metrics=summary['per_target'][target],
                             baseline=measures([dict(r,prediction=r['baseline']) for r in rows if r['target']==target]),
                             uncertainty={'status':'not estimated per target','reason':'Sparse target classes and few known groups; pooled paired analysis is reported separately'}),db)
            store.insert('training_run_events',dict(id=uid(),run_id=run_id,message='Fourteen nested-selection final fits saved as exploratory candidates; active deployment unchanged because the procedure loses to baseline'),db)
        Path('.runtime/defensible-analysis/candidate-run.json').write_text(encode(dict(run_id=run_id,models=len(models),status='candidate',versions=versions)),encoding='utf-8')
        print('Registered candidate run',run_id,flush=True)
    finally:store.pool.close()


if __name__=='__main__':
    main()
