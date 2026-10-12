"""Frozen-source audit and bounded nested search; never activates a model.

Run with .runtime/venv/Scripts/python.exe -m research.maximum_defensible
--output .runtime/maximum-defensible-2026-10-13. Output must be new.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
import warnings

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.instrument.store import encode
from research.compact_source_models import POLICY as CP, CORE, CONVERSATION, fit, predict
from research.defensible_source_models import fit_candidate, matrix
from research.emergency_audit import align, key, metrics, rating, choose as prior_choose

EXTENDED = CONVERSATION + ('reasoning_ratio', 'hedging_ratio', 'concession_ratio',
                           'experimentation_ratio', 'disagreement_rate', 'question_ratio')
CONFIGS = [
    dict(name='median', kind='reference'), dict(name='mode', kind='reference'),
    *[dict(name=f'pooled-{fs}-logistic-{c}', kind='logistic', features=fs, c=c, weight=None)
      for fs in ('core', 'conversation') for c in (.01, .1, 1.)],
    dict(name='pooled-conversation-logistic-balanced', kind='logistic', features='conversation', c=.1, weight='balanced'),
    dict(name='pooled-extended-logistic-0.1', kind='logistic', features='extended', c=.1, weight=None),
    *[dict(name=f'pooled-conversation-ordinal-{c}', kind='ordinal', features='conversation', c=c, weight=None)
      for c in (.1, 1.)],
]
POLICY = dict(version='maximum-defensible-1', seed=42, configurations=CONFIGS,
    grouping='Leave one known connected recording/person component out; inner leave-one-component-out',
    unit='Existing target rating within participant-session; 423 ratings are not independent observations',
    features=dict(core=CORE, conversation=CONVERSATION, extended=EXTENDED),
    pooling='Share coefficients among P1-P12 only, with penalized target indicators; G/I fit separately',
    selection='Inner equal-group exact agreement; no MAE increase versus both median and mode, no per-class recall loss > .02 versus median for inner classes with support >= 5; minimum gain .025 over best reference; ties declaration order',
    promotion='Only the single nested challenger is eligible. Common-cohort agreement gain >= .025 versus compact, MAE <= compact and mode, class recall loss <= .02 versus compact for scores 1-4, and paired group-bootstrap agreement lower bound > 0 versus compact and mode. Otherwise retain compact as research reference.',
    inference='Completed-session analysis only; no labels, reviewer notes, recording/participant IDs, confidence or annotation-selected windows as predictors',
    calibration='Ordinal probabilities are monotonic projected cumulative logistic estimates, not claimed calibrated; no calibration fit with five small groups',
    status='Retrospective development, not preregistered, not independent final testing',
    bounded=True, automatic_deployment=False)


def dump(out, name, obj):
    (out / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(out, name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (out / name).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list, tuple)) else v for k, v in r.items()})


def filename(e):
    return e['metadata']['versions'].get('local_ingestion', {}).get('source_filename', e['session_id'])


def audit_groups(examples, links, applied):
    """Check full linked-recording transitivity, including unrated bridge seats."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    def union(a, b):
        parent[find(a)] = find(b)
    for l in links['links']:
        union(l['a']['recording'], l['b']['recording'])
    identities = {}
    for plan in applied['plan']:
        for n in plan['nodes']:
            identities[n['session_id'], int(n['code'])] = plan['person_id']
    constraints = defaultdict(set)
    checks = defaultdict(set)
    for e in examples:
        constraints[('recording', find(filename(e)))].add(e['component'])
        constraints[('session', e['session_id'])].add(e['component'])
        code = int(next(iter(e['labels'].values()))['participant_code'])
        person = identities.get((e['session_id'], code))
        e['_known_person'] = person or 'unresolved:' + e['participant_id']
        constraints[('person', e['_known_person'])].add(e['component'])
        hashes = [e['source_hash'], *e['metadata'].get('source_hashes', []),
                  e['metadata']['versions'].get('source_recording_sha256')]
        for h in filter(None, hashes):
            constraints[('hash', h)].add(e['component'])
            checks[h].add(e['session_id'])
    bad = [dict(kind=k[0], identifier=k[1], components=sorted(v)) for k, v in constraints.items() if len(v) > 1]
    if bad:
        raise ValueError(f'Known participant/source leakage across frozen components: {bad}')
    return dict(known_constraint_violations=bad, full_manifest_links=len(links['links']),
        known_person_components=len({e['_known_person'] for e in examples if not e['_known_person'].startswith('unresolved:')}),
        unresolved_participant_sessions=sum(e['_known_person'].startswith('unresolved:') for e in examples),
        shared_hashes_within_components=sum(len(v) > 1 for v in checks.values()),
        independence='Known links respected; unresolved people and source ancestry prevent a participant-independent generalisation claim')


def guarded_choice(diagnostics):
    """Select only from inner predictions, with individual rare-class guards."""
    median, mode = diagnostics['median'], diagnostics['mode']
    ref_best = max(('median', 'mode'), key=lambda n: diagnostics[n]['equal_group_agreement'])
    permitted = []
    for config in CONFIGS:
        n = config['name']; m = diagnostics[n]
        if m['equal_group_mae'] > min(median['equal_group_mae'], mode['equal_group_mae']) + 1e-12:
            continue
        if any(c['support'] >= 5 and m['per_class'][c['score']]['recall'] < c['recall'] - .02
               for c in median['per_class'] if c['recall'] is not None):
            continue
        permitted.append(n)
    if not permitted:
        return ref_best
    chosen = min(permitted, key=lambda n: (-diagnostics[n]['equal_group_agreement'],
                   next(i for i, c in enumerate(CONFIGS) if c['name'] == n)))
    if diagnostics[chosen]['equal_group_agreement'] - diagnostics[ref_best]['equal_group_agreement'] < .025:
        return ref_best
    return chosen


