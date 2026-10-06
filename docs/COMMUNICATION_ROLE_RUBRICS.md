# Role observations and opportunity rules

The software defines observable behaviors for every pilot role. These are local classifier proposals, not validated assessments of skill. Automatic types remain unavailable until the exact semantic version and model digest pass independent review. Shared acoustic measurements remain available when interpretation is unavailable.

## Role coverage

| Role | Semantic observations | Shared timing and acoustic context |
| --- | --- | --- |
| General | Acknowledgement, clarification, structured explanation | Speaking share, turn length, overlap, pace, response gaps |
| Leadership | Clear instructions, acknowledgement, counterargument acknowledgement | Contribution space and turn-taking |
| Sales | Discovery questions, responses to objections | Balance, explanation length, pace |
| Teaching | Structured explanations, unexplained jargon, adaptation after explicit confusion | Space for questions and pace |
| Law | Direct answers, supported reasoning, cross-questions | Response gaps, turn length, user-entered pressure context |
| Debate | Counterargument acknowledgement, concessions, concise rebuttals | Floor management and overlap |
| Negotiation | Clarification, concessions, counterargument acknowledgement | Contribution space and turn-taking |
| Medicine | Concern acknowledgement, unexplained jargon, structured explanations | Balance and space for concerns |
| Student | Structured explanations, direct answers | Pacing, turn length, question opportunities |
| Presentation | Structured explanations, direct answers, unexplained jargon | Pacing, turn length, audience-question opportunities |

`backend/communication/behaviors.py` contains the operational definitions. A clear instruction specifies an action and who performs it. A structured explanation contains a main point and a reason or example. Supported reasoning explicitly connects a claim with a reason; it does not establish that the claim is true. A concession explicitly accepts a point or narrows a position. Jargon proposals must abstain when the audience's familiarity is unknown. Audience understanding is never inferred from these observations.

Defensive responses require explicit criticism followed by a reply that shifts blame or evades the concrete issue. This labels the cited exchange only; it does not establish a personality trait. An overlap remains a separate measured event and cannot establish interruption intent.

## Opportunity denominators

Ordinary behavior rates count distinct classified wearer turns divided by all nonempty wearer turns in the supplied transcript windows. Types must be individually enabled; an enabled objection detector cannot supply zeros for an unavailable acknowledgement detector. Counts use the complete successful classifier pass before the retained event examples are capped.

Paired behavior rates require both the response type and its opportunity type to pass validation:

| Response | Required opportunity |
| --- | --- |
| Direct answer | Another speaker's question |
| Adaptation | Another speaker's explicit confusion |
| Counterargument acknowledgement | Another speaker's disagreement |
| Concise rebuttal | Another speaker's disagreement |
| Defensive response | Another speaker's criticism |
| Objection response | Another speaker's objection |
| Concern acknowledgement | Another speaker's concern |

Each pair cites the other speaker's turn first and the wearer's immediately following original-time turn second. The response must begin within 0–30 seconds after the preceding turn ends. Overlapping responses, intervening turns, long gaps, and missing wearer text abstain from this denominator. These conservative pilot rules omit some real opportunities rather than assigning them without support. A concise rebuttal additionally requires at most 40 original transcript words; truncating the prompt cannot bypass that check.

If there are no qualifying opportunities, the rate is absent. A measured zero requires an enabled opportunity detector, an enabled response detector, a complete classifier pass, and at least one qualifying opportunity. `semantic_counts` stores the numerator, denominator, and up to three original timing references for each rate. These are derived summaries, not another full transcript. Small opportunity counts remain a limitation; rates are pilot heuristics without calibrated uncertainty.

## Interpretation, correction, and retention

The interpreter receives user-entered context and role alongside bounded redacted turn windows. All of that content is untrusted data. Windows contain at most 20 turns and share one boundary turn so an adjacent response can be classified across the boundary. Duplicate events are removed, and exhausted output windows cause interpretation to abstain. Speech models are released before local interpretation.

All event references must exist. Paired response types require two ordered references; other events use one or two. At most 12 event examples and two excerpts per example survive processing. Each excerpt contains at most 200 characters. Counts are computed before that cap, and rate evidence retains bounded timing references even when the corresponding excerpt is unavailable.

Wearer corrections override automatic events and invalidate reports and frozen goal references. A correction reviews retained excerpts, not the deleted complete transcript, so it removes automatic semantic rates for that conversation. Acoustic measurements survive. An empty correction is not evidence that a behavior never occurred. Corrections accept the original `evidence_id` field or an `evidence_ids` array for a paired event.

## Versioned evaluation and reports

The current contract is `communication-semantics-2`, the validation manifest is `communication-semantic-validation-2`, and role advice is `communication-rubrics-2`. Evaluation datasets must declare `analysis_version: communication-semantics-2`; manifests also bind that version and the model digest. Old prompt evaluations cannot activate the new detectors.

The existing 50-exchange, all-role, 90% precision, and ten-prediction requirements apply independently to every event type. Evaluate paired opportunities and responses independently; either failing leaves the associated rate unavailable. Synthetic unit tests verify the contract and abstention rules, not classifier accuracy. See [the pilot runbook](COMMUNICATION_COACH.md) for the evaluation command.

Rates feed the existing session-weighted, comparable-cohort baseline and three-later-session recurring-pattern rules. A goal can be selected from observed baseline metrics and freezes its pre-goal reference. Reports include role coverage as observed or unavailable, counts, original timing, prior comparison, a possible effect, uncertainty, and a practical adjustment. There is no aggregate communication score. See [architecture](COMMUNICATION_ARCHITECTURE.md) and [implementation status](IMPLEMENTATION_STATUS.md).
