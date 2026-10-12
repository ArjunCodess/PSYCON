"""Replay frozen source-score models and run retrospective grouped diagnostics.

Outputs remain private under .runtime. No labels, weights or approvals are changed.
Cross-validation concerns unreviewed source ratings, not validated psychology.
"""
import csv
import json
from pathlib import Path
import warnings
import importlib.metadata
import platform

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, mean_absolute_error, f1_score, cohen_kappa_score

from ml.src.environment import load_project_environment
from backend.instrument.store import Store
from backend.instrument.training import infer

RUN = 'b207e378-0698-47f7-bdd4-d50e9ebbb982'
OUT = Path('.runtime/results-analysis')


def metrics(rows):
    observed = [r for r in rows if r['prediction'] is not None]
    if not observed:
        return dict(n=0, total=len(rows), coverage=0, accuracy=None, mae=None, kappa=None)
    y = [r['rating'] for r in observed]; p = [r['prediction'] for r in observed]
    b = [r['baseline'] for r in observed]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        kappa = cohen_kappa_score(y, p, labels=list(range(5)), weights='quadratic')
    return dict(n=len(y), total=len(rows), coverage=len(y)/len(rows),
                correct=sum(a==v for a,v in zip(y,p)), accuracy=np.mean(np.array(y)==p).item(),
                mae=mean_absolute_error(y,p), macro_f1=f1_score(y,p,labels=sorted(set(y)),average='macro',zero_division=0),
                kappa=float(kappa) if np.isfinite(kappa) else None,
                baseline_accuracy=np.mean(np.array(y)==b).item(), baseline_mae=mean_absolute_error(y,b),
                confusion=confusion_matrix(y,p,labels=list(range(5))).tolist())


