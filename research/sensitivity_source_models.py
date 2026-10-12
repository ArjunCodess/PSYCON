"""A separately disclosed sensitivity-oriented nested development experiment.

Uses the same frozen examples and nine candidates as the MAE experiment. It is
post-hoc exploration, not confirmation, and never activates a model.
"""
import json
from pathlib import Path
import numpy as np

from research.defensible_source_models import POLICY,fit_candidate,predict,score,measures


def select_for_sensitivity(train,target):
    groups=sorted({e['component'] for e in train});results={}
    for candidate in POLICY['candidates']:
        observed=[]
        for group in groups:
            development=[e for e in train if e['component']!=group]
            validation=[e for e in train if e['component']==group]
            if not development:continue
            model=fit_candidate(development,target,candidate)
            observed.extend(dict(group=group,rating=score(e,target),prediction=predict(model,e)[0]) for e in validation)
        results[candidate]=measures(observed)['macro_sensitivity'] if observed else None
    if results['median'] is None:return 'median',results
    best=max(POLICY['candidates'],key=lambda c:(results[c],-POLICY['candidates'].index(c)))
    if results[best]-results['median']<.02:best='median'
    return best,results


def main():
    from ml.src.environment import load_project_environment
    from backend.instrument.store import Store
    load_project_environment(override=False);store=Store('instance/instrument')
    try:
        run=store.one('SELECT * FROM training_runs WHERE id=%s',('b207e378-0698-47f7-bdd4-d50e9ebbb982',))
        snapshot=store.one('SELECT * FROM training_snapshots WHERE id=%s',(run['snapshot_id'],))
        assert not store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],))
        targets=[m['target'] for m in store.rows('SELECT target FROM model_versions WHERE run_id=%s ORDER BY target',(run['id'],))]
    finally:store.pool.close()
    examples=snapshot['manifest']['examples'];groups=sorted({e['component'] for e in examples})
    aliases={g:f'Group {i+1}' for i,g in enumerate(groups)};rows=[];folds=[];models={}
    for target in targets:
        eligible=[e for e in examples if target in e['labels']]
        for group in groups:
            train=[e for e in eligible if e['component']!=group];test=[e for e in eligible if e['component']==group]
            if not test:continue
            assert not {e['component'] for e in train}&{e['component'] for e in test}
            chosen,inner=select_for_sensitivity(train,target);model=fit_candidate(train,target,chosen);baseline=fit_candidate(train,target,'median')
            folds.append(dict(target=target,omitted=aliases[group],selected=chosen,served_method=model['method'],inner_sensitivity=inner))
            rows.extend(dict(target=target,speaker_id=e['speaker_id'],group=aliases[group],rating=score(e,target),
                             prediction=predict(model,e)[0],baseline=predict(baseline,e)[0]) for e in test)
        chosen,inner=select_for_sensitivity(eligible,target);model=fit_candidate(eligible,target,chosen)
        model.update(target=target,snapshot_hash=snapshot['sha256'],inner_sensitivity=inner,evaluation_status='exploratory',
                     label_status='unreviewed source scores',selection_objective='observed-class macro sensitivity')
        models[target]=model;print(target,chosen,flush=True)
    original=json.loads(Path('.runtime/results-analysis/grouped-cv-predictions.json').read_text())
    keys={(r['target'],r['speaker_id']) for r in original if r['prediction'] is not None}
    common=[r for r in rows if (r['target'],r['speaker_id']) in keys]
    summary=dict(snapshot_hash=snapshot['sha256'],policy=dict(candidates=POLICY['candidates'],objective='Inner pooled observed-class macro sensitivity',
                  minimum_inner_gain=.02,tie_break='Candidate declaration order, favoring references',seed=42,
                  status='Additional retrospective development after original and MAE-oriented results were examined'),
                  all_labels=measures(rows),common_original_coverage=measures(common),
                  median_common=measures([dict(r,prediction=r['baseline']) for r in common]),
                  final_methods={t:m['method'] for t,m in models.items()},folds=folds,
                  limitations=['Not independently confirmed, preregistered, or promoted',
                               'Optimizing sensitivity may reduce accuracy or increase ordinal error',
                               'Same unreviewed source scores and unresolved-overlap limits as earlier analyses'])
    out=Path('.runtime/defensible-analysis')
    for name,value in [('sensitivity-summary',summary),('sensitivity-predictions',rows),('sensitivity-models',models)]:
        (out/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
    Path('docs/report_assets/sensitivity-source-summary.json').write_text(json.dumps({k:v for k,v in summary.items() if k!='folds'},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary['common_original_coverage'],indent=2))


if __name__=='__main__':main()
