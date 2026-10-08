# PSYCON: PostgreSQL, participant annotations, and supervised training

Planning audit: 2026-10-08. The checklist and execution record below describe the current build; the repository audit later in this file records the pre-implementation state. Small focused lowercase commits are now authorized; pushes remain deferred.

## Neon and Docker execution update

The configured Neon PostgreSQL 18 deployment was inspected before migration. Its existing public schema was preserved. Both the Neon database and local canonical PostgreSQL source were dumped and restored into disposable PostgreSQL 18 databases; all logical row counts and hashes were verified. The canonical 76-table source was transferred to Neon after confirming that its new canonical schema had no sessions or participant submissions. All source counts and hashes matched before new jobs were added, preserving 17 sessions, 104 speakers, 4,366 utterances, 27,708 words, 3,660 evidence records and retained reports/reviewer provenance. All three application roles passed Neon readiness and reads.

Neon pooled connections now use transaction-local settings; heartbeat and resource cleanup use the same schema-aware connection path. Docker web and CUDA worker run against Neon. All 11 original group videos are registered with unchanged names and content hashes, mounted read only, and queued for separate idempotent analyses. Generated normalized playback is also registered with paths, hashes and session relationships; deletion marks generated audio unavailable without removing shared originals. GPU contention commits its requeue without consuming attempts. CUDA model memory is released between stages, and the selected Whisper precision is recorded explicitly. Previous citation identities remain intact. Native Windows paths resolve through an explicit Docker mount mapping; native launchers do not replace the configured database URL.

The original-media backup still requires a destination with sufficient free space. New Docker processing is durable and running; queue registration is not a claim that every new analysis has completed. Missing human labels, consent or evaluation data remain visible exclusions. Commits are now authorized, with short lowercase messages; private data and runtime assets remain excluded, and no push is authorized.

Current verification: 50 focused PostgreSQL instrument tests pass. The complete suite passed 380 tests and skipped five optional checks; the backup/restore case refused C: after available space fell below its required reserve, and passed its explicit recheck on E:. Together these runs verified all 381 runnable tests; five optional integrations remain skipped. Frontend syntax/report checks, Python compilation and whitespace validation pass. Desktop native preview shows the 11 originals and their latest derived processing states; mobile resize still times out, with the earlier synthetic 390 x 844 journey recorded below. Real-media backup remains the open W05/W18 gate.

## Implementation checklist

Status is recorded only after implementation and validation, not after schema creation. No commits or pushes are authorized by the current request.

- [x] W01 PostgreSQL environment, permissions, ordered migrations, readiness
- [x] W02 Complete native PostgreSQL storage port and preserved reports
- [x] W03 Durable jobs, leases, retries, cancellation, stale-write fencing
- [x] W04 Exact-name local media and verified model artifact registration
- [ ] W05 Inventory, backup/restore, idempotent migration and cutover verification
- [x] W06 Separate people, participants, reviewed speaker mappings
- [x] W07 Source-derived versioned forms and independent trait guidelines
- [x] W08 Individual/batch CSV/XLSX preview, mapping, atomic imports
- [x] W09 Immutable answers, evidence and correction lineage
- [x] W10 Review, agreement, target-specific eligibility
- [x] W11 Frozen snapshots and person/source/time leakage prevention
- [x] W12 Actual durable supervised training for both target families
- [x] W13 Evaluation, verified registration, activation and rollback
- [x] W14 Structured prediction inputs and controlled A/B/C research
- [x] W15 Participant/training/model workflows in the current UI
- [x] W16 APIs, exports, deletion, backup/restore and reproducibility
- [x] W17 PostgreSQL integration and desktop/mobile journey validation
- [ ] W18 Dependency gates and final completion audit

Current inventory (2026-10-08): the existing `.env` keys were checked without exposing their values; an explicit PostgreSQL URL is now configured. Docker/PostgreSQL connectivity was restored and existing records were inspected. The old public application tables had zero sessions, recordings, participants, marksheets, labels, and reviews. Their database dump was restored to a disposable database and logical counts/hashes verified before the user-authorized reset. The legitimate instrument SQLite source was separately backed up and restore-verified, then read-only migrated to PostgreSQL with IDs intact; replay verified idempotency. PostgreSQL contains 17 sessions, 104 speakers, 4,366 utterances, 27,708 words, 3,660 evidence rows, and 17 LLM runs. All 11 original videos and related local inputs are registered with exact filenames and verified hashes; deleted smoke sessions were not imported.

Validation record: final automated suite passed 376 tests with five optional integrations skipped, 381 collected and zero failures/errors. It includes 45 focused instrument PostgreSQL tests covering both fitted target families, immutable snapshot/rubric lineage, loading, activation/rollback, corrections, withdrawals, foreign-owner access, imports, reviewed source grouping, leases, stale writes, generation retries/raw failures, merge/split reanalysis, unreachable PostgreSQL without a fallback, and coordinated synthetic asset restoration. JavaScript syntax, Python compilation and git diff whitespace checks passed. The five skips concern optional older communication/group PostgreSQL services, the legacy Compose API, real embedding/diarization input and an opt-in FFmpeg fixture; none substitutes for the current PostgreSQL tests. No production human labels, consent or metrics were fabricated.

