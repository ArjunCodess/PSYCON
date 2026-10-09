# PSYCON

PSYCON is a behavioral observation and communication research instrument. It connects a person's speaker-specific talking patterns and discussion context with psychologist-reviewed observations from the A-T marksheet. It preserves timestamped evidence and personal history, and trains supervised models to predict eligible contextual ratings from conversational data.

The current ISEF prototype uses audio and transcripts. Its focus is what a person said and did in a particular exchange, how that relates to reviewed human observations, and how patterns differ across comparable conversations. The [v4.0 psychologist marksheet](docs/PSYCON_Psychologist_Observation_Mark_Sheet.pdf) and [answer interpretation guide](docs/PSYCON_Tendency_Flag_Guide.pdf) define the observation targets. Their [marksheet source](docs/PSYCON_Psychologist_Observation_Mark_Sheet.tex) and [guide source](docs/PSYCON_Tendency_Flag_Guide.tex) retain the exact definitions.

A psychologist-reviewed profile here means a set of contextual ratings, evidence, confidence, and review records. It does not establish a personality type or diagnosis. Model agreement with those ratings needs held-out evaluation. See [the behavioral direction](docs/PSYCON_VISION.md) for the staged work and [current coverage](docs/INSTRUMENT_STATUS.md) for implementation limits.

## Research question

**To what extent can speaker-specific talking patterns and discussion context predict contextual A-T ratings reviewed by school psychologists on held-out participants and recordings, and does adding strictly earlier personal history improve the evidence support and usefulness of the resulting communication reports?**

The study has two separate evaluations. The supervised predictor learns the relationship between conversational measurements and reviewed human ratings, then measures per-item agreement on data excluded from fitting. The report experiment compares transcript-only, structured-context, and full-PSYCON inputs using the same speaker, local language model, and generation settings. The structured-context and full-PSYCON conditions share frozen supervised predictions so a changed predictor cannot be mistaken for an improvement from personal history.

The question is about observable behavior in context. A correlation between a speaking pattern and a psychologist's rating does not establish a cause, a psychological state, or a permanent characteristic of the person. Success requires supported evidence, reproducible human judgments, performance against simple prediction baselines, and independent review of the reports. A completed software pipeline alone cannot answer the research question.

## Psychology and the school psychologists' data

The study's human reference is the marksheet data provided and reviewed by psychologists from the project author's school. Their role is to judge recorded behavior against the item definitions, check the surrounding exchange, and retain evidence for their judgments. PSYCON connects those observations to the correct participant's audio and transcript. It does not generate the psychologist's answers or treat its own predictions as human validation.

Each marksheet describes one participant in one discussion. The five observation areas cover following the discussion, structuring contributions, sharing turns, responding to challenge, and delivery changes after an identifiable event. The psychological interpretation stays tied to what the recording supports. For example, reduced participation after a challenge needs evidence of the challenge, earlier participation, later behavior, and an opportunity to speak; a short contribution by itself cannot establish withdrawal or anxiety.

The rating scale preserves the psychologist's distinctions:

| Answer | Meaning in the v4.0 marksheet |
| --- | --- |
| 0 | The behavior was not observed despite a fair opportunity |
| 1 | One weak or brief occurrence |
| 2 | Repeated or noticeable behavior with limited effect |
| 3 | Clear and repeated behavior, or an effect on the exchange |
| 4 | Sustained behavior or a strong effect on the exchange |
| N/O | No fair opportunity, or a recording that cannot support a rating |
| Missing | No answer was supplied |

Scores above zero require timestamps and the surrounding event. The interpretation guide treats 1 as a weak moment, 2 as a possible one-session pattern needing more evidence, and 3 or 4 as support for a contextual description. Reviewers also record confidence, recording quality, language access, overlap, moderation, unequal participation, sensitive topics, and accommodations. These conditions can change what a rating means.

The app preserves the observer's original answer, independent review, disagreements, adjudication, and later corrections as separate records. Self-reports also remain separate from observer ratings. Reviewer agreement tests whether people apply the rubric consistently; model agreement tests whether conversational inputs predict their reviewed answers. Neither makes the marksheet a diagnostic instrument or establishes broader psychological validity.

