# Emergency evaluation audit

The reported roughly 64% is reproduced as the training-median reference: 259/402 = 64.4279%. It is not the original PSYCON model's performance. Original model refitting reproduces all archived outputs, with 0 prediction mismatches.

## Architecture and scoring

The instrument registers recordings and provenance, processes speaker-attributed transcripts, computes conversational features, imports observer forms and freezes source-group manifests. `backend/instrument/datasets.py` preserves missing/N/O answers separately and exposes strict reviewed and exploratory source-score eligibility. `backend/instrument/training.py` fits training-only median imputation, missingness indicators, standardization and per-target logistic models, then serves portable JSON through `infer`. `research/analyze_source_training.py` performs the original omitted-group diagnostic; `research/compact_source_models.py` implements the existing compact nested procedure. `research/emergency_audit.py` reproduces the frozen evaluation and records this new experiment. The binary physiological evaluation in `research/evaluation.py` is a separate task and must not supply these ordinal agreement claims.

The prediction unit is one target rating for a participant within one recorded session. Fourteen fitted targets are G, I and P1-P12, with 423 ratings on 40 participant-session examples, nine recordings and five known connected groups. They are not 423 people. The full manifest contains additional unfitted labels; only the original fourteen fitted targets define this audit cohort. All examples were used in the original final training fit. Original omitted-group fitting gates abstain on 21 ratings, leaving the fixed 402-rating comparison cohort.

Labels are integer 0-4 source observations in form `psycon-context-5.0`; they are not diagnostic categories. N/O is insufficient observation opportunity, never score zero. Missing targets are not manufactured. P1-P12 contextual role scores dominate pooled agreement, so per-target results accompany pooled results. No majority vote over utterances or LLM report text supplies these supervised ratings. Reports have a separate bounded prompt, structured schema, measurement checks, speaker evidence and uncertainty. The LLM is not the source of the score being audited.

## Reproduced results

| Procedure | Scored ratings | Exact matches | Agreement | MAE | Mean observed-class recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original grouped model | 402 | 230 | 57.21% | 0.562 | 30.33% |
| Existing compact procedure, common cohort | 402 | 250 | 62.19% | 0.490 | 29.98% |
| New agreement selection, common cohort | 402 | 247 | 61.44% | 0.498 | 29.10% |
| Fold training-median reference, common cohort | 402 | 259 | 64.43% | 0.460 | 29.64% |
| Fold training-mode reference, common cohort | 402 | 264 | 65.67% | 0.453 | 29.21% |

Original final-fit replay is 414/423 = 97.87% and is training resubstitution, not testing. The new procedure scores all 423 ratings at 60.52% with explicit population-reference fallbacks; the median reference on all 423 is 63.36%. Cohorts must not be mixed.

## Integrity findings and limits

No observed label-index, ID alignment, duplicate-rating, denominator, scale or portable-output defect explains the 64% claim. The actual problem is attribution of a baseline result to the model and possible conflation of training/CV/testing. The new audit aligns by target and speaker ID and fails on duplicates, unmatched predictions, reference disagreement, invalid scales and group mismatch instead of silently changing a denominator. The frozen manifest hash is checked before fitting and again after; source labels were not altered. No difficult observations were excluded beyond the original outcome-independent fitting gates, and fallback-inclusive results are shown separately.

Known-group folds reduce known overlap but unresolved identity/source overlap remains. Every procedure is retrospective development because these observations were already used during development. A new random split now would not create an untouched test set. Opportunity, observer confidence, structured evidence and independent label review remain missing; strictly eligible behavioral-validation labels number zero. Inter-rater reliability, clinical/personality validity and report benefit are unmeasured. The authors confirm consent/approval documentation; additional details outside supplied photographs are not independently checked. The audit uses local frozen inputs rather than asserting current live database state.

## Metric assumptions

Exact agreement is the proportion of matched integer ratings that coincide, not validated psychological accuracy. MAE treats adjacent scale steps as equal distances, a simplifying ordinal assumption. Quadratic kappa applies squared distance weights and pooled marginal chance agreement; the pooled number mixes targets and repeats people, so per-target results and grouped limitations matter. It is model-reference agreement, not psychologist inter-rater reliability. Absent reference classes have null recall. No predictions for an observed class yield zero recall/F1 but undefined precision. Macro recall/F1 average only observed reference classes; score zero is unobserved. Training-mode references are fitted within each target/fold, never from held-out labels. No significance claim is made.
