# Week 5 research workflow

The Week 5 research code is prepared, but the repository has no PSYCON participant dataset and therefore has no valid Week 5 model result. Training starts after completed psychologist marksheets and their matching device sessions are available.

The marksheets provide human observations and possible target variables. They do not contain the physiological and speech inputs needed to train the PSYCON sensor model. See `DATA_REQUIREMENTS.md` for the exact handoff.

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

