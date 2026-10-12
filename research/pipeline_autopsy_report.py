"""Produce aggregate submission documents from an executed, immutable autopsy."""
from pathlib import Path
from collections import Counter
import argparse, csv, hashlib, json, shutil, zipfile
from research.pipeline_autopsy import FAMILIES, ALL, expanded
from research.compact_source_models import CONVERSATION
from research.maximum_defensible import write_csv, dump


STAGES = [
    ('Load and normalize', 'Uploaded original media', '16 kHz mono PCM16, original timeline and diagnostics', 'backend/instrument/audio.py: preprocess; service.py', 'AV first audio stream, 1-192 kHz, 1-8 channels, 1s-4h; complete decode and resampler flush; no denoising or silence removal', 'Reject invalid/nonfinite/too short/too long input; downmix can obscure simultaneous voices. Nine retained WAVs match container audio duration within 15 ms, all mono16k. This rules out material duration truncation in these files, not word loss or channel cancellation.'),
    ('Diarize', 'Normalized waveform', 'Anonymous speaker intervals', 'backend/instrument/audio.py: diarize', 'Pyannote Community-1 pinned revision; 1-12 speakers; merge same-speaker gaps <=.3s', 'Merged gaps count toward turn duration. Overlap and speaker swaps can contaminate every speaker feature. No independently annotated speaker timeline is available, so diarization error rate cannot be measured.'),
    ('Transcribe and timestamp', 'Normalized waveform', 'Whisper segments and word timestamps', 'backend/instrument/audio.py: transcribe', 'Pinned large-v3; beam5; VAD; previous-text conditioning off; forced English; CPU int8 or CUDA int8_float16', 'Configuration advertises language but call forces en. Whisper timestamps are not independent forced alignment. Confidence is model probability, not calibrated word accuracy. No corrected transcripts or language labels support a WER or language-policy improvement claim.'),
    ('Attribute and identify', 'Words plus diarized intervals', 'Speakers, turns, attributed/ambiguous utterances, words', 'backend/instrument/audio.py: attribute; service.py retry; datasets.py', 'Word overlap winner >=.8, runner-up <.1; stable saved speaker IDs on retry; seat mappings and known links supplied separately', 'Anonymous cluster labels are not people. Ambiguous words remain unattributed. Retry rejects changed retained evidence. Twenty-one participant-session identities remain unresolved, so grouping is known-link protection rather than proven complete participant independence.'),
    ('Segment and gate', 'Attributed word stream', 'Timestamped utterances; completed/withheld profile stage', 'backend/instrument/audio.py; service.py STAGES', 'Speaker changes, punctuation, >1s gaps; mean transcript confidence >=.55; attributed fraction >=.6; clipping <=5%', 'Punctuation affects utterance denominators; no reviewed topic/phase boundaries. Quality gates measure operational coverage, not rating agreement. Frozen features do not expose all historical gate decisions, and canonical stage export failed.'),
    ('Measure timing and participation', 'Speaker intervals and utterances', '12 participation/turn/timing measurements', 'backend/instrument/features.py: extract, time_metrics', 'Union speech time, exclusive speaking share, turn durations, latency and overlap candidate counts; chronological sort added in schema1.0.2', 'Database retries return unordered turns. Before the correction, permuting three valid turns changed one-second latency to missing; all six permutations now agree. Frozen features were not rewritten, so accuracy impact remains unmeasured.'),
    ('Measure linguistic context', 'Attributed text, session metadata', '13 rule indicators, five context flags, confidence', 'backend/instrument/features.py PATTERNS; datasets.py', 'English lexical/punctuation markers; exposure-normalized event rates; attributed-utterance ratios', 'Lexical matches do not establish intention, emotion or behavior. WPM has attributed words over all diarized speech, so failed attribution biases it downward. Context category flags are constant here and cannot discriminate recordings; confidence varies but does not certify truth.'),
    ('Freeze and align labels', 'Versioned reference answers, mappings and features', '40 examples, 423 target ratings', 'backend/instrument/datasets.py; research/emergency_audit.py: align; maximum_defensible.py: audit_groups', 'Exact target + speaker-ID join; answer IDs retained; integer0-4 scale; five connected components include linked recordings', 'No duplicate or unmatched reference units in the verified snapshot; absent answers remain absent. G/I negative behavior and P1-P12 positive behavior are separate targets, with original numeric direction retained. No score0 references, and no independently reviewed/opportunity-eligible labels.'),
    ('Split and preprocess', 'Frozen examples and connected groups', 'Train/inner-validation/test matrices', 'research/compact_source_models.py; pipeline_autopsy.py', 'Outer leave-one-connected-group-out; inner grouped folds; train-only median imputation plus indicators and standardization', 'No same known component crosses a fold. Missingness is retained. Unknown participant links may remain; groups are small and unequal. Train-only redundancy selection and quantile/log corrections were tested without touching outer labels.'),
    ('Fit and predict', 'Training matrices and per-target ratings', 'One ordinal category per target or explicit reference fallback', 'backend/instrument/training.py: infer; compact_source_models.py; pipeline_autopsy.py', 'Regularized logistic, ridge, previous bounded ordinal/tree experiments; min12 examples, three groups, two classes; median fallback', 'Tiny targets often use a population reference rather than personalized prediction. Logistic uses category maximum probability; ridge rounds floor(x+.5), clipped0-4; prior ordinal model uses monotone exceedance probabilities and lower median. No fourteen-target psychological total is computed.'),
    ('Evaluate and report', 'Predictions joined to untouched ratings', 'Agreement, ordinal error, class metrics, evidence-linked report', 'research/emergency_audit.py: metrics; backend/instrument/service.py; local_llm.py; measurement_report.py', 'Common402 IDs fixed by original non-abstentions; all423 separately; LLM narrative downstream of supervised predictions', 'Report prose, archetype matches and historical narrative do not feed these prediction experiments. Completed-session features cannot support live-prefix forecasts. Earlier personal history has no validated incremental prediction experiment here. Narrative grounding/usefulness needs independent review.')
]


