# Observed disagreement analysis

The new procedure disagrees on 167/423 full-cohort ratings. The actual reference-to-prediction transitions are {(1, 2): 2, (1, 3): 3, (1, 4): 10, (2, 3): 3, (2, 4): 20, (3, 1): 5, (3, 2): 7, (3, 4): 81, (4, 2): 2, (4, 3): 34}. These are descriptive scoring patterns, not causal explanations. Source-score 4 is common; score zero is absent. The confusion matrix and class-recall chart show whether minority classes are recognized, while the per-target metrics identify uneven performance.

## Anonymized observed examples

- Example 11, P1, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.
- Example 11, P2, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.
- Example 11, P3, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.
- Example 12, P2, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.
- Example 12, P5, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.
- Example 12, P7, Group 1: source 1, new prediction 4, original 2, compact 4, fold median 4.
- Example 29, P12, Group 1: source 1, new prediction 4, original 3, compact 4, fold median 4.
- Example 29, P5, Group 1: source 1, new prediction 4, original 4, compact 4, fold median 4.

Each example is an actual paired prediction, not a fabricated transcript. `paired_predictions.json` includes every rating, agreement and absolute error. The frozen inputs contain overall conversational measurements and some observer notes, but not a complete verified timestamped conversational-evidence package for every rating. Private free-text notes may identify participants and are intentionally not copied here. Without reliable linked turns and independent review, this audit cannot attribute any disagreement to sarcasm, assertiveness/aggression confusion, defensiveness, code-switching, transcription errors or missing surrounding context. Those are untested hypotheses, not discovered failure groups.

## Measurable constraints

Missing feature counts across the forty participant-session examples: {'open_question_ratio': 23, 'unhedged_proposal_ratio': 26}. Imputation uses training data only and records missingness; a missing response latency is not an observed zero. Source annotations lack systematic opportunity, observer confidence and independent review. General speech markers are weak proxies for contextual role objectives. The model does not encode a stable psychological trait. Transcript quality and speaker mapping need separately labelled audits before claiming a cause of disagreement.

## Hypotheses and distinguishing checks

An interaction-context failure would require reviewed preceding/following exchanges matched to the same observation. A transcription/language failure would require human audio verification and language slices. A rubric-ambiguity failure would require independent psychologists scoring the same events before adjudication. Unequal opportunity would require an event/opportunity record. None of those missing measurements was invented or retroactively assigned in this experiment.