Psychologist-reviewed school data can be retained before it is ready for training. Training additionally requires documented permission, a reviewed participant-to-speaker mapping, applicable opportunity, supported evidence, source review, and independent answer review. The current application records do not yet contain eligible, consented, independently reviewed human labels. The software has been exercised with isolated synthetic studies; those checks are engineering tests and are not results from school participants.

## Current scope: software active, hardware paused

Hardware development is paused for now. The active work is the recording-to-evidence pipeline, psychologist marksheet intake and review, supervised behavioral prediction, personal history, and report evaluation in the software application. No wearable, physiological sensor, face recognition, voice enrollment, or identity embedding is required to run this workflow. Earlier hardware and coaching material is retained in [the archived README](docs/LEGACY_PRODUCT_README.md).

## Run the research instrument

Run this one command from the repository root in PowerShell, with Docker Desktop running and the PostgreSQL URL in the ignored `.env`:

```powershell
.runtime\venv\Scripts\python.exe run_psycon.py docker
```

Open http://localhost:8008. Docker starts the web app, CUDA speech worker, and independent CPU trainer concurrently after applying migrations and idempotently queuing the original-video batch. All services use the configured PostgreSQL, including Neon pooled URLs. Startup never substitutes the old local database. The Docker image extends the installed `psycon-week4-worker:latest` speech runtime; build that runtime first on a fresh machine. Registered Windows paths are explicitly mapped to the mounted workspace, and originals are mounted read only.

PostgreSQL is the only application database; a connection failure never creates another store. Original media and generated models stay in registered local paths; answers, bounded source spreadsheets, evidence, jobs, model manifests, and results live in PostgreSQL. The application remains a local single-user research instrument.

Session **Participants & answers** supports anonymous participants, reviewed speaker mappings, individual/batch CSV and XLSX previews, source downloads, direct entry, immutable corrections, independent review, and consent records. **Training & models** shows explicit exclusions, frozen snapshots, queued supervised fitting, held-out evaluations, exploratory limitations, deliberate activation, rollback, and predictions. Saving a sheet does not grant consent or establish training eligibility. A-T uses the actual v4.0 marksheet; independent communication labels use [the annotation guidelines](docs/COMMUNICATION_ANNOTATION_GUIDELINES.md).

The training dashboard shows per-target training, validation, and final-evaluation records and independent source-group counts before fitting. Start training is disabled for snapshots that cannot fit any target. Jobs update automatically, and fitted models remain candidates until you deliberately activate them. Choose a processed recording and speaker to inspect predictions without copying database IDs. The trainer also commits queued spreadsheet imports independently of speech processing, using the worker database role for imports and the trainer role for fitting.

To run without Docker, use this one PowerShell command after installing the project runtime and configuring PostgreSQL:

```powershell
npx.cmd --yes concurrently@9.2.1 --kill-others --names web,media,trainer ".runtime\venv\Scripts\python.exe run_psycon.py web --port 8008" ".runtime\venv\Scripts\python.exe run_psycon.py worker" ".runtime\venv\Scripts\python.exe run_psycon.py trainer"
```

Read [the storage and training runbook](docs/POSTGRES_TRAINING_RUNBOOK.md) for migrations, least-privilege roles, snapshots, workers, exports, coordinated backups/restoration, and deletion. The retained legacy source is read only by the one-time migration command. `run_backend.py` and the local-runtime web/worker commands launch the same canonical application.