Current database verification: source migration replay passed again after the latest changes, and a fresh PostgreSQL dump was restored into a disposable database with all 76 table counts and logical-row hashes matching. The verified copy is `instance/storage-reset-backup/current-23a10ec3-da0b-4ff1-8af9-91dfdba5c44f`. Canonical records include 28 registered media assets, 17 retained analyses, 17 retained legacy generation outcomes and 51 normalized cited claims. New local-model attempts are logged separately, including failed or partial output. Legacy earlier retry history was unavailable.

Open delivery gates:

- W05: the actual database and read-only source are restore-verified, but the complete 15.13 GB original-media backup needs a separate destination with at least 20 GB free. The user-authorized old public-schema reset was completed only after its database restore verification; originals were preserved.
- W17 validation passed in the project-native browser: desktop original-only dashboard, readiness, model inspection/exploratory activation, individual CSV preview and durable save for an unmapped participant, immutable correction, dialog focus restoration, and reviewed reanalysis completing all eight stages. Production audio loaded and seeking returned to ready state 4. Because native resize commands time out, an ignored synthetic-only same-origin test frame provided an actual 390 x 844 CSS-pixel viewport. It showed no page overflow, a fitting answer dialog, horizontally scrollable tables and Escape/focus restoration. This verifies narrow responsive browser behavior, not a physical phone or its touch/codec behavior.
- W18: final delivery remains open for the complete original-media backup. The canonical Docker web and CUDA worker run on localhost:8008 against Neon, and all 11 originals have idempotent processing requests. Small lowercase implementation commits are authorized after validation; no push is authorized.

Implemented W16 backup/restore procedures were exercised with PostgreSQL and synthetic registered local assets; this does not substitute for the real-media backup gate in W05. Real supervised training remains honestly unavailable until actual participant consent, mappings and independently reviewed annotations are supplied.

## The decision

PostgreSQL will be PSYCON's only application database. Recordings, participants, transcripts, measurements, evidence, personal baselines, reference profiles, human form answers, label revisions, jobs, model runs, training datasets, predictions, and evaluations must belong to one connected data model. There will be no SQLite fallback or separate spreadsheet-only database.

The product flow will be:

**Conversation → identified session participants → speaker evidence → human annotations → reviewed training examples → supervised model → evaluated predictions → evidence-grounded report.**

Uploading a spreadsheet stores human annotations. Training changes a supervised prediction model using those annotations and the corresponding conversational evidence. It does not automatically retrain Whisper, pyannote, or Qwen, establish personality diagnoses, or turn reviewer judgments into unquestionable psychological ground truth.

The audio-first specification still applies. Names and faces are not required. The new training pipeline must not depend on face recognition, physiological signals, or identity embeddings.

## Confirmed storage and training decisions

- PostgreSQL holds every application record, answer, transcript, result, and provenance link. Original audio/video bytes remain local, with their exact existing filenames. Do not rename originals or copy them into PostgreSQL.
- Generated model files remain local. Small model artifacts may be stored on GitHub if their size, distribution rights, and contents permit it; participant spreadsheets, recordings, and private answers do not belong in Git. PostgreSQL stores artifact paths, hashes, sizes, versions, and training lineage.
- Train both eligible A–T ratings and explicitly defined communication-trait targets. Feed their predictions into the LLM alongside measured features, contextual evidence, personal baselines, and reference comparisons. Training the supervised predictors and running the LLM are separate operations.
- Use the actual marksheet and answer interpretation guide in `docs` to define imports and targets. Preserve observer ratings and any participant self-report as different source types.

## What the marksheet and interpretation guide define

The audited sources are `docs/PSYCON_Psychologist_Observation_Mark_Sheet.tex`, version 4.0, and `docs/PSYCON_Tendency_Flag_Guide.tex`, titled "PSYCON answer interpretation guide". Their PDF counterparts are rendered documents. The current CSV example captures only participant, class, and A–T scores; it does not capture the full paper form.

| Source fields | Required import/storage behavior |
| --- | --- |
| Session ID/date, participant code, seat/speaker channel, observer code, class/section, topic, observation minutes, languages, recording quality 1–5 | Keep these as typed metadata and reconcile participant/session identities explicitly. A slot or class is not a permanent person identity. |
| A–T score 0–4 or N/O | Keep score, missing status, fair opportunity, and evidence separate. Every positive score requires timestamps and surrounding events. N/O is not zero. |
| Limited opportunity, overlap, poor recording, unfamiliar language, moderation, unequal participation, sensitive topic, accommodation | Preserve individual context flags and notes; they affect eligibility and interpretation. |
| Fair opportunity, reliable speaker identification, recording support, context effects | Store the exact answer categories, explanations, and evidence references, rather than compressing validity into one quality score. |
| Five grouped contextual patterns, each Observed/Not clear/N/O with confidence 1–3 | Preserve human judgments independently of any rule-derived interpretation. These are session patterns, not established longitudinal traits. |
| Event, observable response, duration, participation effect, narrative evidence, signatures and review times | Store structured event/response intervals and narrative answers with reviewer identity and revision history. |