def num(v, pct=False):
    return 'undefined' if v is None else f'{v*100:.2f}%' if pct else f'{v:.3f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] + ['| '+' | '.join(map(str,r))+' |' for r in rows])


def build(output, public=None):
    out=Path(output); decision=json.loads((out/'decision.json').read_text()); slices=json.loads((out/'slices.json').read_text())
    comparisons=list(csv.DictReader((out/'ablation_comparison.csv').open(encoding='utf-8')))
    metrics={(r['procedure'],r['cohort']):{k:json.loads(v) for k,v in r.items() if k not in ('procedure','cohort','quadratic_kappa_meaning')} for r in comparisons}
    snapshot=json.loads(Path('.runtime/model-hardening/snapshot.json').read_text()); examples=snapshot['examples']; meta={e['speaker_id']:e for e in examples}
    folds=json.loads((out/'folds.json').read_text()); logs=list(csv.DictReader((out/'experiment_log.csv').open(encoding='utf-8')))
    quality=json.loads((out/'audio_quality.json').read_text()); receipt=json.loads((out/'receipt.json').read_text())
    receipt['code_files_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path('research/pipeline_autopsy.py'),Path('backend/instrument/features.py'),Path('research/emergency_audit.py'),Path('research/compact_source_models.py'),Path('research/maximum_defensible.py')]}
    dump(out,'receipt.json',receipt)
    history=[dict(directory='.runtime/pipeline-autopsy-2026-10-13',status='failed before complete results',reason='Ridge n_iter_=None guard; no successful metric claimed'),
        dict(directory='.runtime/pipeline-autopsy-2026-10-13-v2',status='superseded quality metadata',reason='Legacy-only audio path; eight WAVs wrongly unavailable; model predictions reproduced by corrected run'),
        dict(directory='.runtime/pipeline-autopsy-2026-10-13-final',status='completed; superseded export',reason='Correct quality metadata; final submission adds all diagnostic predictions, participant slices, zero-score slices and preserved input hashes; no model or policy change'),
        dict(directory=str(out),status='complete',reason='Final reproducible model run and submission export')]
    dump(out,'run_history.json',history)
    if (out/'test_results.xml').exists():
        import xml.etree.ElementTree as ET
        suite=ET.parse(out/'test_results.xml').getroot().find('testsuite')
        dump(out,'test_summary.json',dict(tests=int(suite.get('tests')),failures=int(suite.get('failures')),errors=int(suite.get('errors')),skipped=int(suite.get('skipped')),
            integration_status='Dedicated PostgreSQL integration fixtures unavailable: PSYCON_TEST_DATABASE_URL unset; broader attempt produced setup errors, not passed tests',
            regression_evidence='Temporal permutation test failed before fix and passed after; closed-form Ridge and train-only transformation checks pass'))
    oldpath=Path('.runtime/maximum-defensible-2026-10-13-final/verified_baseline.json')
    old=json.loads(oldpath.read_text()) if oldpath.exists() else dict(status='Previous independent reproduction artifact unavailable in this environment')
    dump(out,'verified_baseline.json',dict(previous_audit=old,autopsy=json.loads((out/'baseline_before.json').read_text()),preserved_hashes=json.loads((out/'reference_hashes.json').read_text())))
    shutil.copyfile(out/'ablation_comparison.csv',out/'candidate_comparison.csv');shutil.copyfile(out/'predictions.csv',out/'fold_predictions.csv')
    training=[]
    for f in folds:
        counts=Counter(meta[s]['labels'][f['target']]['score'] for s in f['train_ids'])
        mode=min(counts,key=lambda v:(-counts[v],v))
        training.append(dict(target=f['target'],outer=f['outer'],training_examples=sum(counts.values()),selected=f['selected'],
            mode=mode,majority_training_agreement=counts[mode]/sum(counts.values()),**{'score_'+str(k):counts[k] for k in range(5)}))
    write_csv(out,'training_fold_distribution.csv',training)
    breakdown=[]
    for procedure, dimensions in slices.items():
        for dimension, values in dimensions.items():
            for value,m in values.items():breakdown.append(dict(procedure=procedure,dimension=dimension,slice=value,**m))
    write_csv(out,'slice_metrics.csv',breakdown)
    common='common_402'; ref=metrics['compact',common];nested=metrics['nested',common]
    baseline=table(['Procedure','Cohort / scored / abstentions','Correct','Agreement','MAE','Balanced accuracy','QWK'],
        [[n,f'{m["total_reference_ratings"]} / {m["matched_predictions"]} / {m["abstention_count"]}',m['correct'],num(m['exact_agreement'],True),num(m['mae']),num(m['macro_recall_observed'],True),num(m['quadratic_kappa'])]
         for cohort in (common,'all_423') for n in ('original','compact','median','mode','nested') for m in [metrics[n,cohort]]])
    ablations=table(['Fixed diagnostic','Correct / 402','Agreement','MAE','Balanced accuracy','Agreement change vs full same estimator','MAE change vs full same estimator'],
        [[n,m['correct'],num(m['exact_agreement'],True),num(m['mae']),num(m['macro_recall_observed'],True),num(m['exact_agreement']-metrics['full|'+n.split('|')[1],common]['exact_agreement'],True),num(m['mae']-metrics['full|'+n.split('|')[1],common]['mae'])]
         for n in [k[0] for k in metrics if k[1]==common and '|' in k[0]] for m in [metrics[n,common]]])
    pertarget=table(['Target','Compact correct / n','Compact MAE','Nested correct / n','Nested MAE','Median correct','Mode correct'],
        [[t,f'{m["correct"]}/{m["matched_predictions"]}',num(m['mae']),f'{nn["correct"]}/{nn["matched_predictions"]}',num(nn['mae']),slices['median'][common+'|target'][t]['correct'],slices['mode'][common+'|target'][t]['correct']]
         for t,m in slices['compact'][common+'|target'].items() for nn in [slices['nested'][common+'|target'][t]]])
    classes=table(['Procedure','Score','Truth n','Predicted n','Precision','Recall','F1'],
        [[n,c['score'],c['support'],c['predicted'],num(c['precision'],True),num(c['recall'],True),num(c['f1'])] for n in ('compact','nested','mode') for c in metrics[n,common]['per_class']])
    components=[]
    for family,names in FAMILIES.items():
        single=metrics[family+'|logistic_0.1',common];drop=metrics['without_'+family+'|logistic_0.1',common];full=metrics['full|logistic_0.1',common]
        for name in names:
            values=[e['features'].get(name,{}).get('value') for e in examples];available=[v for v in values if v is not None]
            constant=len(set(available))<=1
            components.append(dict(feature=name,family=family,available_examples=len(available),missing_examples=len(values)-len(available),
                unique_values=len(set(available)),in_compact=name in CONVERSATION,
                decision='constant; excluded from compact candidate' if constant else 'retain in compact reference; contribution uncertain' if name in CONVERSATION else 'exclude from compact candidate; incremental benefit inconclusive',
                family_standalone_agreement=single['exact_agreement'],family_drop_agreement_delta=drop['exact_agreement']-full['exact_agreement'],family_drop_mae_delta=drop['mae']-full['mae'],
                justification='Constant observed values cannot discriminate examples; future context populations untested.' if constant else 'Family-level exploratory contrast, not an isolated causal contribution of this individual feature. No independently reliable removal claim.'))
    write_csv(out,'component_decisions.csv',components)
    maptext=table(['Stage','Input','Output','Files','Configuration','Failure and consequence'],STAGES)
    diag=max((m['exact_agreement'],n,m) for (n,c),m in metrics.items() if c==common and n not in ('original','compact','nested','median','mode'))
    worst=sorted(slices['compact'][common+'|target'].items(),key=lambda z:-z[1]['mae'])
    report=f'''# PSYCON pipeline autopsy, 13 October 2026

Retain the compact procedure as the research reference and reject promotion of the new challenger. The inner-selected procedure changes 250/402 correct to 251/402, and MAE 0.490 to 0.488, but remains below the training-mode reference, worsens one group's MAE, and does not meet the predefined gain criterion. Neither procedure supports independent generalization or an 85% claim.

## Ordered pipeline map

```mermaid
flowchart TD
 A[Original audio] --> B[Mono 16 kHz, unchanged timeline]
 B --> C[Anonymous diarized intervals]
 B --> D[Whisper words and timestamps]
 C --> E[Word attribution and participant mapping]
 D --> E
 E --> F[Utterances and quality gates]
 F --> G[Observable features and evidence]
 G --> H[Training-only preprocessing]
 H --> I[Per-target supervised model or reference fallback]
 I --> J[Ordinal prediction joined to reference answer ID]
 J --> K[Grouped metrics and evidence-linked report]
```

{maptext}

## Verified baseline and same-cohort comparison

{baseline}

The original has 423 references and 402 predictions, with 21 explicit abstentions. Its all-reference row still calculates agreement and MAE on 402 predictions; 230/423 is not substituted as prediction accuracy. Every other procedure predicts all 423, with training-reference fallbacks counted as predictions. All423 is the full source-score cohort, not a strictly reviewed behavioral cohort; strict behavioral eligibility is zero and cannot be evaluated. Common402 excludes exactly the original abstention IDs for paired comparison. No new exclusions were selected. Counts for all423 scores0-4 are 0,24,24,109,266; common402 counts are 0,13,20,103,266. Raw reference answers, saved original predictions and compact artifacts retain their hashes.

Each rating is keyed by target and participant-session speaker ID, with answer ID and session ID exported in private fold_predictions.csv. The preceding audit refitted original and compact procedures with zero saved-prediction differences. Duplicate keys, invalid scales, unmatched predictions and differing saved truth/group values fail alignment. The overlap audit protects all known participant and recording links, including shared source ancestry; unresolved identities prevent a claim of complete participant independence. No numeric labels were inverted or rewritten. G/I and P1-P12 describe different directions of behavior and are modeled separately.

## Ranked bottlenecks

1. **Class imbalance and weak separation.** Compact predicts score 4 on {ref['per_class'][4]['predicted']}/402, recalls none of 20 score2 examples, and has {num(ref['macro_recall_observed'],True)} balanced accuracy. Training mode reaches 264/402 correct without behavioral features. The apparent agreement primarily reflects score prevalence; actual behavioral signal has not reliably exceeded it.
2. **Sparse target data and group shifts.** G has three and I two common-cohort predictions, so their errors cannot establish a reliable feature ranking. The largest compact ordinal errors include {', '.join(t+' '+num(m['mae']) for t,m in worst[:4])}. Forty participant-session examples across five linked groups provide much less independent information than 423 ratings suggest. training_fold_distribution.csv exposes every category in every outer training fold. Nested selection chose a median reference in {Counter(f['selected'] for f in folds)['median']}/{len(folds)} target-fold decisions.
3. **Unmeasured reference reliability and opportunity.** Zero fitted answers have independently reviewed labels, structured observation windows, fair-opportunity decisions or individual observer-confidence fields. There is no repeated-rater experiment from which to estimate label noise or a numerical prediction ceiling. Unequal speaking opportunity and rubric direction are plausible explanations, not proven mislabeled records. Obtain independent blinded re-rating with behavior-specific evidence windows; retain the current answers unchanged.
4. **Unverified upstream speech and identity accuracy.** Audio duration and clipping pass this audit, but no corrected transcript, diarization truth or word-speaker annotation supports a measured stage error budget. English-only transcription and lexical rules may miss multilingual or implicit behavior. Attributed-word denominators can magnify attribution loss. These remain hypotheses requiring annotation, rather than reasons to remove recordings or claim a correction improves agreement.
5. **A demonstrated temporal ordering defect.** Unordered retry queries in service.py feed extract(), which interpreted adjacent database rows as adjacent turns. A three-turn example should yield one-second latency for both speakers; a permutation yielded missing values before the correction. Chronological sorting fixes all six permutations without changing sorted inputs. Schema1.0.2 marks this fix for newly computed features. Existing cached features and frozen models remain untouched; before/after historical accuracy is identical because this experiment uses the frozen snapshot. Its numerical impact on regenerated real features is inconclusive until the canonical stage records are accessible.

## Controlled ablations and correction attempts

There are {receipt['configurations']} declared configurations: each family alone, full 31, compact 8, core 4, every family removed, training-only redundancy/missingness cleanup, log1p correction and 5th/95th-percentile winsorization, each with logistic C0.1/C1 or ridge alpha10; plus train-fold-balanced logistic and per-target median/mode. Original bounded ordinal and shallow-tree comparisons remain in the previous audit. All share the frozen five outer components. Every feature selection, median, missingness indicator, scale, class weight and quantile is fitted on training data only. Inner leave-one-group-out folds select per target by equal-group MAE, subject to class-recall guard and minimum 0.025 MAE gain over median; declaration order breaks ties. No outer metrics change this policy.

{ablations}

Each row is a fixed exploratory diagnostic, not a candidate selected by these outer results. Compare family removal against full with the same estimator; low standalone performance alone does not justify a cut. The highest diagnostic is {diag[1]}, {diag[2]['correct']}/402 = {num(diag[0],True)}, MAE {num(diag[2]['mae'])}; it predicts score4 on {diag[2]["per_class"][4]["predicted"]}/402 and recalls score2 at {num(diag[2]["per_class"][2]["recall"],True)}. It was not promoted or rerun with favorable tuning. All experiments follow prior outer-result inspection, so the nested estimates also remain retrospective exploratory development.

The attempts did not produce a replacement that passed all gates. Agreement, MAE versus compact/mode, group consistency and paired agreement gates failed; the class-recall gate passed. Group-MAE regression occurred in {', '.join(decision['group_mae_regressions'])}. The nested-minus-mode descriptive agreement interval is {num(decision['uncertainty_vs_mode']['agreement_interval'][0],True)} to {num(decision['uncertainty_vs_mode']['agreement_interval'][1],True)}. Five-group resampling is unstable and is not an independent validation significance test.

The first execution failed on a report-side convergence check because closed-form Ridge exposes n_iter_=None. The check now tests for a numeric iteration count, and its regression test fits Ridge successfully. No successful metric was claimed for that failed run. A second audit initially looked only in the legacy normalized-audio layout; correction resolves current derived/normalized.wav before the historical direct layout. The corrected complete run reproduces the previous model predictions. Historical failed and superseded runs remain preserved, and run_history.json records their status. Neither correction changes labels or model training policy.

## Per-target and per-class behavior

{pertarget}

{classes}

All target, truth class, recording, participant-session, known group, speech quantity, duration, clipping, silence, transcript confidence and prediction-direction slices are in slices.json and slice_metrics.csv. Each contains n, correct, agreement, MAE, balanced accuracy, QWK, per-class precision/recall/F1 and a 5x5 confusion matrix. Participant-session slices are not estimates of stable traits or deduplicated known people. Quality/speech bins were declared before comparisons and are descriptive, with confounding by recording and group. There is no causal attribution of downstream error to any stage. Stage-specific WER, speaker error and attribution precision remain unavailable. Feature-family metrics come from controlled end-to-end ablations, not human annotations of that stage.

Score 0 has zero references. Its recall is explicitly undefined; when no predictions exist, its precision and F1 are undefined too. Undefined denominators remain null in machine-readable results. Balanced accuracy averages only observed truth classes, so class-conditional slices reduce to that class's recall. MAE assumes equal adjacent steps on the declared 0-4 ordinal scale; QWK uses squared distance divided by 16 and is undefined when expected disagreement is zero. Pooling distinct targets is descriptive, not a validated single psychological construct.

Compact has {ref['overpredictions']} overpredictions and {ref['underpredictions']} underpredictions on common402. Nested has {nested['overpredictions']} and {nested['underpredictions']}. Confusion rows are reference 0-4, columns prediction 0-4. Inspect individual failed answer IDs in the private predictions rather than treating every disagreement as a label defect.

## Retained, excluded and unresolved components

The retained compact candidate uses {', '.join(CONVERSATION)}. Its existing target-specific inner selection, missing-value indicators, train-only imputation/scaling, sparse-data fallback and ordinal output rules remain unchanged. This is a reproducibility reference, not an endorsed personalized assessment. No current model component or raw extraction family was deleted or deployed by this audit.

The other {len(ALL)-len(CONVERSATION)} predictors remain excluded from the compact candidate. component_decisions.csv lists all 31 individually, their availability, family contrasts and decision evidence. Constant context indicators cannot separate these samples and need no correction to earn a place here; broader contexts may change that. Variable excluded predictors are inconclusive, because removing a family sometimes improves a fixed diagnostic but does not establish reliable incremental loss across this small, previously inspected cohort. Cleanup/log/winsorization and class weighting remain unpromoted alternatives. No feature is called useless solely because its standalone agreement is low.

The chronological correction is retained as a deterministic extraction correctness fix, with all existing frozen results preserved. It is isolated from model replacement because no real-data performance gain has been measured. No language-policy, diarization-model, punctuation, attribution-threshold or aggregation change is deployed without stage truth and a valid comparison. Recording identity, speaker IDs, reference labels, observer notes, target windows, derived target values and future-session information are excluded as predictive inputs. Completed-session observations cannot justify stable psychological traits.

## Reproduction and submission files

```powershell
.runtime/venv/Scripts/python.exe -m research.pipeline_autopsy --output .runtime/pipeline-autopsy-reproduction
.runtime/venv/Scripts/python.exe -m research.pipeline_autopsy_report --output .runtime/pipeline-autopsy-reproduction
.runtime/venv/Scripts/python.exe -m pytest tests/research tests/validation/test_stages.py tests/validation/test_evidence.py tests/validation/test_communication_semantics.py -q
```

Use a new output directory and the authorized private .runtime/model-hardening snapshot/models/predictions, original results-analysis predictions, overlap artifacts and audio media. Model evaluation runs on the frozen snapshot even when canonical PostgreSQL is unavailable. Full stage inspection and integration tests require the canonical/test database respectively; no SQLite mirror substitutes for them. Source hash, code hash, runtime, configuration, seed, train/test IDs, fold selection and per-fold metrics are retained in receipt.json, reference_hashes.json, policy-before-results.json, folds.json and experiment_log.csv. There are {receipt['fit_log_records']} fit/evaluation log records. The focused suite passed 101 tests with one ffmpeg-dependent skip; test_results.xml and test_summary.json retain the executed evidence. Database-backed integration fixtures were unavailable, and their setup errors are not counted as passed tests. No automatic model activation or live-database write occurred.

The submission directory contains verified_baseline.json, candidate_comparison.csv, fold_predictions.csv, confusion_matrices.json, error_analysis.md, experiment_log.csv and final_recommendation.md, plus full_pipeline_report.md, slice_metrics.csv, slices.json, component_decisions.csv, training_fold_distribution.csv, audio_quality.json, canonical_stage_audit.json and provenance files. Individual predictions and identity-bearing materials remain private. Aggregate documentation is published separately. Reproduction is conditional on those authorized private inputs, not possible from the public repository alone.

Retain the compact research reference, reject the new replacement, and simplify claims to evidence-linked contextual measurement. Resolve identities, independently annotate speech/attribution and re-rate fair-opportunity windows before collecting an independent final test. The current data do not support a numerical high-accuracy ceiling or reliable personalized deployment.
'''
    (out/'full_pipeline_report.md').write_text(report,encoding='utf-8');(out/'error_analysis.md').write_text(report,encoding='utf-8')
    (out/'final_recommendation.md').write_text(report.split('## Ordered pipeline map')[0]+'\nRetained features: '+', '.join(CONVERSATION)+'.\n\nNo current model components removed. Chronological extraction correction affects future newly computed features only. See full_pipeline_report.md and component_decisions.csv for exact evidence and unresolved decisions.\n',encoding='utf-8')
    if public:
        pub=Path(public);pub.mkdir(parents=True,exist_ok=True)
        for name in ('candidate_comparison.csv','confusion_matrices.json','component_decisions.csv','training_fold_distribution.csv','decision.json','receipt.json','policy-before-results.json'):
            shutil.copyfile(out/name,pub/name)
        # Shared report describes source files, but contains no individual IDs or answers.
        shutil.copyfile(out/'full_pipeline_report.md',pub/'full_pipeline_report.md')
        safe=[r for r in breakdown if r['dimension'].split('|')[1] in ('target','score','group','direction','speech_quantity','duration','audio_clipping','silence','transcript_confidence')]
        write_csv(pub,'slice_metrics.csv',safe)
        dump(pub,'summary.json',dict(nested_common=nested,nested_all=metrics['nested','all_423'],compact_common=ref,mode_common=metrics['mode',common],configurations=receipt['configurations'],promote=False,private_stage_status='canonical unavailable',stage_accuracy_measured=False))
    dump(out,'artifact_hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='artifact_hashes.json'})
    with zipfile.ZipFile(out.parent/(out.name+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in out.iterdir():
            if p.is_file():z.write(p,p.name)
    print('Report created:',out/'full_pipeline_report.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--public');a=p.parse_args();build(a.output,a.public)
