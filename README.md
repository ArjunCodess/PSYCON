# PSYCON

PSYCON is a behavioral observation and communication research instrument. It connects a person's speaker-specific talking patterns and discussion context with psychologist-reviewed observations from the A-T marksheet. It preserves timestamped evidence and personal history, and trains supervised models to predict eligible contextual ratings from conversational data.

The current ISEF prototype uses audio and transcripts. Its focus is what a person said and did in a particular exchange, how that relates to reviewed human observations, and how patterns differ across comparable conversations. The [v4.0 psychologist marksheet](docs/PSYCON_Psychologist_Observation_Mark_Sheet.pdf) and [answer interpretation guide](docs/PSYCON_Tendency_Flag_Guide.pdf) define the observation targets. Their [marksheet source](docs/PSYCON_Psychologist_Observation_Mark_Sheet.tex) and [guide source](docs/PSYCON_Tendency_Flag_Guide.tex) retain the exact definitions. Hardware, physiological inference, face recognition, and voice enrollment are outside this version.

A psychologist-reviewed profile here means a set of contextual ratings, evidence, confidence, and review records. It does not establish a personality type or diagnosis. Model agreement with those ratings needs held-out evaluation. See [the behavioral direction](docs/PSYCON_VISION.md) for the staged work and [current coverage](docs/INSTRUMENT_STATUS.md) for implementation limits.

## Run the research instrument

Run this one command from the repository root in PowerShell, with Docker Desktop running and the PostgreSQL URL in the ignored `.env`:

```powershell
.runtime\venv\Scripts\python.exe run_psycon.py docker
```

Open http://localhost:8008. Docker starts the web app and CUDA worker concurrently after applying migrations and idempotently queuing the original-video batch. Both services use the configured PostgreSQL, including Neon pooled URLs. Startup never substitutes the old local database. The Docker image extends the installed `psycon-week4-worker:latest` speech runtime; build that runtime first on a fresh machine. Registered Windows paths are explicitly mapped to the mounted workspace, and originals are mounted read only.

PostgreSQL is the only application database; a connection failure never creates another store. Original media and generated models stay in registered local paths; answers, bounded source spreadsheets, evidence, jobs, model manifests, and results live in PostgreSQL. The application remains a local single-user research instrument.

Session **Participants & answers** supports anonymous participants, reviewed speaker mappings, individual/batch CSV and XLSX previews, source downloads, direct entry, immutable corrections, independent review, and consent records. **Training & models** shows explicit exclusions, frozen snapshots, queued supervised fitting, held-out evaluations, exploratory limitations, deliberate activation, rollback, and predictions. Saving a sheet does not grant consent or establish training eligibility. A-T uses the actual v4.0 marksheet; independent communication labels use [the annotation guidelines](docs/COMMUNICATION_ANNOTATION_GUIDELINES.md).

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

```powershell
$env:PSYCON_TEST_DATABASE_URL = "postgresql://psycon:psycon@127.0.0.1:5432/psycon"
.runtime/venv/Scripts/python.exe -m pytest tests -o addopts= -q
.runtime/node/node.exe --check backend/static/instrument.js
.runtime/node/node.exe --check backend/static/instrument_review.js
.runtime/node/node.exe --check backend/static/instrument_reports.js
.runtime/node/node.exe tests/frontend/instrument_reports.cjs
```

The previous coaching, wearable, physiology, and face-linked workflows remain as legacy code. Their documentation is archived in [the previous README](docs/LEGACY_PRODUCT_README.md); they do not define the current prototype. The legacy Flask app also exposes this workspace at `/instrument`, but its startup still requires its original external services.
