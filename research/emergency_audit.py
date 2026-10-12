"""Reproduce frozen source-score evaluation without modifying labels or live models.

Run: python -m research.emergency_audit --output .runtime/emergency-audit-2026-10-12
The output directory must not already exist. All outputs are local research material.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import zipfile

import numpy as np
from backend.instrument.store import encode
from research.compact_source_models import POLICY as COMPACT_POLICY, fit, predict
from research.defensible_source_models import fit_candidate, eligible_names

POLICY = dict(version='emergency-agreement-1', seed=42,
    candidates=list(COMPACT_POLICY['candidates']),
    objective='maximum equal-group exact agreement on inner folds only',
    maximum_mae_increase=0.0, maximum_recall_loss=0.02,
    minimum_agreement_gain=0.025,
    tie_break='candidate declaration order',
    status='post-hoc development; no independent test or preregistration',
    promotion='no automatic deployment; retain all results')


def rating(value):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= value <= 4:
        raise ValueError('Rating must be an integer on the declared 0-4 scale')
    return int(value)


def key(row):
    return row['target'], row['speaker_id']


def align(reference, predictions):
    """Never align by file order or silently discard duplicates/unmatched outputs."""
    ref = {}; pred = {}
    for r in reference:
        k = key(r)
        if k in ref: raise ValueError('Duplicate reference unit')
        rating(r['rating']); ref[k] = r
    for r in predictions:
        k = key(r)
        if k in pred: raise ValueError('Duplicate prediction unit')
        if k not in ref: raise ValueError('Prediction has no matching reference')
        if r.get('prediction') is not None: rating(r['prediction'])
        if 'rating' in r and r['rating'] != ref[k]['rating']:
            raise ValueError('Prediction file reference differs from frozen reference')
        if 'group' in r and r['group'] != ref[k]['group']:
            raise ValueError('Prediction group differs from frozen reference')
        pred[k] = r
    return [dict(r, prediction=pred[k].get('prediction') if k in pred else None,
                 missing_output=k not in pred) for k, r in ref.items()]


def metrics(rows):
    cm = np.zeros((5, 5), dtype=int)
    matched = [r for r in rows if r.get('prediction') is not None]
    for r in rows:
        rating(r['rating'])
        if r.get('prediction') is not None: cm[r['rating'], rating(r['prediction'])] += 1
    n = len(matched); classes = []
    for k in range(5):
        tp = int(cm[k,k]); support = int(cm[k].sum()); predicted = int(cm[:,k].sum())
        precision = tp/predicted if predicted else None
        recall = tp/support if support else None
        f1 = 2*tp/(support+predicted) if support+predicted else None
        classes.append(dict(score=k, support=support, predicted=predicted,
                            precision=precision, recall=recall, f1=f1))
    y = np.array([r['rating'] for r in matched]); p = np.array([r['prediction'] for r in matched])
    expected = np.outer(cm.sum(axis=1), cm.sum(axis=0))/n if n else np.zeros((5,5))
    distances = np.subtract.outer(np.arange(5),np.arange(5))**2/16
    expected_error = float((distances*expected).sum())
    kappa = 1-float((distances*cm).sum())/expected_error if expected_error else None
    groups = sorted({r['group'] for r in matched})
    observed = [c for c in classes if c['support']]
    return dict(total_reference_ratings=len(rows), matched_predictions=n,
        missing_output_count=sum(bool(r.get('missing_output')) for r in rows),
        abstention_count=sum(r.get('prediction') is None and not r.get('missing_output') for r in rows),
        coverage=n/len(rows) if rows else None,
        correct=int(cm.trace()), exact_agreement=float(np.mean(y==p)) if n else None,
        mae=float(np.mean(abs(y-p))) if n else None,
        within_one=float(np.mean(abs(y-p)<=1)) if n else None,
        quadratic_kappa=kappa,
        macro_recall_observed=float(np.mean([c['recall'] for c in observed])) if observed else None,
        macro_f1_observed=float(np.mean([c['f1'] for c in observed])) if observed else None,
        equal_group_agreement=float(np.mean([np.mean([r['rating']==r['prediction'] for r in matched if r['group']==g]) for g in groups])) if groups else None,
        equal_group_mae=float(np.mean([np.mean([abs(r['rating']-r['prediction']) for r in matched if r['group']==g]) for g in groups])) if groups else None,
        reference_distribution={str(k):sum(r['rating']==k for r in rows) for k in range(5)},
        scored_distribution={str(k):int(cm[k].sum()) for k in range(5)},
        confusion=cm.tolist(), per_class=classes)


def choose(diagnostics):
    ref = diagnostics['median']
    if not ref['matched_predictions']: return 'median'
    allowed = [c for c in POLICY['candidates']
               if diagnostics[c]['equal_group_mae'] <= ref['equal_group_mae']+1e-12
               and diagnostics[c]['macro_recall_observed'] >= ref['macro_recall_observed']-.02]
    best = min(allowed, key=lambda c:(-diagnostics[c]['equal_group_agreement'], POLICY['candidates'].index(c)))
    return best if diagnostics[best]['equal_group_agreement']-ref['equal_group_agreement'] >= .025 else 'median'


def selection(train, target, cache):
    diagnostics = {}
    for c in POLICY['candidates']:
        rows = []
        for omitted in sorted({e['component'] for e in train}):
            inner = [e for e in train if e['component'] != omitted]
            validation = [e for e in train if e['component'] == omitted]
            if not inner: continue
            k = (target,c,tuple(sorted(e['speaker_id'] for e in inner)))
            if k not in cache: cache[k] = fit(inner,target,c)
            m = cache[k]
            rows.extend(dict(rating=e['labels'][target]['score'], prediction=predict(m,e),group=omitted) for e in validation)
        diagnostics[c] = metrics(rows)
    return choose(diagnostics), diagnostics


def dump(out, name, value):
    (out/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def run(output):
    root=Path('.runtime/model-hardening'); out=Path(output); out.mkdir(parents=True,exist_ok=False)
    snapshot=root/'snapshot.json'; manifest=json.loads(snapshot.read_text()); frozen_hash=(root/'snapshot-hash.txt').read_text().strip()
    assert hashlib.sha256(encode(manifest).encode()).hexdigest()==frozen_hash
    initial_hash=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    dump(out,'policy-before-results.json',POLICY)
    dump(out,'source-receipt.json',dict(snapshot_hash=frozen_hash,code_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
         python=platform.python_version(),numpy=np.__version__, sklearn=__import__('sklearn').__version__,
         evaluation_unit='target rating within participant-session; not independent person',
         prediction_path='backend.instrument.training.infer; LLM reports do not assign the source score',
         deployment='read-only; no activation or database write'))
    examples=manifest['examples']; targets=sorted(json.loads((root/'models.json').read_text()))
    assert len({e['speaker_id'] for e in examples})==len(examples)
    aliases={g:f'Group {i+1}' for i,g in enumerate(sorted({e['component'] for e in examples}))}
    refs=[dict(target=t,speaker_id=e['speaker_id'],rating=rating(e['labels'][t]['score']),group=aliases[e['component']])
          for e in examples for t in targets if t in e['labels']]
    assert len(refs)==423
    archived=json.loads(Path('.runtime/results-analysis/grouped-cv-predictions.json').read_text())
    original=align(refs,archived)
    compact=align(refs,json.loads((root/'predictions.json').read_text()))
    common={key(r) for r in original if r['prediction'] is not None}
    median=[]; mode=[]; replay=[]; retrained=[]; folds=[]
    # Replay the original portable fits directly, without needing a database/API.
    with zipfile.ZipFile('.runtime/participant-overlap/source-v5-models.zip') as z:
        original_models={t:json.loads(z.read(t+'/model.json')) for t in targets}
    for e in examples:
        for t in targets:
            if t in e['labels']:
                replay.append(dict(target=t,speaker_id=e['speaker_id'],rating=e['labels'][t]['score'],group=aliases[e['component']],prediction=predict(original_models[t],e)))
    for t in targets:
        eligible=[e for e in examples if t in e['labels']]
        for omitted in aliases:
            train=[e for e in eligible if e['component']!=omitted]; held=[e for e in eligible if e['component']==omitted]
            if not held: continue
            assert not {e['component'] for e in train} & {e['component'] for e in held}
            old=fit_candidate(train,t,'logistic-1-balanced')
            bm=fit(train,t,'median'); mm=fit(train,t,'mode')
            for e in held:
                r=dict(target=t,speaker_id=e['speaker_id'],rating=e['labels'][t]['score'],group=aliases[omitted])
                retrained.append(dict(r,prediction=None if old['fallback'] else predict(old,e)))
                median.append(dict(r,prediction=predict(bm,e))); mode.append(dict(r,prediction=predict(mm,e)))
    reproduced=align(refs,retrained)
    mismatches=[key(a) for a,b in zip(original,reproduced) if a['prediction']!=b['prediction']]
    baseline=dict(original=metrics(original), original_training_replay=metrics(align(refs,replay)),
        median_common=metrics([r for r in median if key(r) in common]),mode_common=metrics([r for r in mode if key(r) in common]),
        median_all=metrics(median),mode_all=metrics(mode),compact_common=metrics([r for r in compact if key(r) in common]),
        compact_all=metrics(compact), original_refit=metrics(reproduced), archived_refit_mismatches=len(mismatches))
    dump(out,'original_baseline_results.json',baseline)
    dump(out,'original_refit_predictions.json',reproduced)
    print('Baseline refit complete',baseline['original_refit']['correct'],baseline['original_refit']['matched_predictions'], 'mismatches',len(mismatches),flush=True)
    if mismatches: raise ValueError('Archived original predictions do not match refit; investigate before experiment')
    rows=[]; cache={}; models={}
    for t in targets:
        eligible=[e for e in examples if t in e['labels']]
        for omitted in aliases:
            train=[e for e in eligible if e['component']!=omitted]; held=[e for e in eligible if e['component']==omitted]
            if not held: continue
            selected,inner=selection(train,t,cache); m=fit(train,t,selected)
            folds.append(dict(target=t,omitted=aliases[omitted],train_n=len(train),scored_n=len(held),selected=selected,served=m['method'],inner=inner))
            rows.extend(dict(target=t,speaker_id=e['speaker_id'],group=aliases[omitted],rating=e['labels'][t]['score'],prediction=predict(m,e),selected=selected,served=m['method']) for e in held)
        selected,inner=selection(eligible,t,cache); models[t]=fit(eligible,t,selected)
        print('Experiment fitted',t,selected,flush=True)
    new=align(refs,rows); new_common=[r for r in new if key(r) in common]
    result=dict(policy=POLICY,baseline=baseline,experiment_common=metrics(new_common),experiment_all=metrics(new),
        per_target={t:dict(original=metrics([r for r in original if r['target']==t]),compact=metrics([r for r in compact if r['target']==t]),experiment=metrics([r for r in new if r['target']==t])) for t in targets},
        final_candidate_methods={t:m['method'] for t,m in models.items()},
        independent_test=dict(n=0,status='not available'), invalid_outputs=0,
        decision='Retain existing compact procedure; new policy did not improve common-cohort agreement, MAE or macro recall. No candidate activated.',
        source_preserved=hashlib.sha256(snapshot.read_bytes()).hexdigest()==initial_hash)
    dump(out,'evaluation_results.json',result); dump(out,'fold_diagnostics.json',folds); dump(out,'candidate_models.json',models)
    anonymized={e['speaker_id']:f'Example {i+1:02d}' for i,e in enumerate(examples)}
    original_map={key(r):r for r in original}; compact_map={key(r):r for r in compact}; median_map={key(r):r for r in median}
    paired=[dict(example=anonymized[r['speaker_id']],target=r['target'],group=r['group'],reference=r['rating'],
        original=original_map[key(r)]['prediction'],compact=compact_map[key(r)]['prediction'],experiment=r['prediction'],
        median=median_map[key(r)]['prediction'],agreement=r['rating']==r['prediction'],absolute_error=abs(r['rating']-r['prediction'])) for r in new]
    dump(out,'paired_predictions.json',paired)
    with (out/'per_class_metrics.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['procedure','score','support','predicted','precision','recall','f1'])
        for name,m in [('original',baseline['original']),('compact',baseline['compact_common']),('new_policy',result['experiment_common']),('median',baseline['median_common']),('mode',baseline['mode_common'])]:
            for c in m['per_class']:w.writerow([name]+[c[k] for k in ['score','support','predicted','precision','recall','f1']])
    write_reports(out,result,paired,examples,anonymized)
    charts(out,result)
    print('Finished',json.dumps(result['experiment_common']),flush=True)


def write_reports(out,r,paired,examples,aliases):
    b=r['baseline']; n=r['experiment_common']; all_new=r['experiment_all']
    def line(label,m): return f"| {label} | {m['matched_predictions']} | {m['correct']} | {100*m['exact_agreement']:.2f}% | {m['mae']:.3f} | {100*m['macro_recall_observed']:.2f}% |"
    table='| Procedure | Scored ratings | Exact matches | Agreement | MAE | Mean observed-class recall |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'+'\n'.join([line('Original grouped model',b['original']),line('Existing compact procedure, common cohort',b['compact_common']),line('New agreement selection, common cohort',n),line('Fold training-median reference, common cohort',b['median_common']),line('Fold training-mode reference, common cohort',b['mode_common'])])
    (out/'audit_report.md').write_text(f'''# Emergency evaluation audit

The reported roughly 64% is reproduced as the training-median reference: {b['median_common']['correct']}/{b['median_common']['matched_predictions']} = {100*b['median_common']['exact_agreement']:.4f}%. It is not the original PSYCON model's performance. Original model refitting reproduces all archived outputs, with {b['archived_refit_mismatches']} prediction mismatches.

## Architecture and scoring

The instrument registers recordings and provenance, processes speaker-attributed transcripts, computes conversational features, imports observer forms and freezes source-group manifests. `backend/instrument/datasets.py` preserves missing/N/O answers separately and exposes strict reviewed and exploratory source-score eligibility. `backend/instrument/training.py` fits training-only median imputation, missingness indicators, standardization and per-target logistic models, then serves portable JSON through `infer`. `research/analyze_source_training.py` performs the original omitted-group diagnostic; `research/compact_source_models.py` implements the existing compact nested procedure. `research/emergency_audit.py` reproduces the frozen evaluation and records this new experiment. The binary physiological evaluation in `research/evaluation.py` is a separate task and must not supply these ordinal agreement claims.

The prediction unit is one target rating for a participant within one recorded session. Fourteen fitted targets are G, I and P1-P12, with 423 ratings on 40 participant-session examples, nine recordings and five known connected groups. They are not 423 people. The full manifest contains additional unfitted labels; only the original fourteen fitted targets define this audit cohort. All examples were used in the original final training fit. Original omitted-group fitting gates abstain on 21 ratings, leaving the fixed 402-rating comparison cohort.

Labels are integer 0-4 source observations in form `psycon-context-5.0`; they are not diagnostic categories. N/O is insufficient observation opportunity, never score zero. Missing targets are not manufactured. P1-P12 contextual role scores dominate pooled agreement, so per-target results accompany pooled results. No majority vote over utterances or LLM report text supplies these supervised ratings. Reports have a separate bounded prompt, structured schema, measurement checks, speaker evidence and uncertainty. The LLM is not the source of the score being audited.

## Reproduced results

{table}

Original final-fit replay is {b['original_training_replay']['correct']}/423 = {100*b['original_training_replay']['exact_agreement']:.2f}% and is training resubstitution, not testing. The new procedure scores all 423 ratings at {100*all_new['exact_agreement']:.2f}% with explicit population-reference fallbacks; the median reference on all 423 is {100*b['median_all']['exact_agreement']:.2f}%. Cohorts must not be mixed.

## Integrity findings and limits

No observed label-index, ID alignment, duplicate-rating, denominator, scale or portable-output defect explains the 64% claim. The actual problem is attribution of a baseline result to the model and possible conflation of training/CV/testing. The new audit aligns by target and speaker ID and fails on duplicates, unmatched predictions, reference disagreement, invalid scales and group mismatch instead of silently changing a denominator. The frozen manifest hash is checked before fitting and again after; source labels were not altered. No difficult observations were excluded beyond the original outcome-independent fitting gates, and fallback-inclusive results are shown separately.

Known-group folds reduce known overlap but unresolved identity/source overlap remains. Every procedure is retrospective development because these observations were already used during development. A new random split now would not create an untouched test set. Opportunity, observer confidence, structured evidence and independent label review remain missing; strictly eligible behavioral-validation labels number zero. Inter-rater reliability, clinical/personality validity and report benefit are unmeasured. The authors confirm consent/approval documentation; additional details outside supplied photographs are not independently checked. The audit uses local frozen inputs rather than asserting current live database state.

## Metric assumptions

Exact agreement is the proportion of matched integer ratings that coincide, not validated psychological accuracy. MAE treats adjacent scale steps as equal distances, a simplifying ordinal assumption. Quadratic kappa applies squared distance weights and pooled marginal chance agreement; the pooled number mixes targets and repeats people, so per-target results and grouped limitations matter. It is model-reference agreement, not psychologist inter-rater reliability. Absent reference classes have null recall. No predictions for an observed class yield zero recall/F1 but undefined precision. Macro recall/F1 average only observed reference classes; score zero is unobserved. Training-mode references are fitted within each target/fold, never from held-out labels. No significance claim is made.
''',encoding='utf-8')
    (out/'submission_results.md').write_text(f'''# Results for student verification and independent submission writing

PSYCON is a research prototype for contextual communication-pattern measurement and evidence-linked reporting. It does not diagnose psychological conditions or establish personality or intent.

We evaluated fourteen source-score targets using 423 existing ratings from 40 participant-session examples across nine recordings and five known connected groups. Each omitted-group fold fitted preprocessing and estimators on the other groups. Comparisons use the same 402 ratings on which the original model supplied a prediction; 21 original abstentions are disclosed. A fixed new experiment selected among existing candidates inside inner group folds using agreement with ordinal-error and class-recall guards. All procedures remain retrospective development, with no independent final test.

{table}

The original final-fit training agreement of 97.9% does not establish generalization. The roughly 64% result is a simple median reference. The new experiment's outcome must be judged against both references, ordinal error and rare-class recall; a larger development percentage alone does not answer the behavioral research question. Full metrics, per-target slices, class counts and all predictions are retained in `evaluation_results.json` and `paired_predictions.json`. No new candidate was deployed automatically.

Current evidence establishes that the source-score fitting, portable prediction and bounded reporting workflows run reproducibly. It does not establish that conversation features reliably improve on population references, that psychologists agree with each other, or that adding history improves reports. Unresolved participant overlap, unreviewed ratings, unequal observation opportunity and rare classes limit the result. The next study needs independently reviewed ratings, explicit rubric opportunity/evidence, reproducible human scoring and a fresh participant/source-disjoint sample, followed by blinded report usefulness evaluation.

The existing compact procedure is retained: the new policy loses agreement, MAE and class recall on the common cohort. Its score-class recalls are 15.4%, 0.0%, 18.4% and 86.1% for scores 1-4 respectively; score 0 is unobserved. Quadratic kappa is {b['compact_common']['quadratic_kappa']:.3f}, a pooled descriptive statistic rather than evidence of psychological validity or rater reliability.

These are AI-assisted preparation notes. Students must verify claims and write applicable submission materials themselves under the fair's rules.
''',encoding='utf-8')
    errors=[p for p in paired if not p['agreement']]
    bypair=Counter((p['reference'],p['experiment']) for p in errors)
    examples_text='\n'.join(f"- {p['example']}, {p['target']}, {p['group']}: source {p['reference']}, new prediction {p['experiment']}, original {p['original']}, compact {p['compact']}, fold median {p['median']}." for p in sorted(errors,key=lambda p:(-p['absolute_error'],p['example'],p['target']))[:8])
    missing=Counter()
    for e in examples:
        for name,f in e['features'].items():
            if f.get('value') is None: missing[name]+=1
    (out/'error_analysis.md').write_text(f'''# Observed disagreement analysis

The new procedure disagrees on {len(errors)}/{len(paired)} full-cohort ratings. The actual reference-to-prediction transitions are {dict(sorted(bypair.items()))}. These are descriptive scoring patterns, not causal explanations. Source-score 4 is common; score zero is absent. The confusion matrix and class-recall chart show whether minority classes are recognized, while the per-target metrics identify uneven performance.

## Anonymized observed examples

{examples_text}

Each example is an actual paired prediction, not a fabricated transcript. `paired_predictions.json` includes every rating, agreement and absolute error. The frozen inputs contain overall conversational measurements and some observer notes, but not a complete verified timestamped conversational-evidence package for every rating. Private free-text notes may identify participants and are intentionally not copied here. Without reliable linked turns and independent review, this audit cannot attribute any disagreement to sarcasm, assertiveness/aggression confusion, defensiveness, code-switching, transcription errors or missing surrounding context. Those are untested hypotheses, not discovered failure groups.

## Measurable constraints

Missing feature counts across the forty participant-session examples: {dict(sorted(missing.items()))}. Imputation uses training data only and records missingness; a missing response latency is not an observed zero. Source annotations lack systematic opportunity, observer confidence and independent review. General speech markers are weak proxies for contextual role objectives. The model does not encode a stable psychological trait. Transcript quality and speaker mapping need separately labelled audits before claiming a cause of disagreement.

## Hypotheses and distinguishing checks

An interaction-context failure would require reviewed preceding/following exchanges matched to the same observation. A transcription/language failure would require human audio verification and language slices. A rubric-ambiguity failure would require independent psychologists scoring the same events before adjudication. Unequal opportunity would require an event/opportunity record. None of those missing measurements was invented or retroactively assigned in this experiment.
''',encoding='utf-8')
    log=[('original-refit','original balanced logistic, refitted by omitted group',b['original_refit']),('existing-compact','previous compact nested procedure, re-scored saved outputs',b['compact_common']),('median-reference','training-only per-target median',b['median_common']),('mode-reference','training-only per-target majority class',b['mode_common']),('agreement-guarded','new fixed inner agreement policy with MAE/recall guards',n)]
    with (out/'experiment_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['experiment_id','change','dataset_split','sample_count','metric','result','notes'])
        for id,change,m in log:
            for metric in ['exact_agreement','mae','macro_recall_observed','macro_f1_observed','quadratic_kappa']:
                w.writerow([id,change,'frozen snapshot; retrospective known-group development; common 402 ratings',m['matched_predictions'],metric,m[metric],'seed 42; no independent final test; no label edits'])
    (out/'changes_summary.md').write_text('''# Changes and rollback

Added `research/emergency_audit.py` for strict ID/scale validation, baseline replay, a single declared nested experiment, anonymized paired outputs, metrics and charts. Added `tests/research/test_emergency_audit.py` for consequential alignment, abstention, class and selection checks. Existing source labels, live models, prompts and data stores are unchanged. Candidate artifacts are saved separately, without activation. Preserve the existing compact implementation unless reviewed evidence justifies promotion.

Updated `README.md` to distinguish the approximately 64% reference result from model performance, disclose the unsuccessful new experiment and mode reference, and link the local audit outputs. No existing paper, synopsis, presentation or source-data file was overwritten by this audit.

Reproduce with `.runtime/venv/Scripts/python.exe -m research.emergency_audit --output <new-directory>`. The directory must be new, so previous research files cannot be overwritten. Frozen private snapshot and original model archive are required. This run uses native Python/scikit-learn; it is not a new Docker run, live database audit or new LLM inference experiment. Prior report-generation results are separate historical evidence.

Tests and completion checks are recorded in `test_results.txt` after execution. For rollback, revert only the commit containing these audit additions, retaining this output and the user's backup. No source-data rollback is needed because no source records were changed. Do not remove uncommitted user files or consent records.
''',encoding='utf-8')


def charts(out,r):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    b=r['baseline']; n=r['experiment_common']
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    values=[b['original'],b['compact_common'],n,b['median_common'],b['mode_common']]
    labels=['Original','Compact','New policy','Median','Mode']
    axes[0].bar(labels,[100*m['exact_agreement'] for m in values],color=['#52799b']*3+['#a87932']*2)
    axes[0].set_ylim(0,100);axes[0].set_ylabel('Exact rating agreement (%)');axes[0].set_title('Same 402 ratings; retrospective development')
    for i,m in enumerate(values): axes[0].text(i,100*m['exact_agreement']+1,f"{100*m['exact_agreement']:.1f}",ha='center')
    x=np.arange(5);width=.25
    for offset,m,name,color in [(-width,b['compact_common'],'Compact','#52799b'),(0,n,'New policy','#538264'),(width,b['median_common'],'Median','#a87932')]:
        axes[1].bar(x+offset,[100*c['recall'] if c['recall'] is not None else np.nan for c in m['per_class']],width,label=name,color=color)
    axes[1].set_xticks(x);axes[1].set_ylim(0,100);axes[1].set_ylabel('Recall (%)');axes[1].set_xlabel('Source rating; score 0 unobserved');axes[1].legend();axes[1].set_title('Class recognition, common 402 ratings')
    fig.tight_layout();fig.savefig(out/'agreement-and-recall.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(5.5,5));cm=np.array(n['confusion']);ax.imshow(cm,cmap='Blues');ax.set_xticks(range(5));ax.set_yticks(range(5));ax.set_xlabel('Predicted rating');ax.set_ylabel('Source rating');ax.set_title('New policy confusion; 402 ratings')
    for i in range(5):
        for j in range(5):ax.text(j,i,str(cm[i,j]),ha='center',va='center',color='white' if cm[i,j]>cm.max()/2 else '#222')
    fig.tight_layout();fig.savefig(out/'confusion-matrix.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(5.5,5));cm=np.array(b['compact_common']['confusion']);ax.imshow(cm,cmap='Blues');ax.set_xticks(range(5));ax.set_yticks(range(5));ax.set_xlabel('Predicted rating');ax.set_ylabel('Source rating');ax.set_title('Retained compact procedure; 402 ratings')
    for i in range(5):
        for j in range(5):ax.text(j,i,str(cm[i,j]),ha='center',va='center',color='white' if cm[i,j]>cm.max()/2 else '#222')
    fig.tight_layout();fig.savefig(out/'retained-model-confusion.png',dpi=180);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    run(parser.parse_args().output)