def fit_pooled(train, config):
    professionals = [r for r in train if r['target'].startswith('P')]
    target_names = sorted({r['target'] for r in professionals})
    feature_set = POLICY['features'][config['features']]
    names = [n for n in feature_set if any(r['example']['features'].get(n, {}).get('value') is not None for r in professionals)]
    y = np.asarray([r['rating'] for r in professionals])
    if not names or len(set(y)) < 2:
        return None
    pre = Pipeline([('imputer', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                    ('scale', StandardScaler())])
    x = pre.fit_transform(matrix([r['example'] for r in professionals], names))
    # Target identity is known at inference; participant and recording identity are excluded.
    x = np.column_stack([x, np.asarray([[float(r['target'] == t) for t in target_names] for r in professionals])])
    estimates = []
    for threshold in (range(4) if config['kind'] == 'ordinal' else [None]):
        label = (y > threshold).astype(int) if threshold is not None else y
        if len(set(label)) < 2:
            estimates.append(float(label[0]))
        else:
            est = LogisticRegression(C=config['c'], class_weight=config['weight'], max_iter=2000, random_state=42)
            est.fit(x, label)
            if np.any(est.n_iter_ >= 2000):
                raise RuntimeError('Logistic fit reached iteration limit')
            estimates.append(est)
    return dict(pre=pre, names=names, targets=target_names, estimators=estimates, config=config)


def pooled_predict(model, rows):
    x = model['pre'].transform(matrix([r['example'] for r in rows], model['names']))
    x = np.column_stack([x, np.asarray([[float(r['target'] == t) for t in model['targets']] for r in rows])])
    if model['config']['kind'] == 'logistic':
        est = model['estimators'][0]
        if isinstance(est, float):
            return np.full(len(rows), int(est))
        prob = est.predict_proba(x)
        return np.asarray([est.classes_[np.flatnonzero(p >= max(p)-1e-12)[0]] for p in prob])
    probs = np.asarray([np.full(len(rows), est) if isinstance(est, float) else est.predict_proba(x)[:, 1]
                        for est in model['estimators']])
    return (np.minimum.accumulate(probs, axis=0) > .5).sum(axis=0)


def evaluate_config(train, test, config):
    target_fits = {}
    for t in sorted({r['target'] for r in test}):
        examples = [r['example'] for r in train if r['target'] == t]
        if config['kind'] == 'reference':
            target_fits[t] = fit(examples, t, config['name'])
        elif not t.startswith('P'):
            candidate = ('compact-ordinal-' + str(config['c'])) if config['kind'] == 'ordinal' else (
                'core-logistic-' if config['features'] == 'core' else 'compact-logistic-') + str(config['c']) + ('-balanced' if config['weight'] else '-none')
            target_fits[t] = fit(examples, t, candidate)
    model = fit_pooled(train, config) if config['kind'] != 'reference' else None
    pro_test = [r for r in test if r['target'].startswith('P')]
    pooled = pooled_predict(model, pro_test).tolist() if model is not None else []
    pro_map = {key(r): p for r, p in zip(pro_test, pooled)}
    result = []
    for r in test:
        fallback = False
        if key(r) in pro_map:
            p = pro_map[key(r)]
        else:
            if r['target'] not in target_fits:
                target_fits[r['target']] = fit([z['example'] for z in train if z['target'] == r['target']], r['target'], 'median')
                fallback = True
            m = target_fits[r['target']]; p = predict(m, r['example']); fallback |= m['fallback']
        result.append(dict(target=r['target'], speaker_id=r['speaker_id'], group=r['group'],
                           rating=r['rating'], prediction=int(p), fallback=fallback))
    return result


def paired_bootstrap(a, b, draws=10000):
    """Paired cluster bootstrap, descriptive only with five known groups."""
    bm = {key(r): r for r in b}
    groups = sorted({r['group'] for r in a})
    stats = []
    for g in groups:
        rows = [r for r in a if r['group'] == g]
        stats.append((len(rows), sum((r['prediction'] == r['rating']) - (bm[key(r)]['prediction'] == r['rating']) for r in rows),
                      sum(abs(r['prediction']-r['rating']) - abs(bm[key(r)]['prediction']-r['rating']) for r in rows)))
    z = np.asarray(stats); rng = np.random.default_rng(42)
    samples = z[rng.integers(0, len(groups), size=(draws, len(groups)))].sum(axis=1)
    return dict(groups=len(groups), draws=draws, agreement_delta=sum(z[:, 1])/sum(z[:, 0]),
        agreement_interval=np.quantile(samples[:, 1]/samples[:, 0], [.025, .975]).tolist(),
        mae_delta=sum(z[:, 2])/sum(z[:, 0]), mae_interval=np.quantile(samples[:, 2]/samples[:, 0], [.025, .975]).tolist(),
        limitation='Descriptive and unstable with five known groups; not an independent-test significance claim')


def run(output):
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    dump(out, 'policy-before-results.json', POLICY)
    source_paths = [Path(p) for p in (
        '.runtime/model-hardening/snapshot.json', '.runtime/model-hardening/snapshot-hash.txt',
        '.runtime/model-hardening/predictions.json', '.runtime/model-hardening/candidate-predictions.json',
        '.runtime/results-analysis/grouped-cv-predictions.json',
        '.runtime/emergency-audit-2026-10-12/evaluation_results.json',
        '.runtime/emergency-audit-2026-10-12/paired_predictions.json',
        '.runtime/emergency-audit-2026-10-12/experiment_log.csv',
        '.runtime/participant-overlap/applied.json', 'docs/research/PARTICIPANT_OVERLAP.json',
        '.runtime/participant-overlap/source-form-schema.json')]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    manifest = json.loads(source_paths[0].read_text(encoding='utf-8'))
    canonical = hashlib.sha256(encode(manifest).encode()).hexdigest()
    if canonical != source_paths[1].read_text().strip():
        raise ValueError('Frozen snapshot hash mismatch')
    examples = manifest['examples']; targets = sorted(json.loads(Path('.runtime/model-hardening/models.json').read_text()))
    aliases = {g: f'Group {i+1}' for i, g in enumerate(sorted({e['component'] for e in examples}))}
    group_audit = audit_groups(examples, json.loads(source_paths[9].read_text()), json.loads(source_paths[8].read_text()))
    if len({e['speaker_id'] for e in examples}) != len(examples) or len({e['participant_id'] for e in examples}) != len(examples):
        raise ValueError('Duplicate participant-session or speaker units')
    refs = [dict(target=t, speaker_id=e['speaker_id'], rating=rating(e['labels'][t]['score']), group=aliases[e['component']])
            for e in examples for t in targets if t in e['labels']]
    labels = [e['labels'][t] for e in examples for t in targets if t in e['labels']]
    if len({l['answer_id'] for l in labels}) != len(labels):
        raise ValueError('Duplicate rating answer IDs')
    for e in examples:
        for t in targets:
            if t not in e['labels']: continue
            l = e['labels'][t]
            if any(l[k] != e[k] for k in ('speaker_id', 'participant_id', 'session_id')) or l['target'] != t:
                raise ValueError('Rating lineage mismatch')
            if l['form_id'] != manifest['rubric']['id'] or l['form_hash'] != manifest['rubric']['source_hash']:
                raise ValueError('Rating rubric mismatch')
    original = align(refs, json.loads(source_paths[4].read_text()))
    compact_saved = align(refs, json.loads(source_paths[2].read_text()))
    saved_results = json.loads(source_paths[5].read_text())
    paired = json.loads(source_paths[6].read_text())
    example_alias = {e['speaker_id']: f'Example {i+1:02d}' for i, e in enumerate(examples)}
    reverse = {v:k for k,v in example_alias.items()}
    previous = align(refs, [dict(target=r['target'], speaker_id=reverse[r['example']], group=r['group'],
                    rating=r['reference'], prediction=r['experiment']) for r in paired])
    pm = {(r['target'], reverse[r['example']]): r for r in paired}
    om = {key(r): r for r in original}; cm = {key(r): r for r in compact_saved}
    for r in refs:
        p = pm[key(r)]
        if p['original'] != om[key(r)]['prediction'] or p['compact'] != cm[key(r)]['prediction']:
            raise ValueError('Paired file does not match prediction archive')
        if p['agreement'] != (p['reference'] == p['experiment']) or p['absolute_error'] != abs(p['reference']-p['experiment']):
            raise ValueError('Paired file derived metric mismatch')
    common = {key(r) for r in original if r['prediction'] is not None}
    def common_rows(rows): return [r for r in rows if key(r) in common]
    verified = dict(original=metrics(original), compact_common=metrics(common_rows(compact_saved)),
                    compact_all=metrics(compact_saved), previous_common=metrics(common_rows(previous)), previous_all=metrics(previous))
    def compare_metrics(a, b):
        for name in ('matched_predictions', 'correct', 'exact_agreement', 'mae', 'quadratic_kappa', 'macro_recall_observed'):
            if a[name] is None or b[name] is None:
                assert a[name] == b[name], name
            elif not np.isclose(a[name], b[name], atol=1e-12, rtol=0):
                raise ValueError(f'Saved metric mismatch: {name}')
    compare_metrics(verified['original'], saved_results['baseline']['original'])
    compare_metrics(verified['compact_common'], saved_results['baseline']['compact_common'])
    compare_metrics(verified['previous_common'], saved_results['experiment_common'])
    log = []; cache = {}; folds = []; train_distributions = []; predictions = defaultdict(list)
    predictions['original'] = original
    records = [dict(r, example=next(e for e in examples if e['speaker_id'] == r['speaker_id'])) for r in refs]
    def cached_fit(train, target, candidate, outer, stage):
        k = (target, candidate, tuple(sorted(e['speaker_id'] for e in train)))
        if k in cache: return cache[k]
        start = time.perf_counter()
        receipt = dict(procedure='compact_grid', configuration=candidate, target=target, outer=outer, stage=stage,
                       train_n=len(train), train_groups=len({e['component'] for e in train}),
                       train_ids=[e['speaker_id'] for e in train], seed=42)
        try:
            model = fit(train, target, candidate)
            receipt.update(status='success', fallback=model['fallback'], features=model['features'])
            cache[k] = model
        except Exception as exc:
            receipt.update(status='failed', error=repr(exc))
            raise
        finally:
            receipt['seconds'] = time.perf_counter()-start; log.append(receipt)
            write_csv(out, 'experiment_log.csv', log)
        return model
    # Refit every archived outer prediction, and both nested historical policies.
    for target in targets:
        eligible = [e for e in examples if target in e['labels']]
        for group, alias in aliases.items():
            train = [e for e in eligible if e['component'] != group]
            held = [e for e in eligible if e['component'] == group]
            if not held: continue
            counts = Counter(e['labels'][target]['score'] for e in train)
            mode_score = min(counts, key=lambda k: (-counts[k], k)); median_score = int(np.median([e['labels'][target]['score'] for e in train]))
            train_distributions.append(dict(target=target, outer=alias, train_n=len(train), test_n=len(held),
                train_counts={str(k): counts[k] for k in range(5)}, test_counts={str(k):sum(e['labels'][target]['score']==k for e in held) for k in range(5)},
                training_majority_agreement=counts[mode_score]/len(train), mode_score=mode_score, median_score=median_score,
                train_ids=[e['speaker_id'] for e in train], test_ids=[e['speaker_id'] for e in held]))
            old = fit_candidate(train, target, 'logistic-1-balanced')
            oldrows = [dict(target=target, speaker_id=e['speaker_id'], group=alias, rating=e['labels'][target]['score'],
                            prediction=None if old['fallback'] else predict(old,e)) for e in held]
            predictions['original_refit'].extend(oldrows)
            diagnostics = {}
            for c in CP['candidates']:
                inner_rows = []
                for ig in sorted({e['component'] for e in train}):
                    inner = [e for e in train if e['component'] != ig]; val = [e for e in train if e['component'] == ig]
                    m = cached_fit(inner, target, c, alias, 'inner')
                    inner_rows.extend(dict(group=aliases[ig], rating=e['labels'][target]['score'], prediction=predict(m,e)) for e in val)
                diagnostics[c] = metrics(inner_rows)
                log.append(dict(procedure='compact_grid_evaluation', configuration=c, target=target, outer=alias,
                    stage='inner_validation', status='success', train_n=len(train), test_n=len(inner_rows),
                    train_groups=sorted({aliases[e['component']] for e in train}),
                    validation_scheme='leave one training component out; cached fits carry exact train IDs',
                    metrics=diagnostics[c], seed=42))
                m = cached_fit(train, target, c, alias, 'outer')
                outer_fixed = [dict(target=target, speaker_id=e['speaker_id'], group=alias,
                    rating=e['labels'][target]['score'], prediction=predict(m,e), fallback=m['fallback']) for e in held]
                predictions['fixed:' + c].extend(outer_fixed)
                log.append(dict(procedure='compact_grid_evaluation', configuration=c, target=target, outer=alias,
                    stage='outer_validation', status='success', train_n=len(train), test_n=len(held),
                    train_groups=sorted({aliases[e['component']] for e in train}), test_groups=[alias],
                    metrics=metrics(outer_fixed), seed=42))
            ref = diagnostics['median']
            allowed = [c for c in CP['candidates'] if diagnostics[c]['macro_recall_observed'] >= ref['macro_recall_observed']-.02]
            chosen = min(allowed, key=lambda c:(diagnostics[c]['equal_group_mae'],CP['candidates'].index(c)))
            if ref['equal_group_mae']-diagnostics[chosen]['equal_group_mae'] < .025: chosen = 'median'
            previous_choice = prior_choose(diagnostics)
            for procedure, choice in [('compact', chosen), ('previous_refit', previous_choice)]:
                m = cached_fit(train,target,choice,alias,'outer')
                predictions[procedure].extend(dict(target=target,speaker_id=e['speaker_id'],group=alias,
                    rating=e['labels'][target]['score'],prediction=predict(m,e),fallback=m['fallback'],selected=choice) for e in held)
            folds.append(dict(procedure='compact',target=target,outer=alias,selected=chosen,previous_selected=previous_choice,inner=diagnostics))
        print('Historical policies refitted:', target, flush=True)
    for name, saved in [('original_refit', original), ('compact', compact_saved), ('previous_refit', previous)]:
        actual = align(refs, predictions[name]); saved_map = {key(r):r for r in saved}
        mismatches = [key(r) for r in actual if r['prediction'] != saved_map[key(r)]['prediction']]
        if mismatches: raise ValueError(f'{name} replay mismatch: {mismatches}')
        verified[name+'_mismatches'] = len(mismatches)
    for name in ('median','mode'):
        verified[name+'_common'] = metrics(common_rows(predictions['fixed:'+name]))
        verified[name+'_all'] = metrics(predictions['fixed:'+name])
        compare_metrics(verified[name+'_common'], saved_results['baseline'][name+'_common'])
        for r in predictions['fixed:'+name]:
            if name == 'median' and r['prediction'] != pm[key(r)]['median']:
                raise ValueError('Paired median reference mismatch')
    dump(out,'verified_baseline.json',dict(metrics=verified,group_audit=group_audit,
        counts=dict(examples=len(examples),recordings=len({e['session_id'] for e in examples}),groups=len(aliases),ratings=len(refs),
                    absent_targets=sum(t not in e['labels'] for e in examples for t in targets)),
        unique_rating_ids=len(labels),source_hash=canonical,missing_labels=0,duplicate_rating_ids=0,
        reference_distribution=metrics(original)['reference_distribution'],evaluation='Retrospective grouped development; independent final test n=0'))
    dump(out,'training_fold_distributions.json',train_distributions)
    dump(out,'cohort_and_exclusion_audit.json',dict(
        full_manifest_exclusions=len(manifest['exclusions']),
        exclusion_reasons=dict(Counter(reason for e in manifest['exclusions'] for reason in e.get('reasons',[]))),
        exclusions_status='Original snapshot exclusions, not new experiment exclusions; counts can overlap and refer to all original targets',
        global_observed_majority_all=max(Counter(r['rating'] for r in refs).values())/len(refs),
        global_observed_majority_common=max(Counter(r['rating'] for r in common_rows(refs)).values())/len(common),
        observed_majority_status='Descriptive cohort prevalence, not a training-fold prediction or estimated performance ceiling',
        outer_training_distribution={alias:dict(n=sum(r['group']!=alias for r in refs),
            counts={str(k):sum(r['group']!=alias and r['rating']==k for r in refs) for k in range(5)}) for alias in aliases.values()}))
    # New bounded procedure; one selection across pooled targets per outer fold.
    for group, alias in aliases.items():
        train = [r for r in records if r['group'] != alias]; held = [r for r in records if r['group'] == alias]
        diagnostics = {}; outer_rows = {}
        for config in CONFIGS:
            name = config['name']; inner_rows = []
            for ig in sorted({r['group'] for r in train}):
                inner = [r for r in train if r['group'] != ig]; val = [r for r in train if r['group'] == ig]
                for stage, tr, va in [('inner',inner,val)]:
                    start=time.perf_counter(); receipt=dict(procedure='pooled_grid',configuration=config,outer=alias,inner=ig,stage=stage,
                        train_n=len(tr),test_n=len(va),train_groups=sorted({r['group'] for r in tr}),test_groups=sorted({r['group'] for r in va}),seed=42)
                    try:
                        result=evaluate_config(tr,va,config); inner_rows.extend(result)
                        receipt.update(status='success',metrics=metrics(result),fallback_n=sum(r['fallback'] for r in result))
                    except Exception as exc:
                        receipt.update(status='failed',error=repr(exc)); raise
                    finally:
                        receipt['seconds']=time.perf_counter()-start; log.append(receipt); write_csv(out,'experiment_log.csv',log)
            diagnostics[name]=metrics(inner_rows)
        selected=guarded_choice(diagnostics)
        # Fixed outer configurations are diagnostics only; cannot choose another winner from these.
        for config in CONFIGS:
            start=time.perf_counter(); name=config['name']
            receipt=dict(procedure='pooled_grid',configuration=config,outer=alias,stage='outer',train_n=len(train),test_n=len(held),seed=42,
                         train_groups=sorted({r['group'] for r in train}),test_groups=[alias])
            try:
                outer_rows[name]=evaluate_config(train,held,config)
                predictions['diagnostic:'+name].extend(outer_rows[name])
                receipt.update(status='success',metrics=metrics(outer_rows[name]))
            except Exception as exc:
                receipt.update(status='failed',error=repr(exc)); raise
            finally:
                receipt['seconds']=time.perf_counter()-start;log.append(receipt);write_csv(out,'experiment_log.csv',log)
        predictions['nested_challenger'].extend(dict(r,selected=selected) for r in outer_rows[selected])
        folds.append(dict(procedure='nested_challenger',outer=alias,selected=selected,inner=diagnostics))
        print('New nested outer fold:',alias,selected,flush=True)
    dump(out,'fold_assignments_and_selection.json',folds)
    final_metrics={}; comparisons=[]; confusion={}; prediction_csv=[]; slice_report={}
    for name, rows in predictions.items():
        rows=align(refs,rows)
        for cohort, selected_rows in [('common_402',common_rows(rows)),('all_423',rows)]:
            m=metrics(selected_rows); final_metrics[name,cohort]=m
            comparisons.append(dict(procedure=name,cohort=cohort,total_eligible=m['total_reference_ratings'],evaluated=m['matched_predictions'],
                abstentions=m['abstention_count'],missing_outputs=m['missing_output_count'],coverage=m['coverage'],correct=m['correct'],
                exact_agreement=m['exact_agreement'],mae=m['mae'],balanced_accuracy=m['macro_recall_observed'],macro_f1=m['macro_f1_observed'],
                quadratic_kappa=m['quadratic_kappa'],equal_group_agreement=m['equal_group_agreement'],equal_group_mae=m['equal_group_mae'],
                per_class=m['per_class'],status='development diagnostic only' if name.startswith(('fixed:','diagnostic:')) else 'retrospective grouped development'))
            confusion[name+'|'+cohort]=m['confusion']
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                scored=[r for r in selected_rows if r['prediction'] is not None]
                y=[r['rating'] for r in scored];p=[r['prediction'] for r in scored]
                assert m['confusion']==confusion_matrix(y,p,labels=range(5)).tolist()
                assert np.isclose(m['quadratic_kappa'],cohen_kappa_score(y,p,labels=range(5),weights='quadratic'))
        row_meta={e['speaker_id']:e for e in examples}
        detail={key(r):r for r in predictions[name]}
        for r in rows:
            e=row_meta[r['speaker_id']];l=e['labels'][r['target']];d=detail[key(r)]
            prediction_csv.append(dict(procedure=name,answer_id=l['answer_id'],example=example_alias[r['speaker_id']],
                target=r['target'],speaker_id=r['speaker_id'],participant_id=e['participant_id'],known_person=e['_known_person'],
                recording=filename(e),session_id=e['session_id'],group=r['group'],rating=r['rating'],prediction=r['prediction'],
                common_cohort=key(r) in common,abstained=r['prediction'] is None,selected=d.get('selected'),fallback=d.get('fallback'),
                absolute_error=abs(r['rating']-r['prediction']) if r['prediction'] is not None else None))
        if name in ('original','compact','previous_refit','nested_challenger','fixed:median','fixed:mode'):
            slice_report[name]={}
            for dimension in ('target','recording','example','known_person','group'):
                subsets=defaultdict(list)
                for r in rows:
                    e=row_meta[r['speaker_id']]
                    value=r['target'] if dimension=='target' else r['group'] if dimension=='group' else filename(e) if dimension=='recording' else example_alias[r['speaker_id']] if dimension=='example' else e['_known_person']
                    subsets[value].append(r)
                slice_report[name][dimension]={k:metrics(v) for k,v in subsets.items()}
    write_csv(out,'candidate_comparison.csv',comparisons);write_csv(out,'fold_predictions.csv',prediction_csv)
    dump(out,'confusion_matrices.json',dict(order=list(range(5)),rows='reference',columns='prediction',matrices=confusion))
    dump(out,'slice_metrics.json',slice_report)
    uncertainty={n:paired_bootstrap(common_rows(predictions['nested_challenger']),common_rows(predictions[n])) for n in ('compact','fixed:mode','fixed:median')}
    dump(out,'paired_uncertainty.json',uncertainty)
    challenger=final_metrics['nested_challenger','common_402'];compact=final_metrics['compact','common_402'];mode=final_metrics['fixed:mode','common_402']
    gates=dict(agreement_gain=challenger['exact_agreement']>=compact['exact_agreement']+.025,
               ordinal_error=challenger['mae']<=min(compact['mae'],mode['mae']),
               each_class_recall=all(challenger['per_class'][k]['recall']>=compact['per_class'][k]['recall']-.02 for k in range(1,5)),
               descriptive_paired_lower_bounds=all(uncertainty[n]['agreement_interval'][0]>0 for n in ('compact','fixed:mode')))
    promoted=all(gates.values())
    feature_audit(out,examples,labels,manifest)
    reports(out,final_metrics,gates,promoted,uncertainty,group_audit)
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p)] for p in source_paths):
        raise ValueError('Reference file changed during audit')
    dump(out,'reproducibility.json',dict(source_hashes=hashes,source_preserved=True,policy_sha256=hashlib.sha256((out/'policy-before-results.json').read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),code_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        python=platform.python_version(),numpy=np.__version__,sklearn=__import__('sklearn').__version__,seed=42,
        command=f'.runtime/venv/Scripts/python.exe -m research.maximum_defensible --output {output}',
        log_records=len(log),failed_runs=sum(r['status']=='failed' for r in log),promotion_gates=gates,deployments=0))
    for name in ('original','compact','previous_refit','fixed:median','fixed:mode','nested_challenger'):
        m=final_metrics[name,'common_402'];print(name,m['correct'],m['matched_predictions'],m['exact_agreement'],m['mae'],flush=True)


