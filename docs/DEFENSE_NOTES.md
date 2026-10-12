# PSYCON: evidence and interview preparation

These are AI-assisted preparation notes, not submission text or a record of work personally performed by the students. Verify every answer against the source records and describe assistance accurately.

## The statement the current evidence supports

PSYCON is a contextual communication research instrument. It connects attributed recording measurements, imported observer scores, known participant/source groups, and inspectable reports. It has not validated a stable personality profile, reliable prediction of independently reviewed behavior, or effective personalized coaching.

The exploratory question actually examined was whether general conversational proxies recover raw source-form scores better than a training-median reference when known groups are omitted. The answer on this corpus is no. The formal behavioral questions about reviewed A-T ratings and earlier-history benefit remain open.

## Results to know without reading

| Procedure, same 402 evaluated item observations | Exact agreement | Mean absolute error | Mean observed-class sensitivity |
|---|---:|---:|---:|
| Original class-balanced logistic | 57.2% | 0.562 | 30.3% |
| Retrospective nested selection | 60.9% | 0.493 | 28.8% |
| Sensitivity-focused development | 56.5% | 0.562 | 29.9% |
| Latest compact procedure | 62.2% | 0.490 | 30.0% |
| Training-median reference | 64.4% | 0.460 | 29.6% |

The latest compact procedure improves exact agreement by 5.0 percentage points and reduces mean error by about 12.8% relative to the original model, but loses to the median reference in agreement/error and still fails on score 2. The earlier MAE repair improved agreement while reducing class-average sensitivity. These attempts do not establish a validated overall improvement. The original 97.9% training agreement and latest 73.5% training replay are resubstitution, not independent test accuracy.

The full revised procedure covers all 423 labels using explicit training-reference fallbacks, producing 60.0% agreement versus 63.4% for the median reference. Those denominators differ from the 402-label comparison and must not be mixed. There are forty participant-session examples, nine recordings and five known connected groups; 423 ratings are not 423 people.

Sensitivity means correctly detecting an exact score among observations with that score. On the common 402 labels, original sensitivities for scores 1, 2, 3 and 4 are 15.4%, 0%, 33.0% and 72.9%; revised values are 15.4%, 0%, 13.6% and 86.1%. Score 0 has no observations, so its sensitivity is unavailable. These are descriptive pooled ordinal classes with different item meanings, not clinical sensitivity. P1-P12 contribute 397/402 observations.

A separate post-hoc sensitivity-oriented nested procedure used the same candidates and achieved 56.5% agreement, MAE 0.562 and 29.9% mean observed-class sensitivity on the identical 402 labels. It detected score 2 in one of twenty cases, but overall sensitivity remained below the original 30.3%. All 423 labels yielded 55.8% agreement and MAE 0.574. Both repair attempts remain disclosed; neither is promoted as reliable prediction.

The latest compact procedure uses four/eight predefined predictors, ordinal threshold classifiers and shallow ensembles with inner sensitivity constraints. It achieves 62.2% agreement, MAE 0.490 and 30.0% class sensitivity on the same 402 labels. It improves over the original in agreement/error but still loses to the median reference, with zero score-2 recall. Full 423-label performance is 61.2%/0.506 versus median 63.4%/0.478. The descriptive five-group MAE-difference interval spans zero (-0.013 to 0.049). Eight of the fourteen final fits are population references; six use measured features. All fixed-candidate attempts are disclosed; none was promoted as independently validated.

## Questions a judge can reasonably ask

**Why does the model lose to a baseline?** Ratings are concentrated at 4, and forty examples provide limited independent information. General timing/text proxies may omit the context needed for these ratings. The results establish the performance gap, not a unique cause. We examined stronger regularization, unbalanced/balanced logistic fits, ordinal ridge approximations and reference constants without selecting on outer-fold labels.

**Was the improvement selected using the test data?** Candidate selection used inner omitted-group folds within each outer training partition. However, the entire repair was developed after inspecting the original grouped results, so this remains retrospective development. There is no untouched independent final test. The candidate set, objective, fallback policy and every outer fold are retained.

