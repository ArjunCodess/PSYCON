# Behavioral direction for PSYCON

PSYCON studies observable behavior in conversations. It connects a person's talking patterns and interaction context with psychologist-reviewed A-T ratings, preserves the evidence behind those judgments, and evaluates whether supervised models can predict eligible ratings on new conversations. The [README](../README.md) gives startup and usage, [architecture](INSTRUMENT_ARCHITECTURE.md) describes the current application, and [status](INSTRUMENT_STATUS.md) distinguishes implementation from research evidence.

## What a behavioral profile means

The authoritative [v4.0 marksheet](PSYCON_Psychologist_Observation_Mark_Sheet.pdf) records one participant in one discussion. Its five areas are discussion tracking, contribution structure, turn-taking and reciprocity, response to challenge, and pressure-linked delivery change. The [interpretation guide](PSYCON_Tendency_Flag_Guide.pdf) permits contextual pattern descriptions with timestamps and qualifications. Neither document assigns personality, occupation, intent, emotion, intelligence, or diagnosis.

A psychologist-reviewed profile consists of item ratings, supporting moments, discussion context, fair opportunity, observer confidence, validity checks, and review or adjudication records. It remains a human judgment tied to that recording. Agreement between reviewers measures reproducibility; agreement between a model and those reviewers measures prediction performance. Neither alone proves psychological validity.

## The evidence chain

| Layer | What it contributes | Boundary |
| --- | --- | --- |
| Measured observations | Speaker timing, participation, transcript markers, and supported interaction windows | A marker or overlapping turn cannot establish intent or a rubric score on its own |
| Human annotations | Psychologist item ratings, contextual evidence, independent review, and immutable corrections | Self-report and each observer's judgments retain separate sources |
| Supervised predictions | Per-target estimates from frozen reviewed examples, with model versions and abstention | A prediction never replaces a human answer or becomes a human training label |
| Interpretation and history | Evidence-backed explanations and comparisons with strictly earlier eligible sessions | An explanation does not establish a cause or a permanent trait |

Reviewed participant-to-speaker mappings connect the layers. A longitudinal person, a session participant, and a diarized cluster are separate records. Anonymous codes are enough; names, face recognition, and identity embeddings are unnecessary.

## Learning the relationship with human observations

The research question is whether speaker-specific conversational measurements and context predict the psychologist's reviewed item ratings. Descriptive feature/rating correlations can help characterize a dataset, but they are not evidence that one behavior causes another. Each supported A-T target needs its own readiness, evaluation, and limitations. Do not collapse the sheet into an invented overall personality score.

The model trains only on eligible examples with consent, reviewed mappings and source ancestry, completed processing, applicable opportunity, contextual evidence, and independent answer review. Spreadsheet uploads remain saved when these conditions are missing, with explicit exclusion reasons. Zero means not observed despite fair opportunity, N/O means no supported conclusion, and missing means no supplied answer.

Trigger-dependent items need the preceding event and response windows. Q-T additionally compare with the same person's earlier behavior inside that discussion. This event baseline is separate from PSYCON's previous-session historical baseline. Audio-supported participation change can support T; visual-only observations remain retained but excluded. S currently lacks supported vocal-change window features and cannot be trained.

Snapshots freeze answer and mapping revisions, feature versions, source hashes, consent, and split assignments. Shared participants and recording ancestry stay in the same split component. Training-only preprocessing, held-out baseline comparisons, per-item metrics, and separate final evaluation prevent apparent progress caused by leakage. A completed fit remains exploratory when sufficient independent evaluation is unavailable.

The independent Docker or local CPU trainer runs durable supervised training jobs and commits queued imports without waiting for speech processing. This updates the behavior predictor; it does not automatically fine-tune the speech models or LLM. PostgreSQL records job state, snapshots, evaluations, artifact manifests, activation, rollback, and prediction lineage. Original media and generated models keep registered local files. Models do not activate automatically.

## Personal history, references, and reports

Personal data and contextual talking patterns are the main report content. Repeated-session comparisons use only eligible, strictly earlier independent recordings and report counts and uncertainty. A single session cannot establish a stable trait, and a measured change cannot establish that coaching caused it.

Executive, Builder, Salesperson, and Negotiator remain optional exploratory reference lenses for compatibility and controlled research. They are secondary to participant evidence and human observations. Selecting a lens supplies neither an identity nor ground truth. Independent communication annotations remain separately defined session-level behaviors.

Reports show observations, human ratings, predictions, and LLM interpretations as separate kinds of evidence. They remain useful when training data or an LLM is unavailable. The transcript-only A, structured-context B, and full-PSYCON C experiment remains controlled; B and C use identical frozen supervised predictions so predictor changes do not confound historical personalization.

## Staged delivery

- [x] Stage 1: update current documentation to center behavioral evidence and psychologist-reviewed marksheet targets, and identify legacy instructions clearly.
- [x] Stage 2: review the application and reports so participant data, talking patterns, and marksheet relationships receive priority over archetype controls.
- [x] Stage 3: complete and verify the guided marksheet import, database save, readiness, snapshot, training-button, evaluation, activation, rollback, and speaker prediction journey through PostgreSQL tests and the application browser, with independent Docker/local CPU training and intake.

The current application already has participant CSV/XLSX import, review, readiness, frozen snapshots, durable fitting, and model lifecycle controls. Stage 2 now puts speaker measurements and contextual human ratings first, with optional reference comparisons in disclosures. Stage 3 verifies that journey in the application with a disposable synthetic PostgreSQL study, not real participant outcomes. Real human-data validation is not complete. The current real dataset lacks eligible consented, independently reviewed labels. The coordinated original-media backup also still needs a destination with enough free space.

The Stage 2 interface reads current reviewed human observations alongside measurements and predictions without adding those human answers to held-out A/B/C inputs. Existing model targets and evidence identities remain unchanged. Later protocol and implementation changes must be recorded explicitly.