def feature_audit(out,examples,labels,manifest):
    import pandas as pd
    names=sorted({n for e in examples for n in e['features']})
    data=pd.DataFrame(matrix(examples,names),columns=names)
    rows=[]
    for n in names:
        v=data[n]; between=[]
        for sid in sorted({e['session_id'] for e in examples}):
            indices=[i for i,e in enumerate(examples) if e['session_id']==sid]
            between.append(v.iloc[indices].nunique(dropna=True))
        rows.append(dict(feature=n,present=int(v.notna().sum()),missing=int(v.isna().sum()),unique=int(v.nunique()),
            nonfinite=int(np.isinf(v).sum()),constant_across_available_examples=v.nunique()<=1,
            constant_within_every_recording=all(k<=1 for k in between),
            used_in_new_search=n in EXTENDED,source='completed-session measurement/context',
            status_counts=dict(Counter(e['features'].get(n,{}).get('status','missing') for e in examples))))
    write_csv(out,'feature_audit.csv',rows)
    correlations=data.corr()
    high=[dict(a=a,b=b,correlation=float(correlations.loc[a,b])) for i,a in enumerate(names) for b in names[i+1:]
          if np.isfinite(correlations.loc[a,b]) and abs(correlations.loc[a,b])>=.9]
    dump(out,'feature_correlations.json',high)
    duplicates=[]
    for i,e in enumerate(examples):
        for j,f in enumerate(examples[:i]):
            if np.array_equal(data.iloc[i].to_numpy(),data.iloc[j].to_numpy(),equal_nan=True):
                duplicates.append(dict(a=e['speaker_id'],b=f['speaker_id'],same_component=e['component']==f['component']))
    unmet=Counter(reason for l in labels for reason in l.get('unmet_validation_requirements',[]))
    dump(out,'label_and_feature_audit.json',dict(rating_count=len(labels),strict_eligible=sum(l.get('strict_behavioral_eligibility',False) for l in labels),
        fair_opportunity_recorded=sum(l.get('fair_opportunity') is not None for l in labels),
        observer_confidence_recorded=sum(l.get('observer_confidence') is not None for l in labels),
        independently_reviewed=sum(l.get('review_id') is not None for l in labels),structured_evidence_present=sum(bool(l.get('windows')) for l in labels),
        unmet_validation_requirements=dict(unmet),rubric=manifest['rubric'],identical_feature_vectors=duplicates,
        reviewers=dict(Counter(l['reviewer_id'] for l in labels)),transcript_confidence=data['transcript_confidence'].describe().to_dict(),
        feature_timing='Session aggregates available after processing entire recording; following utterances are future information for real-time use, but not for completed-session analysis.',
        feature_lineage='Frozen snapshot does not contain raw transcripts or all extraction parent records; no exhaustive raw-media or human-ASR validation claim.',
        history='No prior-session history features in snapshot; inferred repeat membership does not establish authorized chronological history. No history experiment executed.'))