The guide names item-specific patterns including early turn entry, non-yielding overlap, floor-sharing imbalance, low reciprocal acknowledgement, and disagreement-linked behavioral change. Its proposed interpretation rule treats 1 as a weak moment, 2 as a possible pattern, 3–4 as supporting a contextual session pattern, and N/O as no conclusion. Store this as a versioned project rule, not a validated scientific cutoff or calibrated probability.

Items M–T need event context, and Q–T explicitly require an identifiable event and a same-participant baseline. Keep the earlier **same-session** comparison separate from PSYCON's **previous-session** historical baseline. T includes visible behavior or participation change: audio may support the participation component, but cannot establish gaze, posture, or movement. Missing visual inputs must not become fabricated observations.

Broader traits such as directness, proposal orientation, questioning, acknowledgement, and topic control need explicit definitions and human annotation fields beyond the current paper form. The guide provides useful contextual behavior targets, but it does not supply those broader labels or occupational archetype ground truth. Labels derived mechanically from A–T can support a documented rule-based output, but they cannot count as independent validation of a separate learned trait predictor. `docs/COMMUNICATION_ROLE_RUBRICS.md` supplies additional exploratory operational definitions to audit; its legacy wearer, face, and transcript-deletion assumptions do not override this prototype's audio-first retention policy.

## Pre-implementation repository audit

| Area | Existing implementation | Consequence for this work |
| --- | --- | --- |
| New research instrument | `backend/instrument/store.py` and `schema.sql` use SQLite; `run_psycon.py` starts this app and its worker. | Replace its persistence and SQL throughout the instrument, not just its connection string. |
| Existing PostgreSQL support | `backend/db.py` supplies psycopg pooling; `backend/schema.sql` defines the older application and group tables. Compose specifies PostgreSQL 16. | Reuse the pool and deployment infrastructure, with explicit schema migrations. |
| Participant spreadsheets | `backend/group/labels.py` parses UTF-8 CSV rows containing participant slot, class, and A–T scores. `/group` uploads an entire session sheet. | Add individual-participant uploads and a batch preview in the current research interface. CSV-only session imports are insufficient. |
| Form answers and paper sheets | `marksheets`, `item_ratings`, `evidence_intervals`, `reviews`, and `marksheet_attachments` exist in PostgreSQL; participant-specific routes exist in `backend/group_routes.py`. | Preserve and migrate these records and their reviewer/evidence links into the unified workflow. |
| Import provenance | `group_label_imports` retains import bodies; `training_labels` holds current participant/item scores. | Reconstruct source revisions where possible. Current labels alone cannot establish the original reviewer or superseded labels. |
| Existing training command | `backend/group/train.py` calls the face-and-voice item classifier in `research/face_training.py`. | Preserve its historical artifacts, but replace its dependencies for the audio-first prototype. Renaming this command is not enough. |
| Other ML training | `ml/src/models/train.py` belongs to the older physiological/stress experiment. | Keep it separate; it is not the new conversational training pipeline. |
| Current reports | Structured features, evidence, baselines, reference comparisons, and validated local LLM runs already exist. | Preserve their IDs, source windows, raw outputs, versions, and current UI behavior. |

The read-only instrument audit found 17 sessions: 11 original group-discussion videos and six older partial audio imports. Ten original videos are complete; `IMG_4002.MOV` has an attribution failure and its profile is withheld. There are 104 session speaker clusters, 4,366 utterances, 27,708 words, 3,366 feature rows, 3,660 evidence records, and 17 LLM runs. There are zero mapped longitudinal profiles, reviewer annotations, or manually reviewed behavior annotations. Speaker clusters are not a count of unique people or independently labeled training examples.

The live PostgreSQL connection timed out during this audit. Its existing session, upload, and annotation counts have not been verified. Inspect the running database and any stored objects before planning a final migration inventory. Do not infer that its data are empty or deleted.

The original video folder contains 15,130,865,823 bytes. The audited C: drive had 14,262,882,304 bytes free. Keeping media local avoids another full copy in PostgreSQL. Still budget for preprocessing, model artifacts, database backups, and a tested local-file backup; do not duplicate or delete original videos to perform the record migration.

## W01. Establish one PostgreSQL environment and versioned migrations

- Keep the existing supported deployment version for this migration; do not combine a database engine upgrade with the storage rewrite.
- Make `PSYCON_DATABASE_URL` mandatory for the web app, speech worker, interpreter, importers, research tools, and trainer. Failure to connect must show unavailable status rather than create a local database.
- Introduce ordered migrations with a migration ledger and PostgreSQL advisory locking. Separate migration execution from normal request handling.
- Use explicit `psycon` schema names for the canonical research tables. Existing `public.sessions` belongs to the older device workflow and is structurally incompatible with instrument sessions; do not create the instrument tables over it.
- Define separate web, worker, migration, and training database permissions, connection timeouts, rollback behavior, and readiness checks. Preserve the current local-only application boundary.
- Treat old group endpoints as compatibility routes during transition. They must ultimately read/write the canonical records, not maintain a second mutable set of labels.

**Done when:** the application starts against PostgreSQL, migration replay is safe, unavailable PostgreSQL prevents writes, and no application startup creates a `.sqlite3` file.

## W02. Port the complete instrument storage layer

