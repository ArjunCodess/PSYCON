# Results for student verification and independent submission writing

PSYCON is a research prototype for contextual communication-pattern measurement and evidence-linked reporting. It does not diagnose psychological conditions or establish personality or intent.

We evaluated fourteen source-score targets using 423 existing ratings from 40 participant-session examples across nine recordings and five known connected groups. Each omitted-group fold fitted preprocessing and estimators on the other groups. Comparisons use the same 402 ratings on which the original model supplied a prediction; 21 original abstentions are disclosed. A fixed new experiment selected among existing candidates inside inner group folds using agreement with ordinal-error and class-recall guards. All procedures remain retrospective development, with no independent final test.

| Procedure | Scored ratings | Exact matches | Agreement | MAE | Mean observed-class recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original grouped model | 402 | 230 | 57.21% | 0.562 | 30.33% |
| Existing compact procedure, common cohort | 402 | 250 | 62.19% | 0.490 | 29.98% |
| New agreement selection, common cohort | 402 | 247 | 61.44% | 0.498 | 29.10% |
| Fold training-median reference, common cohort | 402 | 259 | 64.43% | 0.460 | 29.64% |
| Fold training-mode reference, common cohort | 402 | 264 | 65.67% | 0.453 | 29.21% |

The original final-fit training agreement of 97.9% does not establish generalization. The roughly 64% result is a simple median reference. The new experiment's outcome must be judged against both references, ordinal error and rare-class recall; a larger development percentage alone does not answer the behavioral research question. Full metrics, per-target slices, class counts and all predictions are retained in `evaluation_results.json` and `paired_predictions.json`. No new candidate was deployed automatically.

Current evidence establishes that the source-score fitting, portable prediction and bounded reporting workflows run reproducibly. It does not establish that conversation features reliably improve on population references, that psychologists agree with each other, or that adding history improves reports. Unresolved participant overlap, unreviewed ratings, unequal observation opportunity and rare classes limit the result. The next study needs independently reviewed ratings, explicit rubric opportunity/evidence, reproducible human scoring and a fresh participant/source-disjoint sample, followed by blinded report usefulness evaluation.

The existing compact procedure is retained: the new policy loses agreement, MAE and class recall on the common cohort. Its score-class recalls are 15.4%, 0.0%, 18.4% and 86.1% for scores 1-4 respectively; score 0 is unobserved. Quadratic kappa is 0.101, a pooled descriptive statistic rather than evidence of psychological validity or rater reliability.

These are AI-assisted preparation notes. Students must verify claims and write applicable submission materials themselves under the fair's rules.