When an interpretation is requested, PSYCON reuses the configured local Ollama service. If the loopback service is stopped and the bundled `.runtime/ollama` executable exists, it starts that executable in the background with the project-local model directory and cloud access disabled. No model is downloaded, substituted, or repinned automatically. Container endpoints and independently installed runtimes must be started separately. You can also start the bundled runtime manually:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 ollama
```

The app uses Community-1 diarization and faster-whisper large-v3 through replaceable adapters. The launcher selects the available CUDA device or CPU and uses project-local model caches. The diarization model requires the applicable Hugging Face model access and `HF_TOKEN`. The local interpreter uses the configured Ollama model and records its actual digest. Missing models and rejected evidence references produce explicit failures, never substitute profiles.

Interpretation failures identify whether the service is unreachable, the selected model is absent, or its digest differs from `PSYCON_OLLAMA_DIGEST`. Digest mismatches remain blocked. Background-service logs are in `.runtime/logs/ollama-stdout.log` and `ollama-stderr.log`. Interpretation cites only the target speaker's supplied evidence IDs while retaining other speakers' words as interaction context, and truncated model responses are withheld.

## Use it

1. **Upload conversations.** Supply actual recording times, context, participant IDs, dataset role, and consent status. Each file becomes its own session, and originals keep their exact filenames.
2. **Inspect speaker evidence.** Review quality diagnostics, processing stages, the timeline, attributed transcript, measured talking patterns, and surrounding exchanges. Ambiguous overlapping words remain unattributed.
3. **Connect the correct person.** Keep longitudinal people, session participants, and speaker clusters separate. Confirm the participant-to-speaker mapping through a reviewer before linking answers to features. Names and identity embeddings are unnecessary.
4. **Save and review marksheets.** In Participants & answers, preview individual or batch CSV/XLSX files, map columns and participant codes, and save normalized answers to PostgreSQL. Retain the psychologist's identity, context, opportunity, confidence, timestamps, and independent review. Zero, N/O, and missing answers have different meanings.
5. **Examine contextual patterns.** Compare measured participation, timing, responses, and evidence with reviewed A-T observations and strictly earlier personal history. The Q-T event baseline comes from earlier in the same discussion; it is separate from the historical baseline. Optional archetype comparisons are exploratory reference tools.
6. **Train eligible targets.** Training & models shows data readiness and exclusion reasons. Freeze a versioned dataset, queue training on the Docker or local worker, inspect per-item held-out evaluation, and activate a compatible model deliberately. Saving a spreadsheet alone does not authorize training. Models learn from approved examples, rather than indiscriminately using every stored record.
7. **Interpret and evaluate.** Reports distinguish measurements, human annotations, supervised predictions, and LLM interpretation. Review cited audio before acting on suggestions. Evaluate supervised prediction separately from the controlled transcript-only, structured-context, and full-PSYCON comparison. Missing evaluation remains unavailable.
8. **Export or delete.** Exports retain actual processing states, annotations, revisions, and model provenance. Corrections, withdrawals, and deletion invalidate affected datasets and results and flag dependent models for retirement or retraining.

## How the software works

### From a recording to participant evidence

The launcher registers the 11 original files in `group_discussions` idempotently and queues their analysis in PostgreSQL. Uploaded recordings use the same processing workflow. Each session retains its exact original filename, file hash, recording time, context, ownership, and processing configuration. Registration and queuing do not imply that processing has succeeded.

The media worker extracts audio to a separate normalized playback file, checks recording quality, identifies anonymous speaker intervals with Community-1, and transcribes speech with faster-whisper large-v3. It keeps source timestamps and assigns words conservatively: ambiguous overlapping speech remains unattributed. Segmentation then creates turns, utterances, and surrounding exchanges for speaker-specific feature extraction.

Measurements include speaking time and share, turn count, words per minute, overlap candidates, and supported transcript markers. Every feature records its definition, unit, source, version, and limitations. An overlap candidate is not a confirmed intentional interruption, and a rule-based transcript marker is not a psychologist's judgment. Quality failures withhold unsupported analysis while preserving available stage outputs. Evidence links connect a result to the correct speaker, source excerpt, context, and playback time.

### From a marksheet to a trained predictor

Participants & answers previews CSV/XLSX files before saving, supports column and anonymous-code mapping, checks duplicates and invalid rows, and saves valid batches atomically. Direct entry follows the same versioned form definitions. PostgreSQL retains normalized answers, permitted source files, reviewer records, evidence windows, and immutable correction history. The current speaker mapping determines whether those answers can be joined to measured features.

Training & models explains exclusions before fitting. A frozen snapshot records label and mapping revisions, consent, source hashes, feature versions, and split assignments. Shared participants, duplicate recordings, and related recording sources cannot cross the split boundary. Historical inputs use only permitted earlier sessions, and preprocessing learns its parameters from training records alone.

The CPU trainer fits a separate supported target using median imputation, missing-value indicators, scaling, and class-balanced logistic regression. Validation selects the model configuration; final evaluation remains separate. The dashboard reports per-target sample counts, prediction errors, classification metrics, and a training-median prediction baseline where available. Small or unsupported targets remain unavailable or exploratory. This trains the supervised behavioral predictor; it does not fine-tune Whisper, diarization, or the LLM.

Generated model files stay local with their hashes, manifests, evaluations, and training lineage registered in PostgreSQL. A fitted model remains a candidate until an operator activates it. Activation and rollback are recorded, and predictions retain the exact model and input lineage. Corrections or withdrawals invalidate affected snapshots and outputs and identify dependent models that need retirement or retraining.

### From participant evidence to a report

The application keeps four layers visible: measured observations, human annotations, supervised predictions, and LLM interpretations. When available, the local LLM receives structured predictions with model versions, uncertainty, abstention, and evidence references, alongside measured features and interaction context. Personal history uses strictly earlier comparable sessions; pressure-event comparisons use an earlier baseline within the same discussion. Those baselines answer different questions and remain separate.

The report preserves its input, prompt, decoding settings, local model digest, output, citation checks, and processing attempts. Generated text from the video/session workflow is logged in PostgreSQL, including failed attempts. Invented or wrong-speaker citations and truncated responses are withheld. Reports offer qualified interpretations and evidence-backed communication suggestions, while measurements, human observations, and playback remain useful without a trained model or available LLM.

### Pages and services

| Application area | What it lets the researcher do |
| --- | --- |
| Dashboard | Check the original group-discussion videos and their latest analysis states |
| Sessions | Inspect processing, participants and answers, transcript, measurements, and reports; play or export evidence |
| People & history | Link anonymous people across reviewed session mappings and compare eligible earlier conversations |
| Talking patterns | Inspect recurring conversational indicators with evidence and historical limits |
| Evidence | Search saved speaker-specific excerpts and inspect their context and timestamps |
| Research | Run the controlled three-way report comparison and inspect independent reviewer results |
| Training & models | Review data readiness, freeze datasets, train, evaluate, activate, roll back, and inspect predictions |
| Blinded review | Rate a saved report and its cited sources without seeing its system or model label |

Optional reference comparisons remain secondary exploratory tools. They do not assign personality or provide training labels.

The web service uses Flask, Jinja templates, and plain JavaScript. The media worker handles recording analysis and local interpretation; the independent CPU trainer handles fitting and queued spreadsheet intake without waiting for speech processing. PostgreSQL owns durable jobs, claims, leases, retries, cancellation, and protection against stale completion writes, so a browser request does not have to remain open while work runs.

| Software component | Main source |
| --- | --- |
| Launcher and Docker services | [`run_psycon.py`](run_psycon.py), [`docker-compose.instrument.yml`](docker-compose.instrument.yml) |
| Web application and APIs | [`app.py`](backend/instrument/app.py), [`routes.py`](backend/instrument/routes.py), [`workflow_routes.py`](backend/instrument/workflow_routes.py) |
| Recording processing and features | [`service.py`](backend/instrument/service.py), [`audio.py`](backend/instrument/audio.py), [`features.py`](backend/instrument/features.py) |
| Human forms, answers, and eligibility | [`forms.py`](backend/instrument/forms.py), [`answers.py`](backend/instrument/answers.py), [`annotations.py`](backend/instrument/annotations.py) |
| Snapshots and supervised models | [`datasets.py`](backend/instrument/datasets.py), [`training.py`](backend/instrument/training.py) |
| History and controlled report research | [`profiles.py`](backend/instrument/profiles.py), [`research.py`](backend/instrument/research.py) |
| PostgreSQL, jobs, and workers | [`store.py`](backend/instrument/store.py), [`jobs.py`](backend/instrument/jobs.py), [`worker.py`](backend/instrument/worker.py) |
| Exports, backups, and deletion | [`exports.py`](backend/instrument/exports.py), [`backup.py`](backend/instrument/backup.py), [`deletion.py`](backend/instrument/deletion.py) |

The [architecture and research protocol](docs/INSTRUMENT_ARCHITECTURE.md) records feature calculations, quality gates, historical rules, and experimental controls. The [PostgreSQL and training runbook](docs/POSTGRES_TRAINING_RUNBOOK.md) covers configuration, migration, file registration, exports, coordinated database/local-file backup and verified restoration. The complete original-media backup still needs a destination with sufficient free space; database verification does not stand in for that media backup.

## Marksheet targets and training limits

| Observation area | Items | Focus |
| --- | --- | --- |
| Discussion tracking | A-D | Following the current point, answering it, adapting to changes, and needing repetition |
| Contribution structure | E-H | Idea order, requested support, completing a point, and task relevance |
| Turn-taking and reciprocity | I-L | Turn entry, continuing overlap, sharing cues, and acknowledging a direct contribution |
| Response to challenge | M-P | Observable changes after disagreement, their duration, participation changes, and response to feedback |
| Pressure-linked delivery change | Q-T | Event-linked changes in rate, hesitation, vocal delivery, movement, or participation against an earlier same-session baseline |

These are the marksheet's observation areas, not a total personality score. A rating above zero needs contextual evidence. N/O means the recording or opportunity cannot support a conclusion; missing means no answer was supplied. A model must abstain when its target or input evidence is unsupported. Visual-only evidence cannot train the current audio-based predictor. Item S remains excluded until supported vocal-change window features exist; T can use supported participation change, while visual-only answers remain saved and excluded.

Training uses reviewed human ratings as separate per-item targets. Feature/label associations are descriptive, and prediction is evaluated on held-out people and source groups with recorded counts and baseline comparisons. Neither an association nor a fitted model establishes psychological validity. Independently defined communication ratings have their own [annotation guidelines](docs/COMMUNICATION_ANNOTATION_GUIDELINES.md); they are session-level behavioral labels and do not come from archetype choices or model outputs. The current real records do not yet provide eligible, consented, independently reviewed training labels.

## Optional reference comparisons

Saved guarded group analysis can be imported without rerunning face recognition; PostgreSQL must be available:

```powershell
.runtime/venv/Scripts/python.exe run_psycon.py import-groups
.runtime/venv/Scripts/python.exe run_psycon.py build-references
```

The importer uses retained word timestamps and guarded speaker intervals. Imported transcripts are partial, their original Whisper-small provenance remains visible, and absent word confidences stay null. It reads recording times from the original video's metadata; missing times cause an explicit skip. Consent remains `not documented` unless independently established and supplied with `--consent documented`. Do not change that field merely to hide a limitation.

Group-derived Executive, Builder, Salesperson, and Negotiator lenses use an explicit project-defined selection framework and actual recording-level feature distributions. They are exploratory behavioral subsets, not empirically validated occupational archetypes. The corpus is not labeled with occupational identities, and A–T behavioral scores are not converted into role ground truth. Users can also construct a custom empirical reference from selected speakers in at least three reference recordings. Reference participants must be disjoint from analysis participants when their identities are known.

## Implementation and research limits

The pipeline, storage, baseline statistics, comparisons, exports, worker recovery, local reasoning, and evaluation workflow are implemented. Marker extraction is a transparent, unvalidated ruleset, not a validated semantic classifier. Topic control, interruption intent, paraphrasing, and other complex behaviors require manual review; manual event rates are explicitly labeled as partial annotation coverage. No participant counts, accuracies, reviewer scores, confidence intervals, or statistical significance are invented.

LLM inputs use a documented bounded transcript window and retrieved evidence. A valid evidence ID does not prove that a citation supports a claim; independent reviewers evaluate that separately. The current dataset does not establish longitudinal validity or validated prediction of psychologist ratings. See [the architecture and research protocol](docs/INSTRUMENT_ARCHITECTURE.md) and [requirement coverage](docs/INSTRUMENT_STATUS.md).

## Verify

The research workspace keeps its restrained green design across session inspection, participant answers, evidence, reports, research, and training. Long views include keyboard-accessible section navigation; wide tables scroll within their panels. Interface conventions and browser verification limits are recorded in [DESIGN.md](DESIGN.md).

```powershell
$env:PSYCON_TEST_DATABASE_URL = "postgresql://psycon:psycon@127.0.0.1:5432/psycon"
.runtime/venv/Scripts/python.exe -m pytest tests -o addopts= -q
.runtime/node/node.exe --check backend/static/instrument.js
.runtime/node/node.exe --check backend/static/instrument_review.js
.runtime/node/node.exe --check backend/static/instrument_reports.js
.runtime/node/node.exe tests/frontend/instrument_reports.cjs
.runtime/node/node.exe tests/frontend/instrument_workflow.cjs
```

The previous coaching, wearable, physiology, and face-linked workflows remain as legacy code. Their documentation is archived in [the previous README](docs/LEGACY_PRODUCT_README.md); they do not define the current prototype. The legacy Flask app also exposes this workspace at `/instrument`, but its startup still requires its original external services.
