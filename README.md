# PSYCON

PSYCON is an audio-based longitudinal communication-analysis system that learns an individual's conversational patterns, represents them using speaker-specific and contextual evidence, compares them against personal baselines and reference communication archetypes, and uses that structured representation to generate evidence-grounded communication insights and coaching.

The current ISEF prototype is audio-only. Its contribution is the structured conversational representation, historical baselines, evidence lineage, and A/B/C research comparison. Hardware, physiological inference, face recognition, and voice enrollment are outside this version.

## Run the research instrument

Use the existing local Python runtime in two PowerShell terminals:

```powershell
.runtime/venv/Scripts/python.exe run_psycon.py web
```

```powershell
.runtime/venv/Scripts/python.exe run_psycon.py worker
```

Open [PSYCON](http://127.0.0.1:8001). SQLite and retained media live in the ignored `instance/instrument` directory. PostgreSQL, Docker, and object storage are not required for this workspace. It binds to localhost and is a single-user research tool, not a hosted multi-user deployment.

When an interpretation is requested, PSYCON reuses the configured local Ollama service. If the loopback service is stopped and the bundled `.runtime/ollama` executable exists, it starts that executable in the background with the project-local model directory and cloud access disabled. No model is downloaded, substituted, or repinned automatically. Container endpoints and independently installed runtimes must be started separately. You can also start the bundled runtime manually:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 ollama
```

The app uses Community-1 diarization and faster-whisper large-v3 through replaceable adapters. The launcher selects the available CUDA device or CPU and uses project-local model caches. The diarization model requires the applicable Hugging Face model access and `HF_TOKEN`. The local interpreter uses the configured Ollama model and records its actual digest. Missing models and rejected evidence references produce explicit failures, never substitute profiles.

Interpretation failures identify whether the service is unreachable, the selected model is absent, or its digest differs from `PSYCON_OLLAMA_DIGEST`. Digest mismatches remain blocked. Background-service logs are in `.runtime/logs/ollama-stdout.log` and `ollama-stderr.log`. Interpretation cites only the target speaker's supplied evidence IDs while retaining other speakers' words as interaction context, and truncated model responses are withheld.

## Use it

1. **Upload conversations.** Supply actual recording times, context, participant IDs, dataset split, and consent status. Each file becomes its own session; original audio is immutable. Supported formats are MP3, WAV, M4A, MP4, MOV, and OGG, with a 512 MiB / four-hour per-recording limit.
2. **Inspect speaker evidence.** Open a session for quality diagnostics, stage outputs, timeline, word timestamps, attributed transcript, features, and directed interactions. Ambiguous overlapping words remain unattributed.
3. **Connect personal history.** Add a person, select their target communication profile, and map their speaker label in each session. Baselines use only strictly earlier eligible sessions. Context-specific and global baselines remain separate; five comparable previous sessions are required for deviation flags.
4. **Compare and interpret.** Choose Executive, Builder, Salesperson, or Negotiator in the target dropdown; the choice persists for anonymous speakers and can be saved per person. Inspect recurring indicators, mathematical reference comparisons, personal changes, and A/B/C runs. Click evidence to review the original audio and neighboring utterances. The target is a comparison goal, not an identity label.
5. **Evaluate independently.** Research displays actual runs, numeric feature annotations, blinded reviewer forms, ordinal reviewer metrics, and paired inter-rater agreement. It shows `Not evaluated yet` until annotation data exist.
6. **Export or delete.** JSON, feature CSV, RTTM, transcript text, complete ZIP, and research exports retain model/configuration provenance and actual stage states. Deleting a session removes its retained media and analysis and invalidates derived history.

## Group-discussion reference profiles

Saved guarded group analysis can be imported without rerunning face recognition or connecting PostgreSQL:

```powershell
.runtime/venv/Scripts/python.exe run_psycon.py import-groups
.runtime/venv/Scripts/python.exe run_psycon.py build-references
```

The importer uses retained word timestamps and guarded speaker intervals. Imported transcripts are partial, their original Whisper-small provenance remains visible, and absent word confidences stay null. It reads recording times from the original video's metadata; missing times cause an explicit skip. Consent remains `not documented` unless independently established and supplied with `--consent documented`. Do not change that field merely to hide a limitation.

Group-derived Executive, Builder, Salesperson, and Negotiator lenses use an explicit project-defined selection framework and actual recording-level feature distributions. They are exploratory behavioral subsets, not empirically validated occupational archetypes. The corpus is not labeled with occupational identities, and A–T behavioral scores are not converted into role ground truth. Users can also construct a custom empirical reference from selected speakers in at least three reference recordings. Reference participants must be disjoint from analysis participants when their identities are known.

## Implementation and research limits

The pipeline, storage, baseline statistics, comparisons, exports, worker recovery, local reasoning, and evaluation workflow are implemented. Marker extraction is a transparent, unvalidated ruleset, not a validated semantic classifier. Topic control, interruption intent, paraphrasing, and other complex behaviors require manual review; manual event rates are explicitly labeled as partial annotation coverage. No participant counts, accuracies, reviewer scores, confidence intervals, or statistical significance are invented.

LLM inputs use a documented bounded transcript window and retrieved evidence. A valid evidence ID does not prove that a citation supports a claim; independent reviewers evaluate that separately. The current dataset does not establish longitudinal validity or occupational reference accuracy. See [the architecture and research protocol](docs/INSTRUMENT_ARCHITECTURE.md) and [requirement coverage](docs/INSTRUMENT_STATUS.md).

## Verify

```powershell
.runtime/venv/Scripts/python.exe -m pytest tests -o addopts= -q
.runtime/node/node.exe --check backend/static/instrument.js
.runtime/node/node.exe --check backend/static/instrument_review.js
.runtime/node/node.exe --check backend/static/instrument_reports.js
.runtime/node/node.exe tests/frontend/instrument_reports.cjs
```

The previous coaching, wearable, physiology, and face-linked workflows remain as legacy code. Their documentation is archived in [the previous README](docs/LEGACY_PRODUCT_README.md); they do not define the current prototype. The legacy Flask app also exposes this workspace at `/instrument`, but its startup still requires its original external services.
