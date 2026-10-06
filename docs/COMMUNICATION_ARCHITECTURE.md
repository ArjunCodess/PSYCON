# Communication architecture and API

This document describes the implemented English recordings pilot. [Vision](PSYCON_VISION.md) explains the intended product, [operations](COMMUNICATION_COACH.md) gives runnable commands, and [status](IMPLEMENTATION_STATUS.md) distinguishes implementation from validation.

## Components and boundaries

`backend/app.py` registers `CommunicationService`, `PostgresCommunicationStore`, `SourceAdapters`, the communication API, and `/coach` alongside the existing dashboard and group console. The communication service is independent of the large group-observation service; source adapters call existing services through their established contracts.

| File | Responsibility |
| --- | --- |
| `backend/communication/store.py` | PostgreSQL document persistence, profile-scoped queries, process-wide advisory locks, and a deterministic test store. |
| `service.py` | Profiles, consent, encrypted enrollment jobs, uploads, processing, corrections, grants, goals, derived history, context, and cleanup. |
| `analysis.py` | Existing speech adapters, clean wearer intervals, session metrics, anonymous timing, bounded text evidence, and GPU release. |
| `sources.py` | Explicit group/device source descriptions, original-timeline group imports, and continuous PCM assembly. |
| `longitudinal.py` | Eligibility, comparable cohorts, robust summaries, snapshot IDs, prior references, and repeated deviations. |
| `rubrics.py` | Versioned role focus and practical metric/role adjustments. |
| `behaviors.py` | Observable role definitions, complete-pass behavior counts, and explicit response-opportunity denominators. |
| `llm.py` | Local endpoint restrictions, digest checks, bounded interpretation, evidence validation, and semantic release gates. |
| `routes.py` | Scoped bearer access and the versioned HTTP interface. |
| `runtime.py` | Environment loading, model pinning, local account provisioning, web startup, and worker startup. |
| `backend/static/coach.js` | In-memory browser token, forms, evidence rendering, corrections, grants, goals, and context download. |

## End-to-end lifecycle

1. **Provision and consent.** An operator or local account command creates a profile and returns a new bearer token once. PostgreSQL stores only its hash. The wearer selects a role and explicitly permits processing.
2. **Queue enrollment.** Three clips enter an encrypted spool file. A durable enrollment document records its generation and status. The worker decodes the clips and reuses the existing 5–10 second enrollment checks and SpeechBrain ECAPA embeddings. A newer enrollment, revoked consent, or deletion prevents an older job from committing its result.
3. **Queue a recording.** The API checks consent and enrollment, validates a timezone-aware timestamp that is not in the future, normalizes context, and hashes the original bytes. Its conversation ID is SHA-256 of profile ID plus the media hash. The same bytes uploaded to the same profile return the existing conversation, including when retries occur.
4. **Analyze on the worker.** Quality analysis precedes transcription. Whisper transcribes usable regions with source offsets; Community-1 produces regular and exclusive turns; SpeechBrain matches the enrolled wearer conservatively. Clean wearer intervals subtract simultaneous other-speaker speech and intersect usable quality windows.
5. **Interpret bounded text.** Speech models are released before Ollama runs. Anonymous turn windows contain at most 20 excerpts, each capped at 300 characters, with an 8K token context and a bounded output. Validated semantic events retain only cited excerpts; the full transient transcript is discarded.
6. **Commit and clean.** The worker rechecks the conversation revision and active consent before writing derived analysis. Completed personal raw files are deleted, and deletion completion is audited. Failed processing retains encrypted raw data for at most 24 hours.
7. **Build history and coach.** Eligible session summaries form comparable cohorts and deterministic snapshots. Later comparisons and repeated deviations feed role-specific coaching. Corrections rebuild history and invalidate a goal whose frozen meaning changed.
8. **Share or delete.** Scoped grants authorize only their permitted reads. Context exports are generated from current surviving records. Deletion removes personal analysis before raw cleanup, so locked files remain recoverable cleanup work without keeping the conversation visible.

## Persistence and version lineage

