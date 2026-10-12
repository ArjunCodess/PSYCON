# Maximum defensible performance audit, 13 October 2026

The October 13 audit refitted the original, compact and previous agreement-selection procedures with zero saved-prediction mismatches. Its new nested procedure reached 264/402 exact matches (65.67%) and MAE 0.453, exactly matching the fold training-mode predictions. It selected median/mode references in four of five outer folds and a pooled core logistic model in the fifth. Score-3 recall fell from compact's 18.45% to 4.85%, so the predefined promotion gates failed and compact remains the research model reference. No candidate was activated.

The strongest fixed-configuration diagnostic reached 270/402 (67.16%), MAE 0.435, but predicted score 4 on 397 ratings and recalled only 1.94% of score 3. This is a disclosed outer diagnostic, not the inner-selected procedure or an unbiased winner. An 85% target is unsupported by the measured evidence.

All 423 rating counts for scores 0-4 are 0, 24, 24, 109 and 266. The common cohort counts are 0, 13, 20, 103 and 266. The original abstained on 21 ratings; every other procedure scored all 423, with explicit population-reference fallbacks. On all 423, compact achieved 259 matches (61.23%, MAE 0.506), previous agreement selection 256 (60.52%, 0.513), median 268 (63.36%, 0.478), and mode/new nested selection 273 (64.54%, 0.470). The fixed 402 cohort omits those same 21 IDs for paired comparison, not new abstentions.

These are retrospective development results, not independent final testing. Known links stay within folds, but 21 participant-session identities remain unresolved. The fitted labels have zero independent reviews, structured evidence windows, recorded fair-opportunity decisions or individual observer-confidence fields. Rubric reliability and a numerical performance ceiling cannot be inferred. Independent blinded re-rating and a newly collected identity-resolved test sample are required. Session observations do not establish stable psychological traits.

| Procedure, common 402 ratings | Correct | Agreement | MAE | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| Original grouped model | 230 | 57.21% | 0.562 | 30.33% |
| Compact procedure | 250 | 62.19% | 0.490 | 29.98% |
| Previous agreement-selection experiment | 247 | 61.44% | 0.498 | 29.10% |
| Fold training median | 259 | 64.43% | 0.460 | 29.64% |
| Fold training mode | 264 | 65.67% | 0.453 | 29.21% |
| New nested pooled procedure | 264 | 65.67% | 0.453 | 29.21% |

## Class behaviour and metric assumptions

Compact recalls for scores 1-4 are 15.38%, 0%, 18.45% and 86.09%; new nested recalls are 15.38%, 0%, 4.85% and 96.62%. Common-cohort quadratic weighted kappa is 0.101 for compact and 0.129 for the challenger. Per-class precision, recall, F1, support and predicted counts are in `candidate_comparison.csv`; rows in each confusion matrix are reference scores and columns are predictions, ordered 0-4. MAE assumes equal adjacent score distances, QWK uses quadratic distance weights, and balanced accuracy averages only observed truth classes. Undefined metrics remain explicit. Pooled scores mix distinct targets and are descriptive rather than a validated latent measure.

## Reproduction and private artifacts

Run `.runtime/venv/Scripts/python.exe -m research.maximum_defensible --output <new-directory>` with the private frozen inputs. The output must be new. Training-only preprocessing, inner grouped hyperparameter selection, fixed common-cohort alignment and source-hash checks are enforced. No demonstrable implementation bug explains the previous metrics. Six new regression tests contributed to 82 passing research tests; one media test was skipped because ffmpeg was absent from the runtime PATH.

The public aggregate summary is `docs/report_assets/maximum-defensible-summary.json`. The private run under `.runtime/maximum-defensible-2026-10-13-final/` contains all seven requested submission files: `verified_baseline.json`, `candidate_comparison.csv`, `fold_predictions.csv`, `confusion_matrices.json`, `error_analysis.md`, `experiment_log.csv` and `final_recommendation.md`. It also retains 4,416 successful fit/evaluation log records, all unsuccessful model comparisons, fold selections, slices, feature audits, source receipts, test output and checksums. No fit failed; a model can run successfully while failing the performance criterion. Private individual predictions and the submission ZIP are excluded from Git.
