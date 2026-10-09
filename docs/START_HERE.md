# Running and using PSYCON

The current workspace is the behavioral research instrument at [localhost:8008](http://localhost:8008). It holds session evidence, participant answers, review, training, and model inspection in one application. Older coach, wearable, and group consoles are historical workflows; use this workspace for new research records.

## Start the application

With Docker Desktop running, open PowerShell at the repository root and run:

```powershell
.runtime\venv\Scripts\python.exe run_psycon.py docker
```

The ignored `.env` must provide the PostgreSQL connection URL. Docker starts initialization, the web server, and the worker. The installed speech runtime image and authorized local speech models are prerequisites; see the [README](../README.md) and [operator runbook](POSTGRES_TRAINING_RUNBOOK.md) for setup. A failed database connection never starts a fallback database.

Original media and model files remain local. PostgreSQL stores records, paths, hashes, transcripts, evidence, normalized answers, retained annotation sources, jobs, and model lineage. Keep the worker running for queued processing, imports, interpretation, and training. Local Ollama is needed only for requested interpretations; measured session data remain available without it.

## Follow the behavioral workflow

1. **Inspect the conversation.** Open Sessions and review processing status, transcript, speaker timeline, measurements, and cited evidence. Failed attribution can leave a transcript available while withholding unsupported profiles.
2. **Map the participant.** Add an anonymous session participant and have a reviewer confirm the corresponding speaker cluster. Link a longitudinal person only when that association is known.
3. **Import the marksheet.** In Participants & answers, preview an individual or batch CSV/XLSX, select the worksheet, map columns and participant codes, and resolve validation errors before saving. Preserve the actual psychologist or reviewer identity and every correction revision.
4. **Review the observations.** Check context, fair opportunity, confidence, validity, and timestamped evidence against the [marksheet](PSYCON_Psychologist_Observation_Mark_Sheet.pdf) and [guide](PSYCON_Tendency_Flag_Guide.pdf). Zero, N/O, and missing are distinct. Saving answers preserves them even when they are excluded from training.
5. **Check readiness and train.** Training & models explains per-target exclusions. Record training consent, review answers and source ancestry, freeze an eligible snapshot, then queue fitting on the worker. Insufficient data must remain an explicit outcome.
6. **Inspect before activation.** Compare each model's held-out results with its baseline and inspect limitations. A completed fit is not automatically evaluated or active. Activation and rollback record the operator and reason.
7. **Review new predictions.** Predictions stay separate from human ratings and LLM interpretation. Use the speaker's measured patterns, context, evidence, and eligible earlier history to understand them. Archetype lenses are optional comparison tools.

The current real records do not yet supply eligible, consented, independently reviewed human training labels. Synthetic test models are implementation checks, not participant results. [Stage 2 and Stage 3](PSYCON_VISION.md#staged-delivery) still cover behavioral interface emphasis and the complete import-to-training journey.

## Correct, export, and delete

Corrections keep immutable human history and invalidate affected datasets and results. Withdrawals and deletion also identify dependent models that need retirement or retraining. Session exports retain actual stage states and provenance. Private answers, source spreadsheets, recordings, and credentials must stay out of Git.

Use the [runbook](POSTGRES_TRAINING_RUNBOOK.md) for coordinated PostgreSQL/local-file backup and verified restoration. The full original-media backup is still pending a suitable destination. The [coverage record](INSTRUMENT_STATUS.md) and [root checklist](../plan.md) track that gate.