Additive schema migrations 100 and 101 introduce `communication_records(kind, id, profile_id, body JSONB)`, a composite primary key, a profile/kind index, and a kind constraint. Existing research tables are preserved. The document kinds are:

| Kind | Stored information |
| --- | --- |
| `profile` | Label, role, consent, token hash, revisions, encrypted embedding, enrollment generation/status, and revocation. |
| `enrollment` | Durable job identity, generation, creation time, state, and failure class; clips remain in the encrypted spool. |
| `conversation` | Source identity/hash, original date, context, revision, job state, raw state, and derived analysis. |
| `link` | Explicitly confirmed source/profile association and confirmation time. |
| `baseline` | Latest derived history report; it is a rebuildable cache rather than a complete archival snapshot log. |
| `goal` | Selected metric/direction and frozen pre-goal cohort references. |
| `grant` | Scope, token hash, expiry, and revocation state. |
| `audit` | Minimal action, resource ID, profile ID, and completion date. |

Observations use `communication-observations-1`, baselines use `communication-baseline-1`, history uses `communication-history-1`, rubrics use `communication-rubrics-2`, semantic analysis uses `communication-semantics-2`, semantic validation uses `communication-semantic-validation-2`, and export uses `psycon-context-1`. Baseline `snapshot_id` hashes source IDs, revisions, media hashes, context, dates, metrics, analysis/model versions, and eligibility rules. Identical inputs reproduce the same ID; corrected support creates a different ID.

The source SHA-256 and extractor/model metadata live on each conversation analysis. Its evidence and timing rows inherit that provenance and store source intervals. Anonymous attributed-word records retain timing and speaker labels, not a full persisted transcript. Device synchronization and group source lineage remain available through the existing source records.

Profile-scoped PostgreSQL session advisory locks serialize mutations across processes. A global communication worker lock prevents two communication jobs from using the GPU simultaneously. Deploy one inference worker overall so group and communication processing also remain sequential; this lock does not independently coordinate arbitrary additional group workers. Locks are reentrant within a thread, allowing deletion to invoke nested cleanup safely.

## Source adapters

Personal uploads accept WAV, MP3, and OGG up to 32 MB. The encrypted spool is distinct from S3 research objects and excluded from the repository and Docker build context. File-byte deduplication does not identify independently re-encoded copies as the same conversation; source linking and pilot review must still establish independence.

Group imports require recorded source consent, a non-withdrawn participant, a current ready guarded PSYCON profile, and explicit operator identity confirmation. Shared original PCM supplies acoustics. Existing transcript words are mapped back to source time before import. Assigned windows omit uncertain intervals and do not establish complete turn boundaries, so response gaps, pauses, mean turn duration, and candidate interruption rates abstain for this source. A numbered participant is never inferred to be the same person in another recording.

Device imports require a complete session whose metadata explicitly names `communication_profile_id`. One 16 kHz PCM device is assembled in synchronized timestamp order. Mixed devices, missing synchronization, uncertainty above 5 ms, and gaps or overlaps above 5 ms are rejected. The nominal Protocol v2 period is 62 or 63 integer microseconds; assembly uses the declared 16 kHz rate for actual sample duration. Packet boundaries do not become conversation turns. Interruptions in capture require separate sessions rather than silently stitched audio.

## Observations and interpretation

Current wearer measurements include usable speech seconds, speaking share over recording duration, mean retained turn duration, words per usable speech minute, vocabulary diversity, mean observed pauses/response gaps, pitch mean/variation, RMS dBFS, candidate overlap entries per recording minute, and vocal-jitter estimates. Clean acoustics exclude other-speaker overlap. Pitch and level are inspectable observations but are not currently metrics used to generate recurring coaching patterns.

Candidate overlap entry requires at least 0.5 seconds in the new wearer turn and at least 0.2 seconds overlapping an already speaking counterpart. It is a timing candidate, not a validated interruption judgment. Retained overlap intervals make that distinction inspectable. Quality windows, anonymous turns, and word timing remain derived records.