def reports(out,m,gates,promoted,uncertainty,group_audit):
    names=['original','compact','previous_refit','fixed:median','fixed:mode','nested_challenger']
    def table(cohort):
        lines=['| Procedure | Correct / scored | Abstentions / eligible | Agreement | MAE | Balanced accuracy | QWK |',
               '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for n in names:
            r=m[n,cohort]
            lines.append(f"| {n} | {r['correct']} / {r['matched_predictions']} | {r['abstention_count']} / {r['total_reference_ratings']} | {100*r['exact_agreement']:.4f}% | {r['mae']:.6f} | {r['macro_recall_observed']:.6f} | {r['quadratic_kappa']:.6f} |")
        return '\n'.join(lines)
    def classes(n):
        r=m[n,'common_402'];lines=['| Score | Support | Predicted | Precision | Recall | F1 |','| --- | ---: | ---: | ---: | ---: | ---: |']
        def fmt(v):return 'undefined' if v is None else f'{v:.6f}'
        for c in r['per_class']:
            lines.append(f"| {c['score']} | {c['support']} | {c['predicted']} | {fmt(c['precision'])} | {fmt(c['recall'])} | {fmt(c['f1'])} |")
        return '\n'.join(lines)
    decision='Retain the compact procedure as the research model reference; do not claim it beats a population reference.' if not promoted else 'The nested challenger passes the predefined development gates; propose review without automatic deployment.'
    diagnostic_names=[n for n,cohort in m if cohort=='common_402' and n.startswith('diagnostic:')]
    diagnostic_best=max(diagnostic_names,key=lambda n:m[n,'common_402']['exact_agreement'])
    d=m[diagnostic_best,'common_402']
    (out/'final_recommendation.md').write_text(f'''# Submission recommendation

{decision} No measured evidence establishes 85% agreement or independent generalisation. The strongest simple agreement reference is the fold training mode, which must be identified as a population prediction rather than personalised communication analysis.

## Reproduced common cohort

{table('common_402')}

The common cohort is fixed by the original 402 non-abstained rating IDs. The original model has 21 abstentions among all 423 ratings. Other procedures predict those 21 additional ratings, often using an explicit training-reference fallback, so the common table omits 21 ratings for paired comparison rather than counting them as new abstentions.

## Full eligible cohort

{table('all_423')}

## Existing compact model, common cohort

{classes('compact')}

## Nested challenger, common cohort

{classes('nested_challenger')}

## Training-mode reference, common cohort

{classes('fixed:mode')}

## Selection and uncertainty

The policy was saved before the new runs, after earlier outer results were already known. It is a disclosed development policy, not preregistration. Inner grouped folds select hyperparameters and the configuration; only the single resulting nested challenger is eligible for promotion. Fixed-configuration outer results are diagnostic and must not be selected as an unbiased winner.

Promotion gates: {json.dumps(gates,sort_keys=True)}. Paired known-group bootstrap differences are in `paired_uncertainty.json`; only five groups are available, so those intervals are descriptive and unstable. No independent held-out test exists. No model was activated, no ratings changed, and hashes of the reference files remained unchanged.

The highest fixed-configuration development agreement was `{diagnostic_best}` at {d['correct']}/{d['matched_predictions']} = {100*d['exact_agreement']:.4f}%, with MAE {d['mae']:.6f}. This is an outer diagnostic, not the nested selected procedure. It predicts score 4 on {d['per_class'][4]['predicted']} of 402 ratings and recalls only {100*d['per_class'][3]['recall']:.2f}% of score 3, compared with {100*m['compact','common_402']['per_class'][3]['recall']:.2f}% for compact. Selecting it after examining these outputs would reuse outer results for tuning and would conceal a rare-class loss, so it is not recommended for promotion.

## Interpretation and required next validation

These are retrospective development estimates using nested known-connected-group cross-validation. They are not training accuracy and are not an independent final test. Known overlap constraints are respected, but {group_audit['unresolved_participant_sessions']} participant-session examples lack resolved person identities, so unseen-participant independence is unproven. A newly chosen split of this already examined material would not create an untouched test set.

Exact agreement counts integer score matches. MAE assumes equal distances between adjacent ordinal scores. QWK uses scores 0-4 with squared distance weights; score 0 has no observed support. Balanced accuracy is mean recall over the observed truth classes only. Undefined precision/recall remain explicit. Pooled targets describe different behaviours, so the pooled kappa is descriptive and per-target results are required. Scores G/I increase with undesirable behaviour, while P1-P12 increase with professional communication quality; the new model shares coefficients only within P1-P12.

The data cannot establish a numerical performance ceiling or inter-rater reliability. Independent blinded re-rating should preserve the original answers, verify speaker identity and opportunity, attach timestamped context, and measure agreement between raters before training against adjudicated labels. Validate future candidates on newly collected, identity-resolved connected groups. A session score does not establish a stable psychological trait.

## Files for submission

Submit this file with `verified_baseline.json`, `candidate_comparison.csv`, `fold_predictions.csv`, `confusion_matrices.json`, `error_analysis.md`, and `experiment_log.csv`. Include `policy-before-results.json`, `training_fold_distributions.json`, `fold_assignments_and_selection.json`, `slice_metrics.json`, `paired_uncertainty.json`, `feature_audit.csv`, `feature_correlations.json`, `label_and_feature_audit.json`, `reproducibility.json`, and `test_results.txt` as the audit supplement. Prediction IDs and linkage material are private research data; use authorised submission access.

Reproduce from the repository with `.runtime/venv/Scripts/python.exe -m research.maximum_defensible --output <new-directory>`. The frozen local inputs listed in `reproducibility.json` are required. Keep the output directory new to preserve earlier results.
''',encoding='utf-8')
    audit=json.loads((out/'label_and_feature_audit.json').read_text())
    (out/'error_analysis.md').write_text(f'''# Error and measurement audit

The fold training-mode reference exceeds the compact model's observed agreement and has lower MAE. This means the current features have not demonstrated additional predictive value over per-target score prevalence. It does not establish a hard 65% ceiling. The 85% aspiration has no empirical support in these runs.

## Integrity and implementation

All 423 unique answer IDs align to target and speaker ID; snapshot IDs, form hashes, scales and groups are checked. Saved metric fields are recalculated, and paired prediction values and derived errors are cross-checked. Original, compact and prior agreement-selection procedures are refitted, not merely copied. All three reproduce their saved outputs exactly. Both fold references are recomputed using training labels only. The audit checks full linked-recording transitivity, including unrated bridge seats, registered hashes, sessions and person links.

No demonstrable model or denominator bug explains the original agreements. Regression tests cover the new integrity checks, inner selection guards and training-only feature preparation. The earlier compact guard used macro recall, which can conceal a lost rare category; the new procedure checks individual class recall on inner classes with at least five observations. That is a disclosed experimental policy change, not a retroactive correction of the original results.

## Label audit

Among the 423 fitted-target ratings, independent reviews: {audit['independently_reviewed']}; recorded fair-opportunity decisions: {audit['fair_opportunity_recorded']}; recorded observer confidence: {audit['observer_confidence_recorded']}; structured evidence windows: {audit['structured_evidence_present']}; strict behavioural eligibility: {audit['strict_eligible']}. Raw notes sometimes contain times, but these do not become validated structured evidence automatically. Original source scores are retained without rewriting. The original snapshot contains other targets excluded by its original eligibility rules; no new outcome-based exclusion is introduced.

The form's score rule and original provenance are preserved in `label_and_feature_audit.json`. Terms such as clear, repeated, sustained, appropriate and affects the exchange require judgement and observation opportunities that differ by role. Clarity, relevance, reasoning and role alignment overlap conceptually. G/I describe problematic behaviour, while P1-P12 describe positive professional behaviour; pooling their numeric values without target conditioning would mix directions. No repeated independent ratings establish inter-rater consistency. Blinded re-rating is needed to test rubric reliability, not to increase agreement by changing labels.

## Feature and context audit

The new search uses only existing observable rates, durations and ratios, with training-only imputation and scaling. It excludes filenames, IDs, annotation notes, reviewer fields, raw recording lengths, transcript confidence and target-specific annotation windows. Target names are valid known prediction inputs. `feature_audit.csv` records missingness, constants, and fields constant within each recording; `feature_correlations.json` reports absolute correlations >= .9. These are descriptive audits, not feature selection against outer labels. Identical full feature vectors are recorded without deleting any observation.

The extractor relies on automatic diarization and transcription. Question punctuation and English lexical rules do not establish listening, intent, persuasion or reasoning, and can miss paraphrases and multilingual contributions. Speaking share, rate and turn duration do not identify communication quality without the task context. Full-session aggregates are available for completed-session analysis, but would leak future information in a real-time claim. The frozen snapshot contains no raw transcripts and this run does not certify word-error rate, speaker attribution, or raw-video context. Observer-selected windows cannot be assumed available at prediction time; none occur in this audit cohort's features. No authorised chronological-history feature exists in the snapshot, so no historical-improvement claim is made.

## Class imbalance, uncertainty and slices

`verified_baseline.json` records every category count; score 0 is unobserved. The compact procedure has weak recall for scores 1-3 and no recall for score 2 on the common cohort. Its pooled agreement largely comes from score 4. Read precision, recall and F1 beside agreement, MAE and kappa in `candidate_comparison.csv`. Every training fold's category counts and modal prediction are in `training_fold_distributions.json`, including target and outer group. `slice_metrics.json` reports target, recording, participant-session example, known person and connected-group results with explicit counts; small slices are descriptive, and unresolved person IDs are not distinct-person evidence.

The comparison fixes the 402-rating common cohort and separately reports all 423 ratings. Model fallbacks and abstentions are explicit in the log and prediction table. A result is not independent merely because rows appear in separate folds: only known connected groups are separable here. Raw parent records and unlisted person links remain unresolved. The paired bootstrap resamples connected groups, not the 423 correlated ratings. Group-specific disagreement patterns cannot establish enduring personal traits.
''',encoding='utf-8')


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    run(parser.parse_args().output)
