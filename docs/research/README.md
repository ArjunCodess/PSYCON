# Behavioral research workflow

## Latest frozen-source audit

The October 13 audit refitted the original, compact and previous agreement-selection procedures with zero saved-prediction mismatches. Its new nested procedure reached 264/402 exact matches (65.67%) and MAE 0.453, exactly matching the fold training-mode predictions. It selected median/mode references in four of five outer folds and a pooled core logistic model in the fifth. Score-3 recall fell from compact's 18.45% to 4.85%, so the predefined promotion gates failed and compact remains the research model reference. No candidate was activated.

The strongest fixed-configuration diagnostic reached 270/402 (67.16%), MAE 0.435, but predicted score 4 on 397 ratings and recalled only 1.94% of score 3. This is a disclosed outer diagnostic, not the inner-selected procedure or an unbiased winner. An 85% target is unsupported by the measured evidence.

All 423 rating counts for scores 0-4 are 0, 24, 24, 109 and 266. The common cohort counts are 0, 13, 20, 103 and 266. The original abstained on 21 ratings; every other procedure scored all 423, with explicit population-reference fallbacks. On all 423, compact achieved 259 matches (61.23%, MAE 0.506), previous agreement selection 256 (60.52%, 0.513), median 268 (63.36%, 0.478), and mode/new nested selection 273 (64.54%, 0.470). The fixed 402 cohort omits those same 21 IDs for paired comparison, not new abstentions.

These are retrospective development results, not independent final testing. Known links stay within folds, but 21 participant-session identities remain unresolved. The fitted labels have zero independent reviews, structured evidence windows, recorded fair-opportunity decisions or individual observer-confidence fields. Rubric reliability and a numerical performance ceiling cannot be inferred. Independent blinded re-rating and a newly collected identity-resolved test sample are required. Session observations do not establish stable psychological traits.

See [the aggregate audit](maximum-defensible-2026-10-13/submission_results.md). Earlier dated implementation and experiment records below remain historical.


The active study connects speaker-specific conversational evidence with psychologist-reviewed A-T observations. Use the [behavioral direction](../PSYCON_VISION.md), [dataset protocol](../DATASET_PROTOCOL.md), and [PostgreSQL training runbook](../POSTGRES_TRAINING_RUNBOOK.md). Import and review marksheets in the canonical application, freeze eligible examples, and queue supervised fitting on the Docker or local worker.

The five marksheet areas describe contextual behavior in one discussion. Independent communication targets have separate annotation definitions. Archetype goals are optional exploratory comparisons and supply no human training labels. Predictive agreement with human ratings requires held-out evaluation; it does not establish personality or diagnosis. The current real records lack eligible consented, independently reviewed labels.

The controlled A/B/C interpretation experiment evaluates personalization separately from the supervised predictor. Freeze identical supervised outputs for B and C, preserve final-evaluation roles, and report missing evaluation honestly.

## Historical Week 5 device study

The material below records the separate earlier wrist-and-speech experiment. Its commands, physiological inputs, and binary targets are not the active marksheet trainer. No hardware or face dependency is introduced into the behavioral instrument.

### Earlier setup

The Week 5 research code is prepared, but the repository has no PSYCON participant dataset and therefore has no valid Week 5 model result. Training starts after completed psychologist marksheets and their matching device sessions are available.

The marksheets provide human observations and possible target variables. They do not contain the physiological and speech inputs needed to train the PSYCON sensor model. See `DATA_REQUIREMENTS.md` for the exact handoff and `../WEEK_5_IMPLEMENTATION.md` for the implementation record.

## What is ready

The approved-study runner validates session metadata, joins physiology, speech, and context features on common time windows, preserves missing and low-quality signals, assigns whole participants to train, validation, and test sets, compares logistic-regression and random-forest candidates, and produces cross-validation, confidence intervals, error analysis, ablations, context slices, duration analysis, confusion matrices, and ROC curves.

No generated dataset or generated model metrics are checked into the repository. Unit tests use small artificial values to verify code behavior, but those values are never presented as research evidence.

## Run after the data handoff

Keep participant data in the approved encrypted study location outside this repository. Once the input tables and metadata pass review, run:

```powershell
python -m research.run_study `
  --physiology D:\approved-study\features\physiology.csv `
  --speech D:\approved-study\features\speech.csv `
  --context D:\approved-study\features\context.csv `
  --metadata D:\approved-study\metadata\sessions.json `
  --output-dir D:\approved-study\results\model-1.0.0 `
  --dataset-version dataset-1.0.0 `
  --model-version model-1.0.0 `
  --seed 42
```

Each feature CSV uses `participant_id`, `session_id`, `window_start_ms`, `window_end_ms`, `label`, and `quality_state`. Labels must agree across modalities. Physiology and speech feature columns must be numeric. Context records may also contain environment and motion categories for descriptive analysis.

The metadata file is a JSON array with one record per participant and session. Start from `research/templates/session_metadata.json`. The validator rejects pending approvals, direct identifiers, invalid consent combinations, withdrawn sessions, missing calibration references, and incomplete session coverage.

## Analysis rules

One seeded participant assignment is reused for physiology, speech, and combined models. Preprocessing and model selection use development participants only. Confidence intervals resample participants rather than treating repeated windows from one person as independent observations.

The psychologist and research lead must freeze the target score, primary metric, handling of `N/O`, minimum evidence per domain, stability tolerance, and any exclusion rules before opening the test set. A marksheet total must not become the target automatically because its 20 domains describe different behaviors and may require separate analysis.

## Records and gates

- `STUDY_PROTOCOL.md` defines the research questions, session procedure, variables, eligibility, analysis, and reporting rules.
- `INFORMED_CONSENT_TEMPLATE.md` separates physiology, audio, transcription, voice-profile, retention, access, and withdrawal choices.
- `DATA_REQUIREMENTS.md` defines the marksheet and device-data handoff.
- `DATA_MANAGEMENT.md` defines protected storage, access, manifests, backups, withdrawal, and release handling.
- `MODEL_LIFECYCLE.md` defines dataset review, training, validation, approval, versioning, release, and rollback.
- `research/templates/` contains session, calibration, and operator records.

Participant collection remains blocked until the relevant reviewer approves the protocol and consent text. Worn collection also remains blocked until physical calibration and electrical safety checks pass.
