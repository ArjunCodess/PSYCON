# Week 5 implementation record

Week 5 now has two paths.

The **group observation path** (`group-observation-1.0.0`) is the current target. An operator uploads one discussion video, numbers seats from the right of the frame toward the left, and maps anonymous voice clusters by hand. A named psychologist enters marksheet version 4.0, which scores items A–T as **0–4 or N/O**. A second rater can score blind, and a reviewer stores an adjudicated sheet without erasing either original. Training rows keep the recording hash and the evidence intervals. Predictions are written to `model_predictions` and do not replace ratings. `research/group_observation.py` freezes connected session splits, abstains when evidence is thin, and withholds model metrics until an item has enough independent sessions and nonzero scores.

The **binary device path** in `research/evaluation.py` is unchanged and still expects a 0/1 label. It cannot train the marksheet. The centre device in a group recording is shared audio only. A wrist score for one person needs a later wearer mapping and its own protocol.

No approved human session has been collected. The software rehearsal uses synthetic recordings inside the tests. Week 5 is not empirically complete until real consented sessions, completed ratings, and a held-out report state which items had enough evidence.

## Earlier binary-path record

The notes below describe the wrist-and-speech comparison prepared before the marksheet scale was fixed at 0–4 or N/O.

The earlier generated dataset and its accuracy, F1, ROC, confusion-matrix, prediction, and chart files were removed. Small artificial values remain inside unit tests, where they verify code behavior without being reported as research evidence.

## What was implemented

### Study controls

The research questions now cover combined-model improvement, environmental robustness, motion effects, and minimum stable recording duration. The study protocol orders recruitment, consent, hardware calibration, collection, quality review, feature extraction, model training, validation, analysis, and reporting.

The consent draft separates wrist sensing, audio recording, transcription, and biometric voice-profile permission. The data-management rules cover anonymous IDs, encryption, access, retention, withdrawal, deletion, backups, release review, and immutable dataset versions. Calibration and session templates record the operator, environment, firmware, hardware, measurement method, status, and errors.

### Metadata validation

`research/schema.py` validates one participant session before research use. It rejects direct-identifier fields, malformed anonymous IDs, pending approval or protocol versions, withdrawn consent, transcription or voice-profile permission without audio permission, missing calibration references, invalid timestamps, invalid synchronization quality, and sessions excluded from research.

The approved-study runner also checks that metadata has exactly one record for every participant and session in the feature tables. Missing and extra metadata records stop the run.

### Dataset assembly

`research/dataset.py` joins physiology, speech, and context tables on participant ID, session ID, and common-epoch window bounds. It rejects duplicate windows, invalid time ranges, missing synchronization keys, non-finite timestamps, and conflicting labels.

The join preserves a window when one input is absent. Each input receives availability, usability, and quality fields. Values marked corrupt, missing, low quality, untranscribable, or unsynchronized are masked before model fitting, while the quality state remains available for reporting. Physiology-only, speech-only, and combined views reuse the same windows and participant assignments.

The same module creates SHA-256 dataset manifests from an explicit file list and refuses to hash files outside the selected dataset directory.

### Participant-separated evaluation

`research/evaluation.py` creates one deterministic train, validation, and test assignment at the participant level. A participant cannot appear in more than one split. At least five participants are required, and the training and test sets must contain both target classes.

For each input set, the evaluator trains logistic-regression and random-forest candidates. Median imputation and missingness indicators are fitted inside the training pipeline. The validation F1 score selects the candidate, which is then refitted on the combined training and validation participants before one held-out test evaluation.

The evaluator produces:

- Accuracy, precision, recall, F1, ROC-AUC when both classes are present, and a two-by-two confusion matrix
- True-negative, false-positive, false-negative, and true-positive counts
- Grouped cross-validation scores on development participants
- Participant-level bootstrap confidence intervals rather than window-level intervals
- Separate error rows and prediction probabilities
- Descriptive statistics and feature-to-label correlations
- Combined-minus-physiology and combined-minus-speech F1 ablations
- Environment and motion slices
- Ten, thirty, and sixty-second duration summaries with probability drift from the full session
- Data-quality coverage, missing-signal counts, version IDs, split hashes, source-file hashes, charts, and a Markdown report

The duration code is ready, but the psychologist and research lead must choose the stability tolerance before test evaluation. External validation accepts a separate compatible dataset and rejects any participant overlap or feature mismatch.

### Approved-data command

`research/run_study.py` is the only Week 5 study runner. It reads the three feature tables and approved metadata, validates them, runs participant-separated evaluation, and writes versioned artifacts to the selected output directory.

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

Human-study inputs and outputs belong in the approved encrypted store. The repository ignores `data/studies/` and `results/studies/` to reduce the risk of committing participant data.

## Build-plan coverage

| Week 5 item | Current state | Evidence or blocker |
| --- | --- | --- |
| Freeze research questions | Implemented | `docs/research/STUDY_PROTOCOL.md` |
| Prepare the study workflow | Implemented | Study protocol and session checklist |
| Define anonymous participant and session records | Implemented | Metadata template and validator |
| Define consent, withdrawal, minimization, storage, and access | Implemented as documentation and validation | Consent and data-management files; approval is still required before collection |
| Synchronize physiology, speech, language, light, and motion features | Implemented in code | Dataset assembler; matching recordings have not been supplied |
| Reuse one participant split for all comparisons | Implemented in code | Split assignment and leakage checks |
| Train and validate candidates | Runner implemented; empirical work blocked | No completed marksheet and device dataset |
| Produce statistics, metrics, charts, ablations, and intervals | Reporting code implemented; empirical outputs blocked | No completed marksheet and device dataset |
| Define the model-update lifecycle | Implemented | `docs/research/MODEL_LIFECYCLE.md` |
| Calibrate the hardware | Blocked | Requires the assembled modules and recorded measurements |
| Run approved participant sessions | Blocked | Requires approval, consent, calibrated hardware, marksheets, and recordings |
| Record device and environmental conditions | Schema prepared; records blocked | Requires real sessions |
| External validation | Blocked | Requires a separate compatible dataset |

## What the marksheets change

Marksheet version 4.0 has 20 observable behaviour items, A through T. Each item is scored **0, 1, 2, 3, 4, or N/O**. The older 1–5 wording is withdrawn. N/O stays missing and is never coded as zero. The group-observation pipeline trains these item scores from the shared recording. The binary evaluator does not.

The full handoff contract is in `docs/research/DATA_REQUIREMENTS.md`.

## Current verification and completion

The last repository run completed with 120 passing tests and 5 skipped tests. Sixteen passing tests cover the Week 5 metadata, dataset, split, evaluation, artifact-writing, external-overlap, and approved-runner logic. The skipped tests require external WESAD data or other gated resources.

Week 5 is complete as a software and documentation preparation task. Its research exit gate remains open because there is no real dataset package, trained multimodal result, minimum-duration result, hardware calibration evidence, participant-session evidence, backup verification for participant data, or external validation.

