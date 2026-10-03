# PSYCON communication pilot

Read [vision](PSYCON_VISION.md) for the reasoning, [architecture](COMMUNICATION_ARCHITECTURE.md) for the API/data contract, and [status](IMPLEMENTATION_STATUS.md) for implemented behavior and open release gates. This page is the operational runbook.

The personal coach builds on the existing Flask service and local speech models. Open `/coach` for voice enrollment, consented audio uploads, baseline progress, evidence, role-specific adjustments, practice goals and revocable sharing. Research consoles and ratings retain their existing meanings.

## Start locally

Use the existing Python environment with `requirements-backend.txt` and `requirements-psycon.txt` installed, including a compatible GPU PyTorch build. The speech models remain local. Community-1 still requires the existing Hugging Face access approval and `HF_TOKEN`.

Start the database and object store:

```powershell
docker compose up -d postgres minio
```

For a host Python web server, set the local object-store credential to match Compose:

```powershell
$env:PSYCON_S3_SECRET_KEY = 'psycon-local-object-secret'
$env:PSYCON_DATABASE_URL = 'postgresql://psycon:psycon@127.0.0.1:5432/psycon'
$env:PSYCON_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
```

Run a local Ollama service and pull `qwen3.5:4b`. This machine's portable runtime is at `G:\PSYCON-runtime\ollama\ollama.exe`, with models at `G:\PSYCON-runtime\models`. To restart it:

```powershell
$env:OLLAMA_MODELS = 'G:\PSYCON-runtime\models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_KEEP_ALIVE = '0'
$env:OLLAMA_NO_CLOUD = '1'
Start-Process -FilePath 'G:\PSYCON-runtime\ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden
```

Alternatively, use the optional Compose `coaching` profile for Ollama. The Docker GPU worker defaults to `http://ollama:11434`; a worker connecting to host Ollama must set `PSYCON_OLLAMA_URL=http://host.docker.internal:11434`. Only one inference worker should run on the 8 GB GPU. Model calls unload after completion.

Pin the installed model and preserve or generate the profile encryption key:

```powershell
python -m backend.communication.runtime configure-local
python -m backend.communication.runtime create-wearer --label 'My pilot account' --role leadership
python -m backend.communication.runtime web
```

The account command prints a newly issued wearer token. Enter it at `http://127.0.0.1:8000/coach`; the browser keeps it in memory and clears it on sign-out. In another terminal, run:

```powershell
$env:PSYCON_S3_SECRET_KEY = 'psycon-local-object-secret'
$env:PSYCON_DATABASE_URL = 'postgresql://psycon:psycon@127.0.0.1:5432/psycon'
$env:PSYCON_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
python -m backend.communication.runtime worker
```

Both runtime commands load the project `.env` without replacing explicit process settings. For GPU operation, retain the existing `PSYCON_DIARIZATION_DEVICE`, `PSYCON_SPEAKER_DEVICE`, and `PSYCON_WHISPER_DEVICE` settings. Enrollment is queued for the worker, not executed by the lightweight web server. Upload three clear 5–10 second clips, refresh until enrollment completes, then upload conversation audio. Failed enrollment can be replaced by another enrollment upload.

## History and interpretation

Eligible English conversations need verified wearer identity and at least three clean speech seconds. Baselines require five comparable conversations across three UTC calendar days and 30 minutes of usable wearer speech. Each conversation contributes one summary, so long recordings don't receive extra statistical weight. Separate microphone, setting, language and conversation-type cohorts avoid unsupported comparisons.

The first eligible reference is frozen; three subsequent independent conversations must exceed the robust deviation threshold in the same direction before a recurring change appears. Changing context or deleting evidence rebuilds reports and invalidates frozen goal references. Goal comparisons require three comparable post-goal conversations and do not claim that coaching caused an improvement. These rules are pilot heuristics, not clinically validated thresholds.

The local LLM classifies timestamped exchanges using JSON and supplied evidence IDs. Its model digest must match the pin. Missing models, invalid output and unavailable services fall back to measured coaching. Semantic claims remain disabled until independently reviewed examples meet the validation gate. Reviewer access cannot change consent, goals, context or evidence.

To evaluate semantic events, create a private dataset of at least 50 independently reviewed exchanges spanning all rubrics. Each example has a unique `id`, `roles`, `evidence` entries with IDs, and `expected` and `predicted` event lists. Events contain `type` and `evidence_ids`. Supported types are disagreement, criticism, objection, acknowledgement, clarification and question. Include supportive overlap and negative cases, not just positive examples. The top-level `model_digest` must identify the model evaluated.

```powershell
python -m validation.communication_semantics private-reviewed-exchanges.json private-semantic-validation.json
```

Set `PSYCON_SEMANTIC_VALIDATION` to that output path on the worker. A type needs at least ten predictions and 90% precision, in addition to the 50-exchange and role-coverage gates. No reviewed dataset or accuracy result is manufactured by the implementation. Human corrections override automated events. Precision on this set still does not establish generalization to new speakers or settings.

## API and existing sources

Pilot eligibility rules can be set before server and worker startup using `PSYCON_BASELINE_MIN_CONVERSATIONS`, `PSYCON_BASELINE_MIN_DAYS`, `PSYCON_BASELINE_MIN_SPEECH_S`, and `PSYCON_PATTERN_MIN_CONVERSATIONS`. Defaults are 5, 3, 1800 and 3; recurring support cannot be reduced below three independent conversations. Session observations appear immediately, and later comparisons explicitly reference the earlier baseline conversations.