The local interpreter accepts only explicitly allowed local HTTP hostnames. It checks `/api/tags` against the configured model and digest before inference. Output must be an `events` array with supported types and existing evidence IDs. The [role definitions](COMMUNICATION_ROLE_RUBRICS.md) cover exchange events, instructions, explanations, jargon, discovery, reasoning, concessions, and paired responses. A validation manifest must match the model digest and semantic version, cover every role, contain at least 50 unique reviewed exchanges, and support at least ten predictions with 90% precision for each enabled type. Types that fail remain unavailable.

Malformed output, exhausted output windows, invalid evidence, unreachable inference, invalid manifests, and model mismatch return an unavailable semantic state without deleting measured results. There is no cloud fallback. The interpreter receives untrusted user context and one overlapping boundary turn between windows. Complete enabled-type counts are computed before capping retained examples. Paired rates require both enabled types and a consecutive other-to-wearer opportunity within 30 seconds; missing opportunities remain absent. Human event corrections reference retained evidence IDs and replace model events, removing semantic rates because partial excerpts cannot establish full-session absence. The first six wearer-turn excerpts and at most 12 semantic events with up to two cited excerpts each are retained. Redaction is heuristic and may remove ordinary capitalized words or miss sensitive content.

## Baselines, reports, and goals

Eligibility requires a complete conversation, verified wearer identity, usable quality, English context, and a source date no later than the present. Language mismatch prevents baseline use. Cohorts are `(language, conversation_type, microphone, setting)`; topic and relationship do not currently define separate statistical cohorts.

The first eligible prefix meeting 5 conversations, 3 UTC calendar days, and 1800 usable speech seconds forms the comparison reference. A metric needs observations in at least five reference sessions. Each session contributes one value. The baseline stores median, median absolute deviation, count, source IDs, version, and snapshot ID. Later sessions never enter their own earlier reference. Corrections, deletions, or newly added older recordings can change a rebuilt reference and its snapshot ID.

For each later measurement, the deviation threshold is `max(2 × 1.4826 × MAD, metric_floor)`. Floors are 0.1 for speaking share and event rates per turn, 3 seconds for turn duration, 20 words/minute for pace, 0.3 seconds for gaps and pauses, and 0.5 candidate entries/minute. At least three later conversations in the same direction are required. These heuristics establish neither diagnostic thresholds nor calibrated probabilities.

Reports separate observations from possible effects and adjustments. Patterns carry context, reference statistics, supporting conversation IDs/dates/values, retained intervals, evidence counts, and uncertainty. Shared measurements and defined role behaviors support each role lens. Automatic semantic types remain unavailable until their exact-version evaluation passes.

Goals freeze the current ready pre-goal baseline and require at least five reference observations of their metric. Later comparison needs three comparable eligible conversations occurring after goal creation and exposing that metric. Corrections/deletion mark existing goal references invalid rather than silently replacing them. Paired semantic rates count qualifying questions, disagreement, criticism, objections, confusion, or concerns followed by a consecutive wearer response. Both event types need validation, and a missing opportunity leaves the rate absent. The [role guide](COMMUNICATION_ROLE_RUBRICS.md) defines these conservative rules.

## HTTP interface

Every personal route is under `/api/v1/communication` and uses `Authorization: Bearer <token>`. Missing/revoked credentials return 401, disallowed scope returns 403, missing/foreign conversations return 404, and invalid requests return 400. Operator routes use the existing operator authentication. Personal routes do not use its local development bypass.