- Replace SQLite connections, `?` placeholders, `INSERT OR IGNORE`, `PRAGMA`, `executescript`, `BEGIN IMMEDIATE`, positional row reads, and SQLite exception handling.
- Port all queries in `store.py`, `service.py`, `profiles.py`, `research.py`, `corpus.py`, `annotations.py`, `routes.py`, and `worker.py`. Avoid a blind SQL-text replacement shim.
- Use PostgreSQL types: UUID where IDs really are UUIDs, `timestamptz` for times, finite numeric values for measurements, and native JSONB for configuration and raw model packets. Keep important evidence and training relationships relational.
- Handle legacy non-UUID identifiers deliberately: `local`, prototype archetype keys, feature-based trait keys, and SHA-256 baseline IDs cannot all be cast to UUID. Preserve external identifiers through explicit aliases or suitable text keys.
- Normalize API serialization of PostgreSQL UUIDs, timestamps, and JSONB values. Remove assumptions that every JSON field is a string requiring `json.loads`.
- Rename ambiguous timing columns to `start_s` and `end_s` through an explicit mapping, retaining the current external transcript/export contract where necessary.
- Preserve constraints, foreign keys, provenance, uniqueness, cascade behavior, and ordered transcript retrieval. Add composite relationships where needed to prevent linking a speaker or annotation to the wrong session.
- Store LLM claims and claim-to-evidence links in queryable tables in addition to retaining the original model JSON.

**Done when:** every current analysis, baseline, evidence lookup, report, comparison, review, and export works on PostgreSQL with no live SQLite dependency.

## W03. Make jobs durable and safe across processes

- Claim speech, interpretation, import, and training jobs transactionally with row locks and `FOR UPDATE SKIP LOCKED`; give each claim an owner, lease, heartbeat, attempt number, and retry policy.
- Release the claiming transaction before decoding audio, calling an LLM, or fitting a model. Do not hold pooled connections or row locks throughout long inference.
- Fence completion writes with job ownership and the input revision, so a restarted worker cannot overwrite newer annotations, mappings, or reports.
- Replace the local-file worker lock as the authority for job ownership. Keep a shared GPU-resource lease so speech, LLM inference, and training do not compete for the same GPU.
- Recover only expired jobs owned by a dead worker. The current blanket startup update of running LLM jobs is unsuitable when multiple workers exist.
- Use one consistent cancellation/deletion policy: canceled or superseded work must not publish results; resumable stages must not create duplicate evidence.

**Done when:** two workers cannot process the same job concurrently, interrupted work can recover, and stale work cannot publish over current inputs.

## W04. Register local media and model artifacts without renaming originals

- Add `assets` with owner, kind, exact original filename, registered local storage root and relative path, media type, byte size, SHA-256, state, creation time, and retention status. Link these records to sessions and model versions; no video/audio or trained-model bytes go into PostgreSQL.
- Preserve names such as `IMG_3997.MOV` exactly, including case and extension. Use session directories or explicit source paths to distinguish identical basenames, and hashes to identify identical content. Never silently overwrite an existing original.
- Keep uploaded spreadsheet source files and small paper-form attachments in PostgreSQL with bounded size limits, alongside normalized answers and source hashes. They are annotation sources, not media/model assets; backups must preserve their original bytes for review.
- Support streamed local uploads and HTTP range reads for playback/downloads. Reconcile the existing 512 MiB upload limit with imported large MOV files. Validate paths against registered storage roots and reject traversal or arbitrary client-supplied server paths.
- Store generated model artifacts under versioned local directories, verify hashes before loading, and keep their manifest/evaluation in PostgreSQL. Optional GitHub distribution covers suitable small generated models only, with a pinned repository revision and recoverable local artifact.
- Keep temporary preprocessing files and model-loading caches disposable. Runtime executables and third-party model caches remain environment dependencies, with versions/digests recorded.
- Inventory old object-store recordings and attachments, then apply the same media-versus-annotation storage policy. Retain distinct analysis provenance when multiple sessions share source bytes.
- Coordinate database and local-file backups, failed-upload cleanup, model retirement, export streaming, and deletion. A missing local file must show an unavailable asset, not a fabricated successful analysis.

**Done when:** all records live in PostgreSQL, media retain exact local filenames, model artifacts are registered and verifiable, and large-file playback/export/deletion work without unbounded memory use.

## W05. Migrate existing data without losing or resurrecting records

1. Inventory SQLite records, PostgreSQL group records, local media, object-store keys, spreadsheet imports, attachments, and existing training artifacts. Report missing assets and unverified metadata.
2. Back up the source data and test a restore. Pause mutation and processing during final cutover so the snapshot has no live writers.
3. Run a one-time, read-only SQLite importer into PostgreSQL using explicit ID and column mappings. Preserve speaker, utterance, evidence, run, and citation identities.
4. Convert times to timezone-aware values, preserve missing confidences and failed stages, and mark uncertain legacy dates as uncertain. Recompute derived records only through versioned jobs.
5. Link matching legacy group sessions to canonical sessions through recording hashes and reviewed mappings. Identical source audio and partial transcript imports are related analyses, not independent training recordings.
6. Import participant sheets, form answers, rater identities, revisions, evidence intervals, attachments, and model manifests. Missing provenance stays missing until reviewed.
7. Compare table counts, key sets, foreign keys, hashes, timestamps, source intervals, baseline memberships, and representative exports. Re-run the importer to prove idempotency.
8. Switch every process to PostgreSQL, verify operation and recovery, then retire the active SQLite files and compatibility writes. SQLite may be read only by the one-time migration tool before retirement; it must not power production or tests afterward.