All personal API routes use `/api/v1/communication`. Wearer tokens provide access to `/me`, `/me/enrollment`, `/conversations`, `/history`, `/goals`, `/grants` and `/context`. Context grants can read only `/context`; reviewer grants can read the profile, conversations, history and goals. Grants expire after seven days and can be revoked immediately. Context export omits raw media, voice embeddings, evidence text and other people's identity fields.

An existing operator credential can create wearer accounts through `POST /profiles` and explicitly link sources through `POST /source-links`. Links require `profile_id`, `identity_confirmed: true`, `context`, `session_id`, and either `type: group` with a `slot`, or `type: device`. Group links require recorded consent, a non-withdrawn participant and a current ready guarded PSYCON profile. Device session metadata must explicitly name `communication_profile_id`, and the session must be closed.

Group imports analyze the shared original PCM and retain source offsets from attributed words. Clean assigned windows do not establish full turn boundaries, so interruption, response-gap and turn-duration measures abstain for those imports. Device imports assemble one synchronized 16 kHz stream and reject gaps, overlaps, mixed devices and clock uncertainty above 5 ms. Split interrupted capture into separate conversations rather than silently joining speech around a gap.

## Retention and deletion

New personal uploads and enrollment clips are encrypted in `.psycon-private-spool`, or the shared `/private-spool` Compose volume. Neither location belongs to the research object store or application backup. Successful processing deletes raw media and full transcripts; only derived timing, measurements and bounded redacted evidence excerpts survive. Redaction is conservative and does not guarantee perfect anonymization.

Failed raw uploads expire after 24 hours. Deletion marks records before cleanup; worker retries remove locked files. Profile deletion revokes account access and grants, removes enrollment and histories, and cancels queued enrollment. Existing group and device research source recordings retain their original policies; linking does not silently delete a shared research recording. Existing backups need their own retention policy and are not rewritten by personal deletion.

## Wearable pilot

The ear firmware now drains I2S continuously and queues 0.5-second PCM chunks using Protocol v2. Four queued chunks bound memory; overflow records lost samples. NVS reserves sequence blocks before use to avoid reuse across reboot. Exact bytes retry until acknowledged; permanent server errors pause capture. Clock observations and status events use the existing API.

Capture starts paused. Provisioning requires physical BOOT-button presence at startup and expires after 60 seconds. Bond using the pairing passkey printed to the serial console, then write a configuration JSON to the encrypted/authenticated BLE characteristic. Fields are `ssid`, `password`, `api_url`, `token`, `session_id` and `device_id`. The first pilot accepts private-LAN HTTP URLs only, ending in `/api/v1`. After reboot, bonded BLE commands `resume` and `pause` control recording. Wi-Fi must reach the API through an explicitly configured private LAN binding; the default web server listens only on loopback.

Firmware compilation does not prove DMA continuity, clock accuracy, successful physical transport, battery runtime or wearer attribution. Those physical release gates remain open, and wrist firmware still uses placeholder sensor values.

## Verification

The account command prints a new credential once. Keep it outside Git; profile and grant tokens are stored only as hashes. Replacing `PSYCON_PROFILE_KEY` makes existing encrypted enrollment and pending uploads unreadable, so preserve the key across web/worker restarts and backups of retained embeddings.

For a container-only pilot, stop the host Ollama/web listeners before binding the same ports, then run `docker compose --profile coaching up --build -d`. Pull the model into that Ollama volume, inspect its digest, and set `PSYCON_OLLAMA_DIGEST` before recreating the worker. The worker uses `http://ollama:11434`; the host workflow above uses loopback. Do not run both inference workers on the 8 GB GPU. Provision a wearer with `docker compose exec api python -m backend.communication.runtime create-wearer --label 'My pilot account' --role leadership`.

The host worker accepts `--once`, `--poll-seconds`, and `--device-only`. The last option skips both communication and group jobs; it is for existing device processing only. Use the normal worker for personal enrollment and recordings.

If a request stays queued, check that a normal worker is running, its spool path matches the web process, its database is correct, and the encryption key is unchanged. Failed enrollment can be replaced with three new clips. Failed conversation analysis can be retried only while raw data exists. Semantic `awaiting_validation` is expected before review; missing Qwen or digest mismatch must not stop measured results. Future timestamps are rejected even when a device clock is only slightly ahead; correct its date or clock first.

Run the Python regression suite and protocol tests. The optional PostgreSQL lifecycle check uses a local database and removes only its own test records:

```powershell
$env:PSYCON_COMMUNICATION_TEST_DATABASE = 'postgresql://psycon:psycon@127.0.0.1:5432/psycon'
python -m pytest tests/backend/test_communication.py tests/backend/test_communication_postgres.py tests/validation/test_communication_semantics.py
python -m platformio run --project-dir firmware/ear
```

The software tests cover duplicate uploads, encryption, raw deletion, private access, grant revocation, asynchronous enrollment, baseline eligibility, repeated patterns, source continuity, semantic evidence validation and correction/deletion rebuilding. The two-wearer test uses simulated model output; it doesn't count as the human pilot or semantic accuracy evaluation.

On 2026-10-03, the regression run passed 275 Python tests with three unrelated optional checks skipped, and 20 protocol tests plus TypeScript checking passed. The ESP32 build used 17% static RAM and 82.6% flash. A live synthesized-speech smoke test completed real SpeechBrain enrollment, Whisper transcription, Community-1 wearer attribution, Qwen structured interpretation and raw deletion through PostgreSQL. The console displayed retained evidence and measurements without browser errors. Qwen used the installed RTX 4060; this host's existing speech environment used CPU PyTorch. Semantic events remained unavailable pending human annotation, as required. These checks don't establish human identity accuracy, coaching validity or physical-device performance.