| Method and path | Scope | Input/result |
| --- | --- | --- |
| `POST /profiles` | Operator | `{role, label}`; returns newly issued wearer token and ID. |
| `POST /source-links` | Operator | Explicit confirmed group/device source, profile ID, session ID, context, and group slot when applicable; returns queued conversation. |
| `GET /me` | Owner, reviewer | Profile state, enrollment availability/status, and access scope; no embedding/token hash. |
| `PATCH /me` | Owner | `{role, consent}`; updates preferences and invalidates derived references. |
| `DELETE /me` | Owner | Revokes access, removes enrollment and personal histories, and queues failed cleanup. |
| `POST /me/enrollment` | Owner | Multipart `clips` repeated three times and `consent=yes`, at most 10 MB; returns 202 queued. |
| `DELETE /me/enrollment` | Owner | Cancels pending generations and removes embedding/raw clips. |
| `GET /conversations` | Owner, reviewer | Processing status, original context, derived measurements, and retained evidence. |
| `POST /conversations` | Owner | Multipart `audio`, JSON `context`, timezone-aware `occurred_at`; returns 202 queued/existing. |
| `PATCH /conversations/{id}` | Owner | Completed conversation context and/or `{events:[{type,evidence_id}]}` corrections. |
| `POST /conversations/{id}/retry` | Owner | Requeues a failed conversation while its raw data still exists. |
| `DELETE /conversations/{id}` | Owner | Removes personal conversation and rebuildable dependencies. |
| `GET /history` | Owner, reviewer | Cohort progress, snapshot references, comparisons, and recurring role reports. |
| `GET /goals`, `POST /goals` | Owner; reviewer reads | New goal takes `{metric,direction}`; reads include later comparisons. |
| `GET /grants`, `POST /grants` | Owner | Scope is `reviewer` or `context`; new token is returned once, expires after seven days. |
| `DELETE /grants/{id}` | Owner | Immediate grant revocation. |
| `GET /context` | Owner, context | Current `psycon-context-1` export without evidence excerpts, biometric data, or other identities. |

Required context keys are `language`, `conversation_type`, `microphone`, and `setting`. Optional `topic`, `counterpart_relationship`, and `objective` are capped at 200 characters. Only the English UI is offered. Context export includes supported patterns, observation dates/counts, uncertainty, current goals, and a redacted subset of the latest completed session's context. Exported copies already downloaded by another application cannot be remotely recalled; consumers should fetch fresh context after revisions or deletion.

## State, retention, and recovery

Conversation states are `queued → processing → complete` or `failed`; deletion uses `delete_pending`. Raw states are `pending`, `deleted`, or `research_source_retained`. Jobs left processing after a stopped worker are retried under the worker lock. In-flight commits recheck revision, consent, and profile revocation. Failed raw media expires after 24 hours; old orphaned spool files are also cleaned.

Enrollment uses queued, processing, complete, failed, and delete-pending states, plus a profile generation counter. Failed enrollment can be replaced with a new three-clip request. Cleanup completion is audited; locked files are retried. The worker must run for expiry and retry cleanup to happen. These policies are application rules rather than filesystem timers.

Personal profile deletion keeps minimal revoked identity/audit bookkeeping while removing the embedding, label, grants, linked personal history, and goals. It does not rewrite existing backups or delete shared research originals. Temporary raw spool data must be excluded from backups by the operator. Analysis of deleted raw audio cannot be regenerated with a different extractor.

## Wearable capture

The ear firmware drains I2S DMA independently of HTTP work. Eight DMA buffers feed 8000-sample PCM16 packets at 16 kHz. Four queued packets bound buffering at two seconds, plus the packet currently in transport. Queue overflow reports lost sample counts. Protocol v2 headers and CRC protect delivery, and exact bytes retry until acknowledged. NVS reserves blocks of 1024 sequence IDs before use; failed reservation pauses capture, and reboot skips unused reserved IDs instead of reusing them.

Wi-Fi reconnects, clock observations, heartbeat/reconnect/overrun status, and authenticated BLE pause/resume support the local hardware pilot. Capture starts paused and drains old DMA while paused. Provisioning requires the BOOT button at startup, is limited to 60 seconds, uses authenticated encrypted BLE, and accepts only literal private IPv4 HTTP endpoints ending `/api/v1`. Permanent chunk rejection pauses capture and awaits manual resume; 408/429 remain retryable.

The firmware does not persist buffered PCM across reset, segment all-day conversations, measure battery life, read TEMT6000, or integrate real wrist sensors. Sequence skips and status expose recovery boundaries, but their physical fidelity still needs measurement. Public transport needs a later TLS design; the current API stays loopback-bound unless an operator explicitly enables a private LAN binding.