**Why not quote the best target?** P2's revised exact agreement is 82.9%, but it is a median reference and its observed-class sensitivity is 25%. That is not evidence that individualized behavior prediction works. We retain all targets, class counts and failed results rather than highlighting a favorable number alone.

**What is original?** The engineering contribution is the reviewable connection among recording evidence, contextual observation forms, immutable label revisions, known-person/source grouping and separate report inputs. The transcription, diarization and LLM are pretrained components. No new psychological discovery or validated personality construct is claimed.

**What does the report actually personalize?** It can use the selected communication goal and available strictly earlier eligible history. The demonstrated example has no eligible history. The new measurement summary is deterministic; its exercise is prewritten for the selected goal. The bounded LLM uses supplied measurements and constrained statements. Neither establishes a usefulness or history benefit.

**What prevents a plausible hallucination?** Invalid citations, wrong measured values, duplicate claims and unverified numerical inferences are withheld. Earlier failed generations are retained. Schema and ID checks are engineering controls; independent review is still needed for meaning, attribution and usefulness.

**What would change the conclusion?** Independently reviewed labels and a fresh participant/source-disjoint sample that shows lower error than the frozen training reference, without collapsing minority-class sensitivity. A blinded history-only comparison would separately need to show better grounded, useful reports while keeping other inputs fixed.

## Repairs completed

- Nested group model selection fits preprocessing only on training data and keeps known groups together. It compares nine disclosed candidate configurations and falls back to training references when evidence is insufficient.
- The latest fourteen final fits are saved as exploratory candidates, including eight population references and six feature-based models. Earlier candidate runs remain separately auditable. They were not promoted because the selection procedure remains below baseline overall.
- Accuracy, error, class sensitivity, precision, specificity, supports, normalized confusion matrices and omitted-group error plots are exported. A paired known-group bootstrap interval is explicitly exploratory with only five groups.
- The software supplies a separate deterministic measurement summary and labels the selected-goal exercise as untested. It does not pass it off as generated coaching or a personality diagnosis.
- Report validation rejects duplicates, mismatched measured values and unsupported derived numbers. The bounded generation schema limits factual observations and fixes the optional exercise to the selected goal.
- A history-only input-pair helper changes only the historical baseline and refuses unavailable history. It prepares a controlled comparison but is not a completed study.
- Feature denominator metadata now uses the correct speaking duration, exclusive speaking total, turn count, gap count and question/proposal counts. Frozen snapshot feature values were not changed; older denominator metadata remains historical.

## Gaps that software changes cannot close

No documented independent final-test sample, independently reviewed eligible labels, psychologist inter-rater reliability, completed blinded report-benefit study, or longitudinal improvement result exists in this release. Unknown participant overlap and representativeness remain unresolved. Recruitment and prior approval documentation must be verified from real records; user-attested permission does not establish prior approval. Do not invent, backdate or substitute AI opinions for any of them.

The authors must identify what they personally designed, implemented, transcribed, collected and analyzed, and disclose coding/writing assistance. The paper and synopsis remain AI-assisted working drafts. Verify the applicable fair's submission and AI-use requirements before using them as submission materials.

## Inspectable evidence

- [Nested analysis policy and implementation](../research/defensible_source_models.py)
- [Public aggregate results](report_assets/defensible-source-summary.json)
- [Latest compact/ordinal policy and aggregate results](report_assets/compact-source-summary.json)
- [Compact model implementation](../research/compact_source_models.py)
- [Original grouped results](report_assets/source-cross-validation-summary.json)
- [Source-score training release](report_assets/source-training-summary.json)
- [Known overlap mapping](research/PARTICIPANT_OVERLAP.md)
- [ISEF science judging criteria](https://www.societyforscience.org/isef/grand-award/criteria/)
- [Grouped and nested evaluation documentation](https://scikit-learn.org/stable/modules/cross_validation.html)

Private recording-level outputs, final model artifacts and figures are packaged locally under `.runtime/defensible-analysis`. They contain research material and are intentionally excluded from version control.

The authors report that approval and consent records exist; document locations, approving body and dates remain pending verification and citation. This is not a claim that approval was absent.