Deleted smoke sessions must stay deleted. Do not restore them from the isolated verification directory or import manifests. Preserve all 11 original videos and legitimate previous analysis records. A failed attribution must remain a failure unless new processing or a reviewed correction genuinely resolves it.

**Done when:** verified PostgreSQL data replace the active source store, no deleted smoke records return, and no valid recordings or human annotations are lost.

## W06. Unify person, participant, and speaker identity

- A person is longitudinal. A participant is that person's presence in one session. A diarized speaker cluster is an analysis output; these are separate entities.
- Store optional person links, anonymous participant codes, session-local labels, and versioned participant-to-speaker mappings. Require explicit confirmation before joining a sheet to extracted speaker features.
- Support silent participants, unknown speakers, merged/split diarization clusters, and uncertain mappings. An unmapped participant can have a saved sheet but cannot silently acquire another speaker's features.
- Keep participant numbers session-local. “Participant 1” in two sessions does not establish the same person. Class/section labels and filenames do not establish identity either.
- Resolve old face-based slot references through human-reviewed mappings; do not make face recognition a requirement of the new workflow.
- Use mapping revisions to invalidate dependent feature/label joins, baseline snapshots, training snapshots, predictions, and reports.

**Done when:** users can upload a sheet for a specific session participant and trace exactly which reviewed speaker evidence it belongs to.

## W07. Define versioned forms, rubrics, and training targets

- Store rubric/form definitions and versions, item keys, readable descriptions, answer types, allowed values, score meanings, required evidence, modality requirements, and intended training use.
- Preserve the existing A–T version 4.0 rubric without changing its meaning. Store `0` as an observed negative rating only when a fair opportunity existed; keep missing answers and `N/O` distinct.
- Separate observer ratings, participant self-report, independent reviewer judgments, adjudicated labels, and model predictions. A spreadsheet upload can contain multiple source types, but their lineage must remain explicit.
- Retain narrative fields such as preceding event, observed response, context notes, fair opportunity, missing-score reason, trigger interval, baseline interval, and evidence interval.
- Define the observation unit: session-level participant/item rating or an explicitly annotated interaction window. Do not turn several supporting timestamps into several independent labels.
- Inventory each A–T item's observability in this audio-first system. T mixes visible behavior with participation changes; only supported components are eligible. K/M/N/O and other contextual items need an explicit opportunity/event audit. Store all human answers, but train only targets supported by available inputs. Repeated behavior after a trigger requires temporal evidence, not just a global session average.
- Define both target families: ordinal A–T ratings and communication-trait labels with their own annotation guidelines, repeated-evidence requirements, context, and uncertainty. Retain the guide's item patterns and five grouped summaries as separately versioned outputs. User-selected Executive/Builder/etc. goals and school class labels are not occupational ground truth or supervised archetype labels.

**Done when:** every uploaded answer has a known definition and source, and each proposed prediction target has a documented observable basis.

## W08. Add individual and batch spreadsheet imports

- On each session participant, expose **Upload participant answers**, **Enter answers**, **View submitted answers**, and **Correct answers**. Also allow one batch workbook containing multiple participants.
- Support CSV and ordinary XLSX with versioned templates. Do not execute macros or formulas, infer unknown score scales, or convert arbitrary narrative text into ratings automatically.
- Provide a guided preview: choose session, participant, form version, source type, reviewer/respondent, and applicable evidence windows; show mapped columns, parsed values, errors, and proposed replacements before saving.
- For a single-participant file, the selected participant supplies the association; reject conflicting embedded identity. For a batch file, require explicit participant mappings and reject duplicates or ambiguous matches.
- Validate score ranges, timestamps, recording boundaries, file limits, worksheet selection, unknown columns, missing answers, duplicate items, withdrawn participants, and conflicting revisions.
- Commit original upload provenance, normalized answers, source references, and revision state atomically after confirmation. An invalid upload must not partially overwrite previous labels.
- Use content hashes and idempotency keys. Re-uploading identical data should not create new training examples; corrected answers create a new revision with a reason.
- Keep scanned PDFs as attachments. Extracted/OCR values may be preview suggestions, but only confirmed values become annotation records.

**Done when:** an individual participant's sheet becomes queryable PostgreSQL answers with intact provenance, and errors leave existing answers unchanged.

## W09. Normalize annotations and revision lineage

Proposed canonical table families, all in PostgreSQL:

