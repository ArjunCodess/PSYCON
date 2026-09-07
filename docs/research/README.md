# Week 5 research workflow

Week 5 now has two paths. The deterministic fixture path is safe to run from a clean checkout and verifies the complete software workflow. The approved-study path accepts synchronized records only after its metadata passes consent, approval, eligibility, and anonymity checks.

Neither path turns PSYCON into a diagnostic system. Fixture results test code, and participant results would remain experimental research indicators.

## Reproduce the checked-in fixture

```powershell
python -m research.run_fixture_study
python -m pytest tests/research
```

The run regenerates `data/research_fixture/v1/` and `results/week5_fixture/`. Its manifest hashes raw, metadata, and synchronized feature files. The result package contains frozen participant assignments, predictions, explicit errors, descriptive statistics, correlations, candidate and grouped cross-validation metrics, confidence intervals, confusion matrices, ROC curves, context slices, duration analysis, and a readable report.

The fixture contains 15 synthetic participant-like groups and deliberate missing or low-quality signals. It contains no human recording and no device measurement, so it cannot satisfy hardware calibration, participant collection, multimodal benefit, or external-validation claims.

## Approved-study inputs

Do not put participant data in this repository. Store encrypted source files in the approved study location, then run:

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

Each feature CSV has these keys:

- `participant_id`, `session_id`, `window_start_ms`, and `window_end_ms` identify a synchronized common-epoch window.
- `label` is the frozen binary research target and must agree across modalities.
- `quality_state` is `usable`, `corrupt`, `missing`, `low_quality`, `untranscribable`, or `unsynchronized`.
- The remaining columns are modality features. Physiology and speech model inputs must be numeric. Context may also contain `environment` and `motion_condition` for descriptive slices.

The synchronizer keeps the union of windows. It masks feature values from unusable modalities, adds availability and quality fields, and lets the model's training-only imputer handle missing numeric inputs. This makes loss visible in the report instead of quietly deleting it.

The metadata file is a JSON array with one record per participant and session. Start from `research/templates/session_metadata.json`, then use only approved values. The validator rejects pending approvals, direct-identifier field names, invalid consent dependencies, withdrawn sessions, missing calibration references, and incomplete session coverage.

## Participant separation and model selection

The runner creates one seeded participant assignment and reuses it for physiology, speech, and combined models. It fits logistic-regression and random-forest candidates on training participants, selects by validation F1, refits on training plus validation participants, and opens the held-out test participants once. Group cross-validation uses only development participants.

Confidence intervals resample test participants rather than individual windows, so repeated windows from one person do not masquerade as independent samples. Environment, motion, and duration results are descriptive slices. The approved protocol must freeze the primary metric, stability tolerance, and slice categories before collection.

Supply all three `--external-*` arguments to evaluate a separate compatible dataset. The runner rejects participant overlap and mismatched feature columns. Without a separate dataset, the report records external validation as blocked.

## Records and gates

- `STUDY_PROTOCOL.md` freezes the research questions, approved-order session procedure, variables, eligibility, analysis, and reporting rules.
- `INFORMED_CONSENT_TEMPLATE.md` separates physiology, audio, transcription, voice-profile, retention, access, and withdrawal choices.
- `DATA_MANAGEMENT.md` defines protected storage, access, manifests, backups, withdrawal, and release handling.
- `MODEL_LIFECYCLE.md` defines dataset review, training, validation, approval, versioning, release, and rollback.
- `research/templates/` contains session, calibration, and operator checklist records.

Actual participant collection remains blocked until the relevant reviewer approves the final protocol and consent text. Worn collection also remains blocked until the physical calibration and electrical safety gates from earlier weeks pass.

