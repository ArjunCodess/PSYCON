# Psycon: complete presentation content

Updated 13 October 2026 from the verified maximum-defensible audit. Exactly 25 content slides follow. A separate opening title slide and closing thank-you slide are excluded. All text beneath each numbered heading is proposed slide text, including captions. These are AI-assisted preparation drafts for the students to verify, develop in their own words and check against the applicable fair rules. Results describe the source-score pilot, not independently validated personality prediction. No poster is included.

## 1. Abstract

Psycon investigates whether conversation measurements predict contextual observer ratings and support evidence-linked reports.

The pilot uses 423 ratings from 40 participant-session examples across nine recordings and five known connected groups. Compact development reached 62.19% agreement on the common 402 ratings. New nested pooling reached 65.67%, exactly matching training-mode predictions and reducing score-3 recall, so it was not promoted.

These are retrospective development results. Independent rater reliability, final testing, history benefit and 85% agreement remain unestablished.

## 2. Background: behavior depends on the situation

- A person's contribution changes with the topic, assigned role, other speakers and opportunity to respond.
- Speaking for a short time can reflect a limited opportunity, a concise response or a recording error. Duration alone cannot distinguish these explanations.
- A behavioral observation therefore needs a defined event, its preceding context and the participant's response.

Psycon preserves this context so that measurements and interpretations can be checked against the recording.

## 3. Psychology behind Psycon

- Conversation is a social process. Turns, responses and feedback provide context for interpreting what a participant does.
- Observable quantities include attributed speaking time, turn duration and questions or proposals detected by rules.
- Anxiety, motivation and stable personality are not directly measured by these quantities.
- Our project-defined rubric still needs independent reliability and validity studies.

The psychological aim is to study behavior in context while keeping observation separate from interpretation.

## 4. Research gap and contribution

Speech recognition produces words, and diarization estimates who spoke when. Neither step establishes the meaning of a participant's behavior.

Psycon connects each participant-session to timestamped exchanges, versioned observations, known source relationships and inspectable model outputs. Corrections can invalidate dependent datasets and predictions.

The present contribution is this measurement and evaluation workflow. The pretrained speech and language models are existing tools; a new psychological discovery has not been demonstrated.

## 5. Research question and hypotheses

**Main question:** Can speaker-specific conversational measurements predict independently reviewed contextual behavior better than a simple reference, and can eligible earlier history improve communication reports?

- **H1:** Measurements and context reduce held-out ordinal rating error relative to the training-median baseline.
- **H2:** Earlier personal history improves blinded report grounding and usefulness without increasing unsupported claims.

The current source-score pilot explores part of H1. H2 remains untested because the demonstrated report has no eligible earlier history or blinded usefulness assessment.

## 6. Defining behavior before predicting it

The A-T framework organizes contextual observations into five areas:

| Items | Operational area |
|---|---|
| A-D | Tracking the discussion |
| E-H | Structure of contributions |
| I-L | Turn-sharing and reciprocity |
| M-P | Changes following a challenge |
| Q-T | Delivery or participation changes |

These are project-defined areas, not validated personality factors. Imported version-5 source targets G, I and P1-P12 are retained separately; they do not establish full A-T coverage.

## 7. Why zero, N/O and missing must stay separate

- **A numeric score** records the source form's ordinal observation on its 0-4 scale.
- **Zero** requires absence despite a relevant opportunity. It cannot be inferred from a blank answer.
- **N/O** records insufficient opportunity or observational support.
- **Missing** means that an answer was not supplied.

We preserved these states. Replacing N/O or missing entries with invented scores would change the research target and create unsupported evidence.

## 8. Human reference data and its limits

School psychologists supplied observation reference material. Ten private scanned bundles contain 228 image-only pages, and 76 version-5 forms were imported.

| Answer state | Count |
|---|---:|
| Numeric | 750 |
| N/O | 1,662 |
| Missing | 20 |
| Total | 2,432 |

The imported answers lack the opportunity, confidence, structured evidence and independent review needed for strict behavioral validation. They are source scores, not an established psychologist consensus or diagnostic ground truth.

## 9. Participants, repeated recordings and overlap

- The broader benchmark contains 85 person-recording slots across eleven recordings. Slots are not unique people.
- Nineteen author-supplied identity links connect 34 participant records into fifteen known people. Unknown overlap may remain.
- The training snapshot contains 40 participant-session examples from nine recordings in five known connected groups.
- Repeated participants and connected recordings stay together during evaluation.

The 423 training labels are item observations attached to these examples, not 423 independent participants.

## 10. Ethics, privacy and evidence provenance