| Family | Tables and purpose |
| --- | --- |
| Identity and data ownership | `users`, `people`, `sessions`, `session_participants`, `speaker_clusters`, `speaker_mappings`, `datasets`, `dataset_memberships`, `consent_records`, `legacy_id_aliases`. |
| Audio and analysis | `assets`, `storage_roots`, `analysis_runs`, `processing_stages`, `turns`, `utterances`, `words`, `feature_definitions`, `feature_values`, `evidence`, `interactions`, `behavior_annotations`. Local media bytes are referenced, not stored. |
| Personalization and reports | `baseline_profiles`, `baseline_features`, `baseline_sessions`, `archetypes`, `archetype_features`, `traits`, `session_traits`, `trait_evidence`, `comparisons`, `llm_runs`, `llm_claims`, `llm_claim_evidence`. |
| Human forms | `form_definitions`, `form_items`, `annotation_imports`, `annotation_import_rows`, `annotation_submissions`, `annotation_answers`, `annotation_context_flags`, `annotation_validity_checks`, `annotation_pattern_summaries`, `annotation_evidence`, `annotation_reviews`, `annotation_adjudications`, `annotation_attachments`. |
| Training and serving | `training_tasks`, `training_snapshots`, `training_examples`, `training_example_features`, `training_example_labels`, `split_assignments`, `training_runs`, `training_run_events`, `model_versions`, `model_artifacts`, `model_predictions`, `prediction_evidence`, `model_deployments`. |
| Evaluation and operations | `evaluations`, `reviewer_annotations`, `feature_evaluations`, `model_evaluations`, `jobs`, `worker_heartbeats`, `audit_events`, `schema_migrations`, `migration_runs`. |

Use one canonical annotation store, not three independent versions of marksheets, spreadsheet labels, and form answers. Existing group routes must adapt to it. Definitions, answers, labels, features, and relationships need typed/queryable columns; original files and raw model JSON supplement those records.

Preserve raw submissions and corrections immutably, with explicit supersession and a current approved view. Record who uploaded, who actually rated, when, which rubric was used, and what changed. An uploader's identity must not be silently substituted for the original reviewer.

**Done when:** a training label can be followed back to its source answer, original import/attachment, reviewer, revision, participant mapping, and source evidence.

## W10. Add review, agreement, and eligibility

- Provide independent reviewer submissions and adjudication without overwriting each reviewer's original judgment. Keep blind report evaluation separate from supervised behavior labels.
- Define how disagreements are handled per task: adjudication, a documented consensus rule, or a target distribution. Do not count two reviewers' ratings as two independent participants.
- Display per-target exclusion reasons: missing consent, uncertain mapping, incomplete processing, unsupported modality, missing evidence, missing fair-opportunity annotation, unresolved review, withdrawal, insufficient classes, or unsuitable dataset role.
- Imported spreadsheets may be saved before training eligibility exists. Saving does not grant consent, confirm attribution, or certify annotation quality.
- Calculate suitable agreement statistics only on shared rated items, with actual paired counts and uncertainty. Agreement is evidence about label reproducibility, not proof that a construct is psychologically valid.
- Keep self-report targets separate unless a study explicitly evaluates agreement between self-report and observed behavior.

All current instrument sessions say `not documented` for consent. They must not automatically enter a real training dataset. Document their applicable research/consent status and participant mapping first.

**Done when:** the UI explains exactly which participant/item annotations are usable for a specified training task and why others are excluded.

## W11. Build reproducible supervised datasets

- Replace the current face/voice feature requirement with the formal speaker-specific conversation feature dictionary and reviewed interaction/context features. Identity embeddings, faces, names, classes, reviewer IDs, and import order are not behavior predictors.
- Match feature granularity to label granularity. For trigger-based items, calculate documented before/after window features with sufficient quality and preserve the supporting intervals.
- Record schema/extractor versions, missing-value indicators, units, denominators, attribution quality, and annotation coverage. Fit imputers, scalers, feature selection, and any text embedding transformation only on training data.
- Freeze each dataset snapshot under a consistent database transaction, materialize its examples and feature values, then release the transaction before training. Later imports cannot mutate that snapshot.
- Keep dataset role separate from the fit split: development/training, validation, final evaluation, and reference corpus are not interchangeable. The current reference-designated videos cannot silently become development data; changes must be recorded in a new dataset protocol/version.
- Group connected recordings by confirmed person identity and source-recording hash, including partial imports and near-duplicate excerpts. In a group discussion, shared participants can connect multiple whole sessions into a single split component.
- Store train/validation/test memberships with an immutable seed and explicit grouping policy. If the connected data produce too few independent groups, report that limitation instead of falling back to a random row split.
- Separate an unseen-participant generalization study from a within-person longitudinal study. The latter uses forward time splits and only eligible previous history. Never expose target-session human answers or later sessions to that session's prediction/baseline.
- Export a snapshot manifest with label revisions, mapping revisions, feature versions, source hashes, cutoff policy, exclusions, and counts of distinct people, sessions, groups, and item observations.

**Done when:** two runs can reconstruct the same examples and splits, and leakage tests reject shared-person/source overlap or future baseline inputs.

## W12. Implement real training as a separate durable job

