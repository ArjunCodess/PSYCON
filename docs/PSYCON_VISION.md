# PSYCON vision and reasoning

This is the current product direction for personal communication coaching. The [root README](../README.md) gives the overview, [architecture](COMMUNICATION_ARCHITECTURE.md) defines implemented behavior, and [status](IMPLEMENTATION_STATUS.md) records the gaps. Earlier research documents remain evidence for their original experiments; they do not validate this product.

## The problem and the intended outcome

People can review a recording and notice an isolated moment, but connecting several conversations is harder. They may speak differently under pressure, explain too much during a discovery call, respond quickly to disagreement, or leave more space after practicing a goal. The useful question is what repeatedly changes in a comparable context, what evidence supports that observation, and what small adjustment is worth trying.

PSYCON's intended first milestone is one person with several consented conversations: identify their speech, form a baseline, explain a recurring measured change with examples, suggest an adjustment, and compare later conversations with earlier data. The recordings pilot establishes the software path before a wearable makes capture continuous. Two independent wearers must complete that flow before the pilot is treated as released.

The wearable is an input device for that same history. It is not a separate interpretation system. A later wrist stream may add synchronized research context, but stress predictions must not decide that a person was defensive, dishonest, rude, or failing to communicate.

## The theoretical model

The system uses a within-person, longitudinal comparison. Individuals differ in habitual pace, pitch, contribution level, profession, and capture conditions, so a population-wide threshold is a weak basis for personal advice. Comparable personal history offers a reference without turning differences between people into rankings.

Three layers support a report:

| Layer | What it establishes | What it cannot establish alone |
| --- | --- | --- |
| Measured speech observations | Timing, rate, level, pitch, clean wearer speech, and simultaneous speech from the supplied recording. | Intent, psychological traits, listener understanding, or social harm. |
| Contextual interpretation | A reviewed event such as a question, acknowledgement, clarification, objection, or disagreement tied to specific text intervals. | A diagnosis or an interpretation unsupported by the exchange. |
| Longitudinal comparison | Repeated deviations from an earlier reference in a comparable cohort. | A causal effect of coaching or a universally desirable communication style. |

The statistical pilot starts with medians and median absolute deviation over session summaries. Each session contributes one value, so a long recording does not outweigh several independent conversations. The initial reference requires five eligible conversations across three days and 30 minutes of clean wearer speech. These values are configurable pilot rules, not validated psychological thresholds.

At least three later independent conversations must support a change in the same direction beyond the robust deviation threshold. A single overlap or unusually long turn cannot establish a recurring pattern. A different microphone creates a different cohort, so the system does not mistake recording gain for a meaningful loudness change.

Context is entered by the wearer rather than guessed as ground truth. The implemented cohort uses language, conversation type, microphone, and setting. Topic, counterpart relationship, and objective provide additional context but do not yet create fully modeled opportunity categories. Sparse cohorts remain unavailable.

## Coaching and the professional roles

Every recommendation should connect the observation, its setting, the earlier reference, supporting examples, a possible effect, uncertainty, and one practical adjustment. The wearer can inspect the retained excerpt and the original timing reference, then correct an event or the conversation context. Corrections take precedence over model interpretations.

| Role | Intended coaching questions |
| --- | --- |
| General | Is the contribution clear, concise, and balanced, with space to listen and respond? |
| Leadership | Are instructions clear, dissent invited, and others' contributions acknowledged? |
| Sales | Is the conversation discovering needs, balancing participation, and responding to objections? |
| Teaching | Does an explanation have structure, make jargon understandable, and adapt after confusion? |
| Law | Are answers direct, reasoning supported, and responses structured during cross-questioning? |
| Debate | Are counterarguments acknowledged, rebuttals concise, and the floor managed fairly? |
| Negotiation | Are interests clarified, valid points acknowledged, and concessions handled explicitly? |
| Medicine | Can concerns be expressed, explanations understood, and next steps acknowledged? |
| Student and presentation | Are main points structured, pacing appropriate, and audience questions addressed? |

The implementation provides every role lens over shared measurements and practice suggestions. It does not yet validate detectors for every question in this table. In particular, supported reasoning, explanation structure, jargon appropriateness, concessions, and audience understanding need additional operational definitions and annotated evidence. A role label must never imply that those capabilities already exist.

Goals use a frozen pre-goal reference. Later comparisons require comparable sessions and enough measured opportunities; the current implementation uses available metric summaries and clean wearer turns, which is an initial approximation. Better role-specific opportunity denominators require reviewed exchanges. Reports describe measured change without claiming that coaching caused it.

## Local AI and the evidence boundary

Speech recognition, diarization, verification, and LLM interpretation run locally. The initial interpreter is Ollama with `qwen3.5:4b`, pinned to the downloaded model digest. The LLM sees bounded, redacted turn windows and must cite supplied evidence IDs. Transcript instructions are untrusted conversation content.

Structured output and correct references establish traceability, not semantic accuracy. Automated semantic types remain unavailable until a matching evaluation reviews at least 50 independent exchanges spanning all roles and reaches at least 90% precision for each enabled type. The validator also requires at least ten displayed predictions per enabled type. Missing inference, invalid references, or a digest mismatch leave measured results and rule-based coaching available.

The context API is a small authorized representation for another AI application. It contains supported patterns, goals, dates, counts, uncertainty, and current context. It excludes recordings, voice embeddings, evidence text, and other people's identities. It should help another application personalize its assistance without receiving a person's complete communication archive.

## Consent, retention, and user control

The wearer owns access to the personal history. A reviewer needs an explicit, revocable grant, and an AI application needs a context grant. Research ratings remain separate from automated coaching. Participant numbers in different videos do not establish cross-session identity; an operator must confirm a source-to-profile link and the existing source must satisfy its consent and withdrawal rules.

Successful processing deletes new personal raw media, temporary files, and full transcripts. Bounded redacted excerpts and derived timing and measurements remain until deletion. Failed raw uploads expire after 24 hours. Enrollment embeddings are encrypted, and temporary media belongs outside research backups. Redaction is conservative rather than a guarantee that sensitive text has been removed.

Corrections and deletion invalidate affected reports and frozen goals. Surviving derived data can rebuild a report, but an extractor cannot be rerun against deleted audio. A new recording is needed for a new extraction. Shared research recordings retain their existing policy; deleting a personal link does not silently delete a recording used by other participants.

## What comes after the first pilot

The next evidence milestone is the two-person private pilot and independently reviewed semantic dataset. After that, continuous physical ESP32 capture must demonstrate sustained transport, reconnect recovery, loss reporting, clock quality, power behavior, and usable wearer attribution through the same coaching records.

All-day capture requires measured battery life, wearer and bystander consent controls, safe pause behavior, reliable session segmentation, and stronger operational recovery. Real wrist acquisition follows as optional synchronized research context. Hosted worker connections and a public personal product are separate later milestones. The local software build does not establish any of these release gates.