def main():
    load_project_environment(override=False)
    OUT.mkdir(exist_ok=True)
    store = Store('instance/instrument')
    try:
        run = store.one('SELECT * FROM training_runs WHERE id=%s',(RUN,))
        snapshot = store.one('SELECT * FROM training_snapshots WHERE id=%s',(run['snapshot_id'],))
        assert not store.rows('SELECT id FROM snapshot_invalidations WHERE snapshot_id=%s',(snapshot['id'],))
        examples = snapshot['manifest']['examples']
        models = store.rows('SELECT * FROM model_versions WHERE run_id=%s',(RUN,))
        form = store.rows("SELECT key,description FROM form_items WHERE form_id='psycon-context-5.0'")
    finally:
        store.pool.close()
    models.sort(key=lambda m:(len(m['target']),int(m['target'][1:]) if len(m['target'])>1 else ord(m['target'])))
    targets = [m['target'] for m in models]
    groups = sorted({e['component'] for e in examples})
    aliases = {g:'Group '+str(i+1) for i,g in enumerate(groups)}
    training=[]; cv=[]; folds=[]
    for model in models:
        target=model['target']
        selected=[e for e in examples if target in e['labels']]
        artifact=json.loads((Path('instance/instrument/models')/model['id']/'model.json').read_text())
        full_median=int(np.median([e['labels'][target]['score'] for e in selected]))
        for e in selected:
            pred,prob=infer(artifact,{n:f['value'] for n,f in e['features'].items()})
            training.append(dict(target=target,group=aliases[e['component']],speaker_id=e['speaker_id'],
                                 rating=e['labels'][target]['score'],prediction=pred,baseline=full_median,
                                 probability=prob,score_state='unreviewed source observation'))
        for group in groups:
            train=[e for e in selected if e['component']!=group]
            test=[e for e in selected if e['component']==group]
            if not test: continue
            labels=[e['labels'][target]['score'] for e in train]
            train_groups=len({e['component'] for e in train})
            reason=None
            if len(train)<12 or train_groups<3 or len(set(labels))<2:
                reason='Training fold fails original count/group/class fitting gates'
            # Feature availability and preprocessing are determined by training folds only.
            names=sorted({n for e in train for n,f in e['features'].items()
                          if ('__' not in n or n.startswith(target+'__')) and f['value'] is not None})
            if not names: reason='No supported training predictors'
            def matrix(records):
                return [[e['features'].get(n,{}).get('value') if e['features'].get(n,{}).get('value') is not None else np.nan for n in names] for e in records]
            predictions=[None]*len(test)
            if reason is None:
                pipeline=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),
                                   ('scaler',StandardScaler()),('model',LogisticRegression(C=1.0,class_weight='balanced',max_iter=2000,random_state=42))])
                pipeline.fit(matrix(train),labels)
                predictions=pipeline.predict(matrix(test)).tolist()
            median=int(np.median(labels)) if labels else None
            folds.append(dict(target=target,held_out=aliases[group],train_n=len(train),train_groups=train_groups,
                              test_n=len(test),status='abstained' if reason else 'predicted',reason=reason,
                              unseen_score_labels=sum(e['labels'][target]['score'] not in labels for e in test)))
            for e,pred in zip(test,predictions):
                cv.append(dict(target=target,group=aliases[group],speaker_id=e['speaker_id'],rating=e['labels'][target]['score'],
                               prediction=pred,baseline=median,abstention=reason))
    assert len(training)==len(cv)==423
    by_target={t:dict(training=metrics([r for r in training if r['target']==t]),
                      retrospective_cv=metrics([r for r in cv if r['target']==t])) for t in targets}
    summary=dict(run_id=RUN,snapshot_hash=snapshot['sha256'],training=metrics(training),retrospective_cv=metrics(cv),
                 analysis_runtime=dict(python=platform.python_version(),numpy=np.__version__,sklearn=importlib.metadata.version('scikit-learn')),
                 by_target=by_target,folds=folds,descriptions={r['key']:r['description'] for r in form},
                 independent_final_test=dict(n=0,status='not measured'),
                 limitations=['Unreviewed source ratings with unavailable opportunity/confidence/evidence',
                              'Retrospective cross-validation after final all-source fit, not a prospective final test',
                              'Five known connected groups; unresolved overlaps can still cause leakage',
                              'P1-P12 role ratings dominate the pooled item-observation metrics',
                              '423 labels are repeated targets on 40 participant-session examples, not 423 people',
                              'Fold models abstain when original fitting gates are not met',
                              'No behavioral, clinical, personality or personalization benefit is validated'])
    (OUT/'analysis-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    for name,rows in [('training-predictions',training),('grouped-cv-predictions',cv)]:
        (OUT/(name+'.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
    with (OUT/'target-metrics.csv').open('w',newline='',encoding='utf-8') as file:
        writer=csv.writer(file);writer.writerow(['target','train_n','train_accuracy','train_MAE','cv_predicted_n','cv_total_n','cv_accuracy','cv_MAE','cv_baseline_MAE'])
        for t in targets:
            a,b=by_target[t]['training'],by_target[t]['retrospective_cv']
            writer.writerow([t,a['n'],a['accuracy'],a['mae'],b['n'],b['total'],b['accuracy'],b['mae'],b.get('baseline_mae')])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titleweight':'bold','axes.spines.top':False,'axes.spines.right':False})
    blue='#315a91';gold='#c18b31';gray='#697581'
    def save(fig,name,note):
        fig.text(.02,.01,note,fontsize=9,color='#444')
        fig.tight_layout(rect=(0,.04,1,.95))
        fig.savefig(OUT/(name+'.png'),dpi=180,facecolor='white')
        fig.savefig(OUT/(name+'.pdf'),facecolor='white');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.8))
    axes[0].bar(['Numeric','N/O','Missing'],[750,1662,20],color=[blue,gray,gold])
    axes[0].set_title('2,432 imported answer records');axes[0].set_ylabel('Answer records')
    for i,v in enumerate([750,1662,20]):axes[0].text(i,v+30,str(v),ha='center')
    axes[1].bar(['Numeric source','Retained for fit','Used by 14 models'],[750,488,423],color=[gray,gold,blue])
    axes[1].set_title('Source-score filtering');axes[1].set_ylabel('Numeric item observations')
    for i,v in enumerate([750,488,423]):axes[1].text(i,v+15,str(v),ha='center')
    save(fig,'01-data-coverage','76 imported forms; 40 retained participant-session examples. Labels are not unique participants.')
    fig,ax=plt.subplots(figsize=(9,7))
    counts=np.array([[by_target[t]['training']['n'],by_target[t]['retrospective_cv']['n'],423*0] for t in targets],dtype=float)
    masked=np.ma.array(counts,mask=np.tile([False,False,True],(len(targets),1)))
    cmap=plt.get_cmap('Blues').copy();cmap.set_bad('#eeeeee')
    im=ax.imshow(masked,cmap=cmap,vmin=0,vmax=max(counts[:,0]),aspect='auto')
    ax.set_xticks(range(3),['Final model\ntraining labels','Retrospective CV\nscored omitted labels','Independent\nfinal test'])
    ax.set_yticks(range(len(targets)),targets)
    for i in range(len(targets)):
        for j in range(3):ax.text(j,i,'N/A' if j==2 else str(int(counts[i,j])),ha='center',va='center',color='white' if j<2 and counts[i,j]>25 else '#222')
    ax.set_title('Training/testing coverage by target');fig.colorbar(im,ax=ax,label='Item observations')
    save(fig,'02-training-testing-coverage','CV folds refit on other known groups. The final deployed models have no independent test set.')
    fig,axes=plt.subplots(1,2,figsize=(14,5.5));x=np.arange(len(targets));width=.35
    for ax,key,ylabel in [(axes[0],'accuracy','Exact source-rating agreement (%)'),(axes[1],'mae','Mean absolute score error (0-4 scale)')]:
        scale=100 if key=='accuracy' else 1
        a=[by_target[t]['training'][key]*scale for t in targets]
        b=[by_target[t]['retrospective_cv'][key]*scale if by_target[t]['retrospective_cv'][key] is not None else np.nan for t in targets]
        ax.bar(x-width/2,a,width,color=blue,label='Training resubstitution')
        ax.bar(x+width/2,b,width,color=gold,label='Retrospective grouped CV')
        ax.set_xticks(x,targets);ax.set_ylabel(ylabel);ax.legend(fontsize=9)
        ax.set_title('Fit versus omitted-group performance')
        if key=='accuracy':ax.set_ylim(0,105)
    save(fig,'03-training-versus-cv','Raw source-score agreement only. CV denominators differ when a fold abstains; see coverage and target-metrics.csv.')
    fig,axes=plt.subplots(1,3,figsize=(14,4.6))
    for ax,key,title in [(axes[0],'training','Training resubstitution'),(axes[1],'retrospective_cv','Retrospective grouped CV')]:
        mat=np.array(summary[key]['confusion']);im=ax.imshow(mat,cmap='Blues',vmin=0)
        ax.set_xticks(range(5));ax.set_yticks(range(5));ax.set_xlabel('Predicted score');ax.set_ylabel('Raw source rating')
        ax.set_title(title+f"\nn={summary[key]['n']} item observations")
        for i in range(5):
            for j in range(5):ax.text(j,i,str(mat[i,j]),ha='center',va='center',color='white' if mat[i,j]>mat.max()/2 else '#222')
    axes[2].axis('off');axes[2].text(.5,.5,'Independent final test\nNOT MEASURED\n\nNo confusion matrix available',ha='center',va='center',fontsize=14,color=gray)
    save(fig,'04-confusion-heatmaps','Pooled across fourteen different targets, with repeated participant labels. Diagonal cells are exact source-score matches.')
    fig,ax=plt.subplots(figsize=(12,5));x=np.arange(len(targets))
    ax.bar(x-width/2,[by_target[t]['retrospective_cv'].get('mae',np.nan) for t in targets],width,color=blue,label='CV model MAE')
    ax.bar(x+width/2,[by_target[t]['retrospective_cv'].get('baseline_mae',np.nan) for t in targets],width,color=gold,label='Fold training-median baseline MAE')
    ax.set_xticks(x,targets);ax.set_ylabel('Mean absolute score error; lower is better');ax.legend();ax.set_title('Does the source-score model beat a simple baseline?')
    save(fig,'05-cv-versus-baseline','Both bars use the same scored omitted labels. Baseline medians use each fold training data only; no significance claim.')
    fig,ax=plt.subplots(figsize=(9,7));dist=np.array([[sum(r['rating']==v and r['target']==t for r in training) for v in range(5)] for t in targets])
    im=ax.imshow(dist,cmap='Blues',aspect='auto',vmin=0);ax.set_xticks(range(5));ax.set_yticks(range(len(targets)),targets)
    ax.set_xlabel('Raw source rating');ax.set_title('Class distribution in the fitted targets');fig.colorbar(im,ax=ax,label='Item observations')
    for i in range(len(targets)):
        for j in range(5):ax.text(j,i,str(dist[i,j]),ha='center',va='center',color='white' if dist[i,j]>dist.max()/2 else '#222')
    save(fig,'06-score-distribution','Unequal class counts affect exact agreement. G/I flag contextual difficulty; P1-P12 describe task performance, so score meanings differ.')
    check=json.loads(Path('.runtime/participant-overlap/prediction-check.json').read_text())
    speaker=check['predictions'][0]['speaker_id']
    example=[r for r in training if r['speaker_id']==speaker]
    example_cv={r['target']:r for r in cv if r['speaker_id']==speaker}
    (OUT/'example-rating-comparison.json').write_text(json.dumps(example,indent=2),encoding='utf-8')
    fig,ax=plt.subplots(figsize=(12,4.7));x=np.arange(len(example))
    ax.plot(x,[r['rating'] for r in example],'o-',color=blue,label='Raw psychologist source rating')
    ax.plot(x,[r['prediction'] for r in example],'s--',color=gold,label='Final-model prediction')
    ax.plot(x,[example_cv[r['target']]['prediction'] if example_cv[r['target']]['prediction'] is not None else np.nan for r in example],'^:',color=gray,label='Refit with this group omitted')
    ax.set_xticks(x,[r['target'] for r in example]);ax.set_yticks(range(5));ax.set_ylim(-.2,4.3)
    ax.set_ylabel('Ordinal item score');ax.set_title('Actual example from the previous API prediction check');ax.legend()
    save(fig,'07-example-report-comparison','Final-model predictions saw this example during training. The omitted-group predictions come from separate fold models; source labels are unreviewed.')
    print(json.dumps({k:summary[k] for k in ['training','retrospective_cv']},indent=2))


if __name__=='__main__':main()