- Start with transparent baselines: a training-set majority/median predictor, followed by regularized models appropriate to each task. Treat 0–4 ratings as ordinal; evaluate any multiclass approximation explicitly. Add more complex models only through measured comparisons.
- Train both eligible A–T ordinal heads and independently annotated communication-trait heads, using separate task definitions or a documented multi-output model. Never force a target to fit when observations, score variation, or independent recording groups are insufficient. Report readiness and evaluation separately for each target family.
- Replace `backend/group/train.py`'s face-dependent path with a canonical PostgreSQL snapshot trainer, or retain it under an explicitly legacy command and introduce `run_psycon.py train` for the audio-first task.
- Store selected task, dataset snapshot, seed, hyperparameters, software versions, feature order, validation choice, progress, failure details, and produced artifacts in PostgreSQL.
- Use validation data for model/hyperparameter selection and any calibration or abstention threshold. Do not repeatedly tune against the final evaluation set.
- Treat the old five-session/five-nonzero rule as an exploratory implementation threshold, not proof that a dataset is large enough. Define task-specific minimums and report actual coverage/uncertainty.
- Keep LLM fine-tuning outside the first implementation. It would require a separately curated, consented dataset of grounded reports and independently reviewed targets. Human rating spreadsheets are not automatically suitable instruction-tuning examples.

**Done when:** a queued job actually fits a model from frozen human labels, persists its artifacts and lineage, or returns an explicit reason training cannot proceed.

## W13. Evaluate, register, and deliberately activate models

- Report per-target MAE for ordinal errors, macro-F1/balanced accuracy where applicable, confusion matrices, ordinal agreement, abstention/coverage, and probability calibration when probabilities are shown. Include baseline comparisons and actual held-out sample counts.
- Assess variation across speakers, recording conditions, and conversation contexts only where data support it. Use participant/session-group resampling for uncertainty; do not treat correlated utterances as independent samples.
- Define pass criteria before inspecting final test results. A fitted model with no valid held-out evaluation is exploratory, not validated.
- Register immutable versions with dataset hash, code revision, feature schema, task/rubric version, hyperparameters, metrics, limitations, and artifact hashes. A training run must not automatically replace the active model.
- Provide candidate/active/retired states and a recorded activation/rollback action. Verify artifact integrity and feature compatibility before loading the model.
- Persist predictions separately from human answers. No prediction or AI exercise may feed back into the human-label table.
- Withdrawn/deleted data invalidate dependent snapshots and eligibility for future training. Flag affected existing models for retirement/retraining; deleting rows does not remove their influence from trained weights. Follow the chosen retention policy for source-derived artifacts and backups.

**Done when:** the user can inspect a model's real evaluation, activate it deliberately, roll it back, and identify the human data behind a prediction.

## W14. Use trained behavior predictions without breaking PSYCON's evidence chain

- Keep measured features, human labels, supervised predictions, and LLM interpretations visibly distinct. A predicted rubric item remains a prediction, with a model version, uncertainty, and abstention state.
- Link a session-level prediction to its measured inputs and relevant evidence window. Feature importance does not prove that one quote caused the predicted rating. Interval-level claims need interval-level training and evaluation.
- Feed both target families to the reasoning layer as structured inputs with distributions or scores, calibrated uncertainty where available, abstention, model/rubric versions, and supporting evidence references. Keep human-reviewed answers separate, and never expose held-out answers to the predictor or evaluation report generator. Reports must remain useful when no trained model is active.
- Continue strictly historical, context-aware personal baselines. A supervised behavior model is not a replacement for the person's observed history.
- Keep archetypes mathematically defined and independently sourced. Role selection does not assign a training label; A–T ratings do not automatically establish Executive/Builder/Salesperson/Negotiator identity.
- For the original A/B/C experiment, freeze the same feature-extraction/model version for B and C and isolate the representation difference. Evaluate the new supervised predictor separately so improvements are not attributed to personalization when they actually came from a different extractor.

**Done when:** every report distinguishes observation from prediction/inference and traces each new trained output to its versioned inputs and applicable evidence.

## W15. Put the whole workflow in the current interface

- Extend session navigation with **Participants & answers**. Show speaker mappings, per-participant upload/entry actions, annotation revisions, review status, and training eligibility together.
- Provide readable answer tables and source previews, with correction and reviewer actions. Keep IDs, import diagnostics, and raw JSON secondary.
- Add a **Training** workspace: data readiness, dataset preview, exclusions, target selection, split summary, start/cancel/status controls, and completed model versions.
- Add a **Models** area within Training for evaluation, active version, limitations, activation, and rollback. Keep the existing **Research** workspace for independent evidence-grounding and A/B/C experiments.
- Distinguish “Uploaded”, “Needs mapping”, “Needs review”, “Eligible”, “Training”, “Exploratory model”, and “Evaluated model”. Do not show fabricated scores or a fake success state when there are no usable labels.
- Preserve the recent inline Report design, Geist fonts, audio-position behavior, evidence retrieval, exports, and dashboard restriction to original group-discussion videos.
- Consolidate current and older entry points so users do not need to guess which port stores their data. Retire duplicated intake forms after their data and actions are available in the canonical interface.

**Done when:** a user can upload a participant's real answers, review their association, build a dataset, train, evaluate, and inspect a prediction from one application.

## W16. Add APIs, exports, deletion, and reproducibility

- Define participant-scoped import preview/commit, form submission/revision, reviewer adjudication, dataset snapshot, training job, model version, activation, and prediction endpoints under the research API.
- Check ownership and session/participant associations server-side. Keep existing mutation protections; do not trust an uploaded filename or client-selected ID as proof of identity.
- Extend JSON/CSV/ZIP exports with form definitions, source imports, normalized answers, revisions, mappings, training manifests, split assignments, model provenance, and evaluation tables. Preserve RTTM and transcript exports.
- Update session/participant withdrawal and deletion so retained media, answers, source attachments, derived reports, and training lineage follow a consistent policy. Preserve only permitted non-identifying audit records and mark affected models appropriately.
- Provide a tested PostgreSQL backup/restore path covering the chosen asset storage as well as relational data. No result should depend on an unregistered file in a worker's temporary directory.
- Revise README, architecture, dataset protocol, spreadsheet templates, operator instructions, and the ISEF methodology. Remove claims that SQLite is an intended storage option.

