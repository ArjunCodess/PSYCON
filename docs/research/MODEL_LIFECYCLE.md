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