- Nine private signed sheets document voluntary group-discussion participation and the right to stop.
- We confirm that recording and model-training permissions, applicable parental permission and prior approval are documented in the complete records. Those details are outside the supplied photographs and have not been independently checked.
- Private recordings, completed forms, identities and signatures are excluded from the public repository and these slides.
- Source observations, model predictions and generated interpretations retain separate provenance.
- Corrections and withdrawals can invalidate derived artifacts rather than leaving outdated predictions in use.

Software controls support accountability. They do not replace prior approval, voluntary participation or independent human review.

## 11. Pipeline of the software

**Recording → normalization → diarization → transcription → conservative attribution → conversational measurements → reviewed/source-score datasets → model outputs → bounded report**

Each stage records its inputs, version and processing status. Ambiguous words can remain unattributed, and failed or stale outputs are withheld.

The earlier audiovisual benchmark produced 57 ready Psycon profiles from 85 marked slots, compared with 51 for each guarded Nemotron mode. This measures processing coverage, not correct identity, behavioral accuracy or psychological validity.

## 12. What the software actually measures

- **Speaking share:** attributed speaking time divided by total exclusive attributed speaking time.
- **Speech rate:** attributed word count divided by attributed speaking duration, expressed as words per minute.
- **Turn duration and response latency:** timing estimates derived from attributed turns and gaps.
- **Question, proposal and acknowledgement indicators:** rule-based text proxies that need contextual review.

Feature denominators were corrected in metadata version 1.0.1. No validated ideal range is supplied; these measurements cannot independently establish confidence, leadership or personality.

## 13. Training and evaluation methodology

1. Freeze existing source labels, measurements and known groups.
2. Omit one known group in each outer evaluation fold.
3. Use only the remaining groups for inner selection, imputation and scaling.
4. Fit the selected procedure on that outer training partition and predict the omitted group.
5. Compare it with a reference fitted from the same training labels.

These analyses were developed after earlier results had been examined. Nested splitting reduces direct selection leakage, but it does not create an untouched independent final test.

## 14. Model changes and training parameters

The compact reference tests four/eight-feature logistic, ridge, ordinal and depth-limited tree models. The new grid tests shared professional-target logistic/ordinal coefficients with target indicators, core/conversation/extended existing features and training-fold class weighting. G/I are fitted separately.

- Each outer fold holds out a known connected group; inner grouped folds choose the configuration and hyperparameters.
- Imputation and scaling use training data only; IDs, observer notes and annotation-selected windows are excluded.
- Inner agreement gains must preserve ordinal error and individual class recall.
- Only the nested challenger can pass the declared promotion gates; fixed outer diagnostics cannot choose a winner.

## 15. What the training/testing split means here

| Evidence | Status |
| --- | --- |
| Original final fitting | All 40 examples used for training |
| Independent final test | 0 examples |
| Outer development folds | Five known connected groups |
| Common paired cohort | 402 ratings, fixed by original predictions |
| Original abstentions | 21 of 423 |
| Other procedures | All 423 scored, with explicit reference fallbacks |

Nineteen documented identity links stay within folds, but 21 participant-session identities remain unresolved. Grouped development cannot establish participant-independent generalisation.

## 16. Results: every procedure against the baseline

| Procedure, common 402 ratings | Correct | Agreement | MAE | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: |
| Original grouped model | 230 | 57.21% | 0.562 | 30.33% |
| Compact procedure | 250 | 62.19% | 0.490 | 29.98% |
| Previous agreement-selection experiment | 247 | 61.44% | 0.498 | 29.10% |
| Fold training median | 259 | 64.43% | 0.460 | 29.64% |
| Fold training mode | 264 | 65.67% | 0.453 | 29.21% |
| New nested pooled procedure | 264 | 65.67% | 0.453 | 29.21% |

The new nested procedure exactly matches the mode reference. It selects references in four folds and pooled core logistic C=0.01 in one. The compact model remains the research reference because rare-class and mode-superiority promotion gates fail.

*Figure caption: All results use the same 402 ratings and remain retrospective development.*

## 17. Sensitivity: minority scores remain difficult

| Score | Common support | Compact recall | New nested recall |
| --- | ---: | ---: | ---: |
| 1 | 13 | 15.38% | 15.38% |
| 2 | 20 | 0% | 0% |
| 3 | 103 | 18.45% | 4.85% |
| 4 | 266 | 86.09% | 96.62% |

Score 0 has no observations. Across all 423 ratings, score counts 0-4 are 0,24,24,109,266. The challenger improves majority-score recall while losing score-3 detection. These are exact-rating recalls, not clinical sensitivity.

*Figure caption: Read agreement beside class-wise precision, recall and F1; pooled agreement can conceal minority failures.*

## 18. Error, uncertainty and target interpretation

On all 423 ratings, compact reaches 61.23% agreement and MAE 0.506; median reaches 63.36%/0.478 and mode/new nested selection 64.54%/0.470. These procedures have zero abstentions.