**Done when:** an exported/restoreable study can reproduce its data, splits, training configuration, and evidence links.

## W17. Replace the test setup and validate end to end

- Run storage/API/worker integration tests against disposable PostgreSQL databases or schemas, not SQLite pretending to be PostgreSQL. Pure algorithm tests can remain isolated in memory without a database.
- Test schema collision avoidance, migration replay, ID preservation, null/JSON/time handling, concurrent claims, expired leases, stale completions, failed transactions, connection loss, and restore integrity.
- Test participant mismatch, duplicate rows/files, invalid scores, `0` versus `N/O`, missing evidence, conflicting revisions, large XLSX/CSV imports, individual versus batch sheets, and partial upload failure.
- Test unmapped/withdrawn participants, mixed self-report/reviewer data, legacy provenance gaps, unsupported visual targets, insufficient training data, one-class labels, and unavailable consent.
- Test connected-person/source splits, duplicate recordings, reference/evaluation isolation, training-only preprocessing, immutable snapshots, forward baselines, and corrections arriving while a job is running.
- Test successful and interrupted fitting, artifact verification, unavailable held-out metrics, abstention, deliberate promotion, rollback, prediction lineage, and model invalidation after data removal.
- Test the complete real flow: upload a discussion → map participants → upload each sheet → review source evidence → freeze a dataset → train when eligible → evaluate → activate → process a new conversation → inspect predictions and their sources → export → restore.
- Re-run mobile/desktop interaction, keyboard/focus, audio playback, loading/error states, and contrast checks. Previous preview disconnections are not proof these new flows work.

**Done when:** the instrument works without SQLite installed/available, PostgreSQL failures are transparent, and tests demonstrate both valid results and refusal to invent results.

## W18. Execute in dependency order

| Milestone | Work packages | Deliverable / release gate |
| --- | --- | --- |
| 1. Storage and inventory | W01, W04, W05 inventory | Verified PostgreSQL deployment, exact local filenames, source inventory, tested database/local-file backup. |
| 2. PostgreSQL-only instrument | W02, W03, W05 cutover | Existing audio/evidence/report/research workflows work unchanged on PostgreSQL; no live SQLite. |
| 3. Participant answers | W06–W09, participant portions of W15–W16 | Individual and batch uploads save normalized, versioned answers with confirmed participant association. |
| 4. Reviewed training data | W10–W11 | Visible eligibility and reproducible snapshots with defensible group/time splits. |
| 5. Actual supervised training | W12–W13, Training/Models UI | Both target families, real jobs, local registered artifacts, held-out results or explicit insufficiency, deliberate activation. |
| 6. Grounded prediction and research | W14, remaining W15–W17 | New conversations use eligible models with evidence lineage; original A/B/C methodology remains controlled. |

The current user instruction authorizes implementation, explicit migration, synthetic validation and small lowercase commits; pushes remain deferred. Stay on feat/audio-research-instrument. No source recordings, private answers, credentials, runtime caches or backup dumps are versioned. Small lowercase implementation commits are authorized after validation.

## Completion criteria

- Every application record and result uses PostgreSQL; no SQLite runtime, test database, or automatic fallback remains.
- Audio/video stay local with exact filenames; trained files stay local or in an approved small GitHub artifact. PostgreSQL stores their metadata and all normalized answers/results; bounded annotation source files are retained in PostgreSQL.
- Existing recordings and legitimate human annotations are preserved and verified; deleted smoke records remain absent.
- Each participant's spreadsheet/form answers are queryable, versioned, attributable to a human source, and linked to reviewed conversation evidence.
- Training supports both A–T ratings and communication-trait predictions from eligible human annotations and reproducible feature/split snapshots, with explicit exclusions and data insufficiency.
- Models are evaluated, registered, activated, and rolled back transparently; predictions never overwrite human labels.
- Personal baselines, reference archetypes, and evidence-grounded reports remain distinct from supervised predictions.
- No diagnosis, occupational identity, measured accuracy, significance, or validation is asserted beyond the available study evidence.

## Primary implementation references

These support the engineering choices, not the validity of PSYCON's behavioral constructs.

- PostgreSQL 16's [SELECT documentation](https://www.postgresql.org/docs/16/sql-select.html) describes locking clauses and `SKIP LOCKED`, used here only for queue ownership.
- PostgreSQL's [JSON types documentation](https://www.postgresql.org/docs/16/datatype-json.html) and psycopg's [type adaptation documentation](https://www.psycopg.org/psycopg3/docs/basic/adapt.html) inform the JSONB/native-type port.
- Scikit-learn's [grouped cross-validation documentation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data) explains why repeated samples from the same group require grouped evaluation. PSYCON additionally groups shared recordings and connected participants and uses forward time splits for longitudinal tasks.
