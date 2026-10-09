# Behavioral dataset and evaluation protocol

The primary research objective is to predict eligible contextual A-T observations from a participant's audio/transcript-supported talking patterns and discussion context, then evaluate agreement with reviewed human ratings. Descriptive feature/rating correlations do not establish causation or psychological validity. Archetype choices remain optional reference goals, never prediction targets or labels. Independently annotated communication behaviors retain their separate task definitions.

The canonical observation unit is one reviewed participant in one recording, with separate per-target labels. Supporting evidence windows do not create independent examples. `at-4.0` preserves the paper marksheet and interpretation source hashes; `communication-1` uses the independent operational guidelines. Observer ratings, self-report, independent reviews, adjudications and predictions remain distinct. Missing, N/O and zero are separate states.

A target needs documented training consent, a confirmed participant-to-speaker mapping, completed processing, reviewed source ancestry, an independent answer review, fair opportunity and confidence. Positive scores need timestamped evidence. K and M-T require event/response windows; Q-T additionally require an earlier same-session baseline. S is unavailable until supported vocal-change window features exist. Visual-only T answers remain saved but are ineligible; supported participation change can be eligible. Communication traits need at least two nonoverlapping contextual moments. Readiness lists exclusions without discarding saved answers.

## Freeze and splits

`conversation-2` includes speaker-specific conversational measurements, supported event-window measurements, recording context categories and uncalibrated transcript confidence. Names, faces, identity embeddings, physiological inputs, reviewer IDs, class labels and target answers are not predictors. Versioned snapshots capture the rubric definition/hash, exact answer revisions, reviewer, adjudication, confidence, opportunity, consent, mapping revision, feature values, source hashes, reviewed source ancestry, seed and split assignments. Their manifest and materialized examples cannot be updated.

For unseen-participant studies, confirmed people, exact recording hashes, original-video links and reviewed excerpt/derivative ancestry connect whole sessions. A connected component cannot cross development, validation, final evaluation or reference roles. Development components receive deterministic train/validation/test assignments when separate held-out roles have not been supplied. Longitudinal studies require explicit strictly forward role dates. Historical baselines use only earlier eligible independent recordings and exclude other analyses of the target recording; the marksheet's same-session event baseline is separate.

Unreviewed ancestry is excluded. Exact hashes cannot identify every independently re-encoded excerpt, so the source review is a required human check. No automatic identity or acoustic fingerprint establishes source independence.

## Fit and evaluate

Each head needs at least 12 training participant/session examples, three independent training groups and two observed score classes. The baseline is the training median. The fitted alternative is regularized multinomial logistic regression, explicitly an approximation to ordinal scores. Imputation, missing indicators and scaling fit only on training rows. Validation chooses regularization from the recorded candidates; final evaluation never selects a candidate.

The operational evaluated state requires at least three validation and three final-evaluation examples and lower MAE than the median baseline in both sets. This small engineering gate does not establish construct validity, population generalization or adequate scientific power. Per-target records include MAE, macro-F1, balanced accuracy, confusion, quadratic kappa where defined, uncalibrated Brier score, coverage and actual counts. Group-bootstrap MAE intervals and context slices require at least three independent held-out groups; otherwise they say unavailable. Probabilities are uncalibrated.

Artifacts contain portable JSON coefficients and training-only transforms. PostgreSQL records source snapshot, source-code hash and revision, dependency versions, feature schema, task/rubric, configuration, evaluations and local artifact hashes. Loading verifies hashes and compatibility. Fitting does not activate a model. Activation records an operator and reason; exploratory activation needs acknowledgment. Rollback selects a previously deployed compatible version. Corrections, mapping/source changes and withdrawals invalidate dependent snapshots, predictions and model eligibility; deletion removes affected private copies and weights under the retention policy.

## Separate research experiments

Evaluate the supervised predictor against held-out human annotations independently of the matched transcript-only A, structured-context B and full-PSYCON C comparison. B and C receive identical frozen supervised outputs, versions, uncertainty, abstention and evidence references; C adds historical personalization and transparent reference comparisons. Human labels never become predictions or AI-generated training annotations. No fixture metric or selected archetype goal is human ground truth.

The current real database contains retained recording analyses, but no supplied consented, reviewed human training labels. Real supervised results remain unavailable. Synthetic PostgreSQL tests demonstrate implementation behavior only.