On the common cohort, compact/new balanced accuracy is 29.98%/29.21% and quadratic weighted kappa is 0.101/0.129. MAE assumes equal adjacent score distances; kappa uses squared ordinal distances.

The strongest fixed diagnostic reaches 67.16%/0.435 but predicts score 4 on 397/402 ratings and recalls only 1.94% of score 3. It is not an unbiased selected winner. Five-group bootstrap intervals are descriptive; the new procedure has zero paired gain over mode.

## 19. Example output after a real recording

**Attributed speaking duration:** 106.18 seconds  
**Speaking share:** 17.80%  
**Attributed speech rate:** 129.41 words/minute  
**Eligible earlier history:** 0 recordings

The bounded report states: "Speaking share: 17.80% across the complete attributed recording."

A cautious interpretation is: "Interpret this measurement in the discussion context and assigned role; it does not establish communication quality by itself."

The optional goal exercise is: "In your next decision-focused discussion, state one proposed decision, give its supporting reason, then invite a response."

The exercise is prewritten and untested. Linked transcript excerpts do not independently verify these full-recording quantities. The values do not establish a personality profile.

## 20. LLM inputs and personalization

The report input preserves selected transcript exchanges, recording context, measured features, exploratory predictions, provenance and the user's communication goal. Condition C can also include eligible earlier history and structured evidence.

- Exploratory source-score predictions cannot justify personality labels or coaching claims.
- Bounded generation copies supplied measurements and uses cautious statements rather than inventing norms.
- The example's exercise is transparent goal adaptation; its benefit is untested.
- A history-only helper changes only earlier history and refuses comparisons when it is unavailable.

No current result establishes more useful personalized answers.

## 21. Problems encountered and repairs

The frozen audit checked unique answer IDs, target/speaker alignment, scales, missing outputs, denominators, source hashes and known-link transitivity. Original, compact and previous agreement-selection predictions refitted with zero mismatches. No demonstrable implementation bug explains their metrics.

Six new regression tests cover grouping, training-only preparation, individual-class selection guards and paired uncertainty. The research suite passed 82 tests, with one media test skipped because ffmpeg was absent from its runtime PATH.

All unsuccessful comparisons remain recorded; source ratings and live models were unchanged.

## 22. Discussion: what the findings support

The pilot establishes an executable audit workflow, not reliable prediction of independently reviewed behaviour. The new procedure matches a population reference, while the higher fixed diagnostic largely predicts score 4. Compact remains the research reference without a superiority claim.

Unreviewed labels, unequal opportunities and unresolved identities prevent a numerical performance ceiling. Independent blinded re-rating and newly collected identity-resolved groups are required. No measured result supports 85%, a stable psychological trait, diagnosis or a communication benefit.

## 23. The next behavioral study

The next study must be able to challenge the interpretation:

- Independently check attribution, transcription and participant overlap.
- Collect contextual ratings with documented opportunity, confidence and timestamped evidence from independent raters.
- Freeze the model and primary outcome before collecting a fresh participant/source-disjoint evaluation sample.
- Compare ordinal error and minority-score recall against frozen median and mode references.
- Separately compare history-present and history-withheld reports with blinded, randomized usefulness and grounding assessments.

Poor rater agreement, no reference improvement or increased unsupported claims would challenge the hypotheses.

## 24. Future hardware and product direction

The product vision is voluntary, evidence-linked communication review that lets a user inspect and correct recording evidence.

Hardware remains future work. Ear firmware supports I2S audio capture; wrist readings are placeholders, and no tracked KiCad board or validated assembly exists.

Planned work includes a labelled 3D assembly, KiCad schematic/PCB, checked power protection, pin assignments, a bill of materials and bench measurements. Any physiology study needs separate approval and validation. Sensor changes cannot automatically be interpreted as emotions.

## 25. Acknowledgements and central references

We acknowledge the school psychologists who supplied observation reference material and the authors of the open-source speech, diarization and analysis tools. AI assisted coding, analysis and draft preparation; student contributions and actual mentorship must be described from project records.

- Sacks, Schegloff & Jefferson (1974). Turn-taking. doi:10.2307/412243.
- Cronbach & Meehl (1955). Construct validity. doi:10.1037/h0040957.
- Cohen (1968). Weighted agreement. doi:10.1037/h0026256.
- Radford et al. (2022). Speech recognition. arXiv:2212.04356.
- Kapoor & Narayanan (2022). Leakage in ML-based science. arXiv:2207.07048.

These sources motivate methods and limitations; they do not validate Psycon's rubric or effectiveness.

Aggregate source: `docs/report_assets/maximum-defensible-summary.json`; audit details: `docs/research/maximum-defensible-2026-10-13/submission_results.md`. Private individual predictions remain local.
