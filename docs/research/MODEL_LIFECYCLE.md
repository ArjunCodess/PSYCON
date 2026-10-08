## Current audio-first implementation amendment, 2026-10-08

The canonical application follows [the frozen dataset protocol](../DATASET_PROTOCOL.md) and [the PostgreSQL runbook](../POSTGRES_TRAINING_RUNBOOK.md). PostgreSQL holds normalized annotations, bounded original spreadsheet/form sources, immutable corrections, mappings, consent, snapshots and model lineage. Original audio/video and generated model files remain local with exact names and registered hashes. Source documents and private exports retain human metadata under the annotation-source retention policy; they are not public research releases. Names and identity embeddings are unnecessary.

The supervised targets are eligible A-T ratings and separately annotated communication traits. Same-session event baselines differ from strictly earlier personal history. Fitting, held-out evaluation and deliberate deployment are separate gates, as is the controlled A/B/C personalization experiment. Real training is currently unavailable without consented, independently reviewed human labels. Historical device-study instructions below apply only to that separate experiment and do not define the active predictor.

# Model update lifecycle

Every model release follows the same gated sequence. A failed gate stops the release and leaves the current model unchanged.

1. **Register data.** Create an immutable dataset manifest with source hashes, consent and withdrawal state, protocol version, inclusion decisions, label policy, and dataset version.
2. **Review quality.** Validate schema, provenance, synchronization, missingness, corruption, class coverage, participant counts, and possible duplicates. Record exclusions without editing the source records.
3. **Freeze the experiment.** Record the research question, primary metric, split seed, participant assignments, feature version, candidates, thresholds, slices, and acceptance criteria before test evaluation.
4. **Train reproducibly.** Fit preprocessing and candidates on training participants, tune with validation participants, save dependency and code versions, and retain run logs and model artifacts.
5. **Validate.** Run group cross-validation, the frozen test set, modality ablations, quality and context slices, calibration checks, error analysis, and a named external dataset when one is available. Fixture results never satisfy participant or external-validation gates.
6. **Approve the release.** Compare the candidate with the current model and its safety constraints. A reviewer signs the release record only if data authority, reproducibility, performance, subgroup review, limitations, and rollback artifacts are complete.
7. **Version and publish.** Assign immutable dataset and model versions, publish the model card and metrics, update the deployment pointer, and retain the previous model for rollback. Reports must call outputs research indicators and must identify unsupported populations and conditions.

Withdrawn data trigger an impact review. If removal changes a released training dataset, create a new dataset version, retrain when required by the approved policy, and never rewrite the old manifest silently.

