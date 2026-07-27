# PSYCON Seven-Week Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and evaluate a research prototype that compares wrist-only, wearer-audio-only, and quality-aware combined stress classification using the supplied hardware and a reproducible server pipeline.

**Architecture:** ESP32 devices send small, numbered sensor and PCM chunks over HTTPS to a FastAPI Cloud ingest API. The API stores raw objects in a private Supabase Storage bucket and metadata in Supabase PostgreSQL; a separate batch worker performs audio attribution, feature extraction, synchronization, classification, and ablations. The physical build remains two modules only if two complete controller/power sets are present; otherwise the first integration is a single combined benchtop device with two logical streams.

**Tech Stack:** ESP32/Arduino/PlatformIO, I2C, I2S, Wi-Fi/HTTPS, FastAPI Cloud, FastAPI/Pydantic, PostgreSQL/Supabase Storage, NumPy/pandas/SciPy, openSMILE/librosa, PyTorch/torchaudio, Silero VAD, pyannote.audio, SpeechBrain, scikit-learn/XGBoost/LightGBM, pytest, TypeScript/Vitest.

---

**Owners:** Arjun Vijay Prakash - server, data, audio, ML, evaluation; Saksham Yadav - physical build, power, firmware, signal quality. Both owners sign off each integration gate.

## Decisions incorporated into this plan

1. **The server is FastAPI.** FastAPI Cloud is the easiest deployment target for the ingest/control API and can be used when Arjun receives account access.
2. **Cloud storage is external to the API instance.** Supabase PostgreSQL stores metadata and a private Supabase Storage bucket stores audio/sensor objects. The API never treats its local filesystem as durable.
3. **Heavy audio inference is a separate worker.** VAD, diarization, SpeechBrain, and openSMILE run locally in batch during the prototype. This avoids coupling ingestion to PyTorch memory/CPU requirements and FastAPI Cloud scale-to-zero behavior.
4. **The supplied list is the source of truth, but quantities remain a physical check.** It lists a generic 30-pin ESP32, TP4056 charger, 500 mAh LiPo per module, MAX30102, MPU6050, ADS1115, INMP441, MCP9808, and TEMT6000.
5. **ADS1115 is not a GSR circuit.** Student acquisition cannot include EDA until a documented low-voltage, current-limited analog front-end and electrodes pass an electrical review.
6. **The TP4056 is not used as a load-sharing charger.** The linked seller instructs users to disconnect the load while charging. No device is charged while worn.
7. **Libraries do not provide ground-truth labels.** They implement preprocessing, features, and classifiers. Labels come from the approved experimental condition plus age-appropriate participant self-report.
8. **Three modality runs are mandatory:** wrist only, audio only, and quality-aware combined late fusion. All use the same participant/session split and source windows.
9. **Mechanical talking is a named limitation.** The protocol pairs calm speech with challenge speech where approval permits, records task identity, and never claims that instructed speech represents natural conversation.
10. **School-student experiments require a study gate.** Team ownership of the experiment does not replace institutional ethics review, school permission, parental/guardian permission, participant assent, or a distress/withdrawal/deletion procedure.

### Saksham answer status

| Topic | Accepted answer | Remaining evidence |
| --- | --- | --- |
| Battery | Witty Fox 1S LiPo, 500 mAh per module, 3.7 V nominal, 4.2 V full, JST 2-pin | Verify polarity, maximum discharge current, physical condition, and delivered capacity |
| Charger | USB-C TP4056 with DW01A + FS8205A protection; no power path | Verify PROG resistor and actual charge current; keep load off during charging |
| Charging | Power-off charging is the MVP policy | Add written procedure and verify device cannot be worn/operated while charging |
| Runtime | Preliminary estimate: 5-7 hours light load, 2-4 hours heavy Wi-Fi | Measure every operating mode and run a logged discharge test |
| Low battery | Warn near 20%, flush unsent data, shut down cleanly, retain ESP32 brownout protection | Implement and calibrate thresholds against the actual board/cell discharge curve |
| microSD | Optional 16-32 GB FAT32 SPI buffer | It is not in the supplied list; if added, measure current and test forced-power-loss recovery |
| Microphone | Start 10-20 cm from mouth; compare with another speaker at 1 m | Validate level advantage, clothing/wind/resonance, I2S format, clipping, DC offset, and DMA loss |
| Wrist rates | MAX30102 100 Hz, MPU6050 100 Hz, ADS1115 128 SPS, MCP9808 1 Hz, TEMT6000 10 Hz | Verify sustainable bus timing, signal quality, storage, and feature stability |
| GSR | ADS1115 +/-4.096 V initial range, 128 SPS; Ag/AgCl electrodes with fixed placement | Document safe excitation/front-end and calibrate code-to-volts-to-conductance conversion |
| Timestamping | Timestamp at acquisition, then buffer and transport; use sequences | Implement and quantify loss, reboot recovery, and clock drift |
| Thermal/current | Required for charge, upload, retry, sensors, and long operation | All measurements remain open |

## Current state and file map

### Existing files to modify

| Path | Responsibility |
| --- | --- |
| `requirements.txt` | Current WESAD/ML packages; keep core and study dependencies separated into installable groups |
| `pyproject.toml` | Python version and root pytest configuration |
| `firmware/ear/src/main.cpp` | Current INMP441/BLE starter; becomes the two-board audio build if two controllers exist |
| `firmware/wrist/src/main.cpp` | Current I2C/BLE placeholder; becomes real wrist acquisition if two controllers exist |
| `firmware/ear/platformio.ini` | Audio firmware library pins and versions |
| `firmware/wrist/platformio.ini` | Wrist firmware library pins and versions |
| `ml/src/features.py` | Hardware-compatible wrist features and modality definitions |
| `ml/src/models/train.py` | Participant-grouped classifiers, metrics, and ablation runner |
| `protocol/src/types.ts` | Shared logical packet/window/result types |
| `tests/firmware/test_firmware_static.py` | Static pin, queue, and placeholder-removal checks |
| `tests/ml/test_wesad_pipeline.py` | Existing WESAD regression tests |
| `README.md` | Build truth, setup, experiment, caveats |
| `paper/main.tex` | Final measured method/results, never planned results |

### Files to create during implementation

| Path | Responsibility |
| --- | --- |
| `docs/hardware/BOM.md` | Exact quantities, photos/markings, revisions, voltages, and measured current |
| `docs/hardware/WIRING.md` | Verified pin map, I2C addresses, power rails, GSR front-end, and safety notes |
| `docs/study/PROTOCOL.md` | Approved task order, labels, consent/assent, stopping and deletion procedures |
| `docs/study/BIAS_REGISTER.md` | Bias, detection method, mitigation, residual limitation, and owner |
| `firmware/combined/` | One-controller benchtop build when two complete controller/power sets are unavailable |
| `protocol/spec/chunk.md` | Binary packet fields, byte order, CRC, idempotency, and response semantics |
| `protocol/fixtures/` | Golden audio and wrist packets shared across C++, Python, and TypeScript |
| `server/requirements.txt` | FastAPI Cloud compatible API dependencies |
| `server/app/main.py` | FastAPI application and health route |
| `server/app/api/` | Device authentication, sessions, chunks, status, and completion routes |
| `server/app/domain/` | Packet validation and acknowledgement rules without cloud SDK coupling |
| `server/app/storage/` | Local-test and Supabase object/metadata adapters |
| `server/migrations/` | PostgreSQL schema migrations |
| `tests/server/` | Route, idempotency, crash-window, authentication, and storage tests |
| `tools/simulate_device.py` | Numbered good/duplicate/missing/corrupt/retried upload fixture |
| `tools/smoke_cloud.py` | Health, auth, upload, retry, and status smoke test against a deployed URL |
| `worker/requirements.txt` | Compatible pinned audio/ML environment |
| `worker/psycon_worker/` | Decode, attribution, feature, alignment, and replay jobs |
| `tests/worker/` | Golden-waveform, attribution-gate, feature, and replay tests |
| `ml/src/hardware_features.py` | Actual-device wrist windowing and feature extraction |
| `ml/src/ablation.py` | Identical-split wrist/audio/combined experiment runner |
| `tests/ml/test_ablation.py` | Leakage, missingness, split, and result-schema tests |
| `reports/` | Generated attribution, ablation, power, and soak reports |

## Frozen build architecture

### Hardware topology decision

On the first day, count the physical parts and select exactly one topology:

- **Two-board topology:** separate wrist and audio ESP32 boards, each with a safe regulator/power path. This is preferred for wearable placement and maps to `firmware/wrist/` and `firmware/ear/`.
- **One-board topology:** one ESP32 services I2C wrist sensors and the I2S microphone. This is the easiest electrical/software integration when only one controller/power set exists and lives in `firmware/combined/`. It is a benchtop/proof build until microphone and wrist placement are physically validated.

Do not keep both topologies active after the Week 1 decision.

### Starting pin map

| Function | ESP32 GPIO | Device |
| --- | --- | --- |
| I2C SDA | 21 | MAX30102, MPU6050, ADS1115, MCP9808 |
| I2C SCL | 22 | MAX30102, MPU6050, ADS1115, MCP9808 |
| I2S WS | 25 | INMP441 WS |
| I2S BCLK | 26 | INMP441 SCK |
| I2S data input | 33 | INMP441 SD |
| Analog channel 0 | ADS1115 A0 | Reviewed GSR front-end output only |
| Analog channel 1 | ADS1115 A1 | TEMT6000 analog output |

Expected default I2C addresses are MAX30102 `0x57`, MPU6050 `0x68`, ADS1115 `0x48`, and MCP9808 `0x18`. Record what the scan actually finds. Never use a 5 V pull-up on an ESP32 GPIO; inspect the linked MAX30102 breakout because the listing warns that its logic may be 1.8 V.

### Starting sample configuration

These are implementation baselines to validate, not evidence that the final signal is adequate:

| Stream | Starting rate | Stored values |
| --- | ---: | --- |
| INMP441 | 16,000 Hz | Mono PCM16 converted from verified 24-bit I2S slots |
| MAX30102 | 100 Hz | Raw red/IR samples, FIFO overflow, contact and saturation flags |
| MPU6050 | 100 Hz | Raw calibrated accelerometer and gyroscope axes |
| Approved EDA front-end via ADS1115 | 128 samples/s, +/-4.096 V initial range | ADC code, volts, derived conductance only after circuit calibration |
| MCP9808 | 1 Hz | Local sensor temperature and quality/status |
| TEMT6000 via ADS1115 | 10 samples/s | ADC code and normalized ambient-light context |

The MAX30102 output is treated as PPG, not a clinical SpO2 measurement. MCP9808 is a skin-adjacent/environmental proxy, not core temperature. TEMT6000 is a quality/context covariate, not a stress marker.

### Power constraints

The linked cell is 500 mAh. With a conservative 80% usable fraction, 24 hours permits:

```text
500 mAh * 0.80 / 24 h = 16.7 mA average
```

Continuous active ESP32 Wi-Fi plus audio is expected to exceed that budget. Saksham's unmeasured planning ranges are 5-7 hours for light load and 2-4 hours for heavy Wi-Fi, but they are not results. The milestone requires an actual untethered runtime measurement. A separate supervised powered soak may establish 24-hour service.

The board is identified as a USB-C TP4056 with DW01A + FS8205A protection and no true power path. A likely 1.2 kOhm PROG resistor would set approximately 1 A, but the resistor and actual current must be verified because the cell is 500 mAh. Never exceed the cell's documented limit, and do not charge with the device worn, operating, or connected to GSR electrodes.

### Device-to-cloud contract

Each chunk contains a versioned little-endian header followed by raw bytes:

```text
protocol_version, header_bytes, device_id, session_id, boot_id,
stream_type, sequence, first_sample_index, captured_at_unix_us,
sample_rate, channels, sample_format, sample_count, payload_bytes,
crc32, battery_mv, queue_depth, quality_flags, error_counters
```

The server uses `(device_id, session_id, boot_id, stream_type, sequence)` as the idempotency key. It returns:

- `accepted` after the object and metadata record are durable;
- `already_present` when the same key and checksum already exist;
- `conflict` when a key is reused with different bytes;
- a retryable error when durable storage is not confirmed;
- a non-retryable validation error for malformed headers, lengths, or authentication.

One second of 16 kHz, 16-bit, mono PCM is 32,000 bytes. Continuous engineering mode produces roughly 2.76 GB/day before overhead. Research mode may gate uploads only after a continuous reference proves that the gate preserves feature values and speech coverage.

### FastAPI Cloud deployment

FastAPI Cloud hosts only the request/response API and status routes. Supabase stores private objects and PostgreSQL rows. The batch worker is separate.

Required environment variables are:

```text
DATABASE_URL
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
PSYCON_DEVICE_KEY_PEPPER
PSYCON_RAW_RETENTION_DAYS
PSYCON_ENV
```

Create them as encrypted FastAPI Cloud secrets. The credential owner logs in through the FastAPI Cloud CLI/dashboard; credentials are not pasted into source, committed, printed in logs, or embedded as shared plaintext in all devices.

API surface:

```text
GET  /health
POST /v1/sessions
POST /v1/chunks
GET  /v1/devices/{device_id}/status
POST /v1/sessions/{session_id}/complete
```

Object keys are immutable:

```text
raw/{pseudonymous_device_id}/{session_id}/{boot_id}/{stream_type}/{sequence}.bin
```

If storage succeeds and the metadata transaction fails, reconciliation records or removes the orphan according to the retention policy. If metadata succeeds without the expected object, processing state becomes `storage_missing` and the device receives a retryable acknowledgement.

## Feature and classification contract

### Wrist features

- PPG: pulse rate, pulse amplitude, inter-beat interval quality, RMSSD/SDNN only when enough valid beats exist.
- EDA: tonic level/slope and phasic response count/amplitude only after safe calibrated circuitry exists.
- Motion: acceleration magnitude, jerk, gyro energy, non-wear and motion-artifact flags.
- Temperature: mean/slope as local context.
- Light: ambient/contact context and PPG-quality interaction.

Primary hardware windows are 60 seconds with a 10-second hop because HRV features need more than the current WESAD 10-second window. A feature is marked missing rather than filled with zero when its quality requirement fails.

### Audio features

The worker applies signal checks, Silero VAD, pyannote diarization, and SpeechBrain ECAPA wearer verification. Only accepted wearer speech enters openSMILE `eGeMAPSv02` and audit features such as F0 summaries, RMS/dBFS, loudness, HNR, MFCC/spectral summaries, and speech/pause timing. Each 60-second model window requires at least five seconds of accepted voiced speech; otherwise it is `insufficient_audio`.

### Labels

The approved protocol records a condition label, task identifier, task start/end, and an age-appropriate self-report after each block. The primary binary comparison is calm versus task-induced challenge with self-report agreement. A window is `label_uncertain` when the task marker is missing or the approved self-report rule contradicts the task condition; uncertain windows do not enter primary training.

Libraries perform classification but do not generate these labels. Logistic regression is the preregistered primary classifier because it is interpretable and stable for a small pilot. Random forest, XGBoost, and LightGBM are secondary comparisons and must reuse the exact split.

### Mandatory ablation matrix

| Run | Input | Missing-audio rule | Purpose |
| --- | --- | --- | --- |
| A | Wrist physiology and quality/context | Not applicable | Primary baseline |
| B | Accepted wearer-audio features | Return `insufficient_audio`; report coverage | Audio-only evidence |
| C | Quality-aware late fusion of A and B | Fall back to A and record the fallback | Main novelty test |
| D | PPG only | Not applicable | Wrist component attribution |
| E | EDA only, if safe front-end exists | Not applicable | Wrist component attribution |
| F | Wrist physiology without then with motion/context | Not applicable | Motion/task confounding check |
| G | Combined without then with quality gating | Fall back only in gated run | Value of explicit missingness/quality |
| H | Population features versus participant calm-baseline deltas | Same as parent modality | Personalization sensitivity |

Runs A-C are required even if data quality is poor. E is omitted with an explicit `EDA hardware unavailable` result if the reviewed front-end is absent; it is never fabricated from an ADC-only connection.

Use participant-grouped outer evaluation, preferably leave-one-participant-out for the pilot, with any threshold selection and feature selection confined to training participants. Adjacent windows from a session never cross a split. Report balanced accuracy, macro-F1, sensitivity, specificity/false-positive rate, calibration, participant-bootstrap confidence intervals, per-participant results, accepted-audio coverage, missingness, and attribution errors.

## Bias and limitation register

| Risk | Required handling | Residual limitation to report |
| --- | --- | --- |
| Mechanical/instructed talking | Include calm-speaking and challenge-speaking blocks, record task, compare within speaking task | Natural conversation remains unvalidated |
| Speech availability differs by student/state | Report accepted seconds and `insufficient_audio` by participant/condition | Audio performance applies only when usable wearer speech exists |
| Age, puberty, sex, language, accent, speaking style | Participant-grouped splits; describe sample composition; do not use demographics as stress features | A small school sample cannot represent all students |
| Skin tone, fit, perfusion, motion, ambient light | Store PPG quality, contact, motion, and light; stratify failures | Reflective wrist PPG may fail unequally across participants |
| Motion and task identity | Include motion/task covariates and within-task analysis | Model may still learn protocol structure rather than stress |
| Speaker/bystander attribution | Held-out other speakers, overlap rejection, false acceptance/rejection report | One omnidirectional microphone cannot guarantee wearer isolation |
| Classroom noise and room identity | Record room/session/device, vary approved order, keep sessions grouped | Environment-specific performance may not transfer |
| Overlapping windows and repeated measures | Split by participant/session before fitting and bootstrap by participant | Effective sample size is participants, not windows |
| Label uncertainty | Combine task markers with approved self-report rule; exclude uncertain primary windows | Task-induced challenge is not a clinical stress diagnosis |
| Selection and observer effects | Record recruitment route, refusal/withdrawal, and recording awareness | Volunteers from one school may behave differently |
| Temperature interpretation | Call MCP9808 local/skin-adjacent temperature only | It cannot establish core temperature or causality |
| Small pilot and model search | Preregister primary model/run, report all ablations and confidence intervals | Negative or unstable results are expected and valid |

## Definition of done

By the end of Week 7, the repository and physical build must demonstrate:

1. A photographed, revision-specific BOM and wiring diagram matching the tested hardware.
2. Continuous acquisition with sample indices, timestamps, quality flags, gap counts, and no placeholder sensor values.
3. Authenticated, idempotent FastAPI Cloud ingestion with durable private object storage and PostgreSQL metadata.
4. Saved-session replay that produces deterministic features and records exact package/model versions.
5. Wearer attribution that reports VAD, diarization, false acceptance, false rejection, overlap rejection, and accepted coverage.
6. Student data collected only under the completed study gate, or a clearly marked adult/bench-only result if approval is not complete.
7. Wrist-only, audio-only, and quality-aware combined results from identical participant splits, plus diagnostic ablations that the available hardware supports.
8. A 24-hour supervised powered soak and a separate measured 500 mAh untethered runtime result.
9. A final report that separates measured results, uncertainty, bias, failure cases, and future work.

## Week 1 - Freeze hardware, safety, and protocol

**Goal:** Turn the supplied shopping list and starter code into one verified electrical design and one packet contract.

### Task 1: Physical inventory and topology

**Files:** Create `docs/hardware/BOM.md`; create `docs/hardware/WIRING.md`; modify the selected firmware directory.

- [ ] Photograph both sides of every board and record quantity, printed module/IC markings, connector polarity, measured rail voltage, I2C address, and whether a regulator/level shifter is present.
- [ ] Select the two-board topology only if two complete controller and safe power sets are physically present; otherwise create `firmware/combined/` from the working pin definitions and freeze one-board integration.
- [ ] Confirm the MAX30102 logic voltage with its actual schematic or measurements before it joins the ESP32 bus.
- [ ] Document the exact GSR front-end and electrodes. If absent, mark EDA electrically blocked and leave ADS1115 A0 disconnected from people.
- [ ] Confirm the TP4056 has DW01A + FS8205A, measure its PROG resistor and actual charge current, and record a power-off charge procedure with the load disconnected.
- [ ] Verify JST polarity and obtain the battery's maximum discharge-current evidence; inspect the cell for swelling or damage.
- [ ] Run the I2C scanner and record the discovered addresses in `docs/hardware/WIRING.md`.

Run:

```powershell
platformio run -d firmware/ear
platformio run -d firmware/wrist
python -m pytest tests/firmware -q
```

Expected: both existing starters compile and static tests pass before topology-specific changes begin.

### Task 2: Protocol v2 fixtures

**Files:** Create `protocol/spec/chunk.md`; create binary files in `protocol/fixtures/`; modify `protocol/src/types.ts`; add `protocol/tests/chunk.test.ts`; add `tests/protocol/test_chunk.py`.

- [ ] Specify every header field, width, signedness, unit, byte order, CRC coverage, maximum payload, idempotency rule, and error response.
- [ ] Produce one audio chunk and one wrist batch whose decoded values and checksums are written in the spec.
- [ ] Decode the same fixture in TypeScript and Python; firmware emits the same bytes in Week 3.

Run:

```powershell
cd protocol
npm test
npm run typecheck
cd ..
python -m pytest tests/protocol -q
```

Expected: both decoders agree exactly on all fixture fields and CRC values.

### Week 1 exit gate

- The build has a real parts/quantity record and one selected topology.
- No unsafe or assumed GSR connection exists.
- The charger, cell, regulator path, and logic levels are documented.
- Protocol fixtures decode identically in Python and TypeScript.

## Week 2 - Build and deploy the FastAPI ingest path

**Goal:** Make the easiest reliable cloud path work end-to-end before adding audio models.

### Task 3: Local FastAPI service

**Files:** Create `server/requirements.txt`, `server/app/main.py`, `server/app/api/`, `server/app/domain/`, `server/app/storage/`, `server/migrations/`, and `tests/server/`.

- [ ] Implement `/health`, session creation, binary chunk ingest, status, and session completion.
- [ ] Hash per-device API keys and use constant-time comparison; never store or log the plaintext key.
- [ ] Validate header version, lengths, stream limits, sequence, and CRC before storage.
- [ ] Write immutable objects through a storage interface, then insert metadata and return `accepted`; make exact retries return `already_present`.
- [ ] Add local filesystem and in-memory metadata adapters for tests, plus Supabase Storage/PostgreSQL adapters for deployment.
- [ ] Test unauthorized requests, malformed data, duplicate retry, key/checksum conflict, storage failure, database failure, and status gap reporting.

Run:

```powershell
python -m pip install -r server/requirements.txt
python -m pytest tests/server -q
fastapi dev server/app/main.py
```

Expected: tests pass and local `/docs` shows only the frozen API surface.

### Task 4: FastAPI Cloud and Supabase deployment

**Files:** Create `.fastapicloudignore`; create `tools/smoke_cloud.py`; modify `server/README.md`.

- [ ] Arjun receives FastAPI Cloud team/app access through the provider's login/team flow, not a credential committed to the repository.
- [ ] Create a Supabase PostgreSQL project and private `audio-chunks` bucket in a region allowed by the study data policy.
- [ ] Attach Supabase to the FastAPI Cloud app or create the pooled `DATABASE_URL`, then add all required values as encrypted secrets.
- [ ] Apply migrations from the trusted development environment before the API accepts device traffic.
- [ ] Deploy the subdirectory with `fastapi deploy server`.
- [ ] Run the cloud smoke tool with the deployment URL supplied through `PSYCON_API_BASE`; verify accepted upload, exact retry, conflict rejection, and status.

Run:

```powershell
fastapi login
fastapi deploy server
python tools/smoke_cloud.py --base-url $env:PSYCON_API_BASE
```

Expected: the smoke test exits zero, the private bucket contains one immutable test object, and PostgreSQL contains one matching chunk row despite the retry.

### Task 5: Failure-recovery simulator

**Files:** Create `tools/simulate_device.py`; add `tests/server/test_recovery.py`.

- [ ] Send numbered chunks, repeat one, omit one, corrupt one, disconnect once, and retry after the response is lost.
- [ ] Verify that received, missing, duplicate-attempt, conflict, and corrupt counts match the scripted scenario.

Run:

```powershell
python tools/simulate_device.py --base-url $env:PSYCON_API_BASE --scenario recovery
```

Expected: server status reports the intentional gap and corrupt rejection, while each accepted idempotency key has one durable object and row.

### Week 2 exit gate

- FastAPI Cloud deployment works with Arjun's supplied account access.
- Raw bytes live in private durable object storage, not an API-instance directory.
- Metadata, secrets, idempotency, and failure paths are tested.
- The API remains responsive without any audio ML package installed.

## Week 3 - Make acquisition continuous and measurable

**Goal:** Replace starter placeholders with real acquisition and prove that the network cannot stop sampling.

### Task 6: Continuous audio firmware

**Files:** Modify `firmware/ear/src/main.cpp` or `firmware/combined/src/main.cpp`; modify its `platformio.ini`; modify `tests/firmware/test_firmware_static.py`.

- [ ] Replace the 256-sample read plus 250 ms delay with continuous I2S DMA capture.
- [ ] Use independent capture, chunk, and upload tasks with bounded queues and observable high-water marks.
- [ ] Verify INMP441 channel selection and bit shift from a recorded tone and speech fixture before PCM16 conversion.
- [ ] Count clipping, DMA overrun, Wi-Fi reconnect, retry, dropped queue item, and reboot reason.
- [ ] Implement NTP sync records while retaining sample index as the monotonic source of duration.
- [ ] Use a bounded RAM retry queue because microSD is not in the supplied list; emit explicit gap records on overflow. If the measured outage requirement exceeds RAM, add a 16-32 GB FAT32 SPI card using append-only files and periodic flush/recovery tests.
- [ ] Place the microphone 10-20 cm from the mouth for the first fixture and measure wearer level against a speaker one metre away.

### Task 7: Real wrist acquisition

**Files:** Modify `firmware/wrist/src/main.cpp` or `firmware/combined/src/main.cpp`; modify its `platformio.ini`; add hardware fixture checks under `tests/firmware/`.

- [ ] Implement MAX30102 raw FIFO reads with contact, overflow, saturation, and ambient-light flags.
- [ ] Implement calibrated MPU6050 acceleration and gyro batches.
- [ ] Implement MCP9808 local temperature and TEMT6000 ADC reads.
- [ ] Configure MAX30102 at 100 Hz, MPU6050 at 100 Hz, MCP9808 at 1 Hz, and TEMT6000 at 10 Hz, then measure whether the selected I2C bus rate sustains every stream without loss.
- [ ] Implement ADS1115 EDA at 128 SPS and +/-4.096 V only after the approved front-end is documented; use Ag/AgCl electrodes at fixed spacing/pressure, calibrate codes to volts/conductance, or publish `eda_unavailable` rather than zeros.
- [ ] Timestamp each batch immediately at acquisition, then buffer and transport it with sample index, units, sequence, quality, and battery/status fields.
- [ ] Add a calibrated low-battery warning near 20%, queue flush, clean shutdown, and persisted reboot/brownout reason; keep hardware brownout protection enabled.

Run:

```powershell
platformio run -d firmware/ear
platformio run -d firmware/wrist
python -m pytest tests/firmware -q
```

For a one-board topology, replace both PlatformIO commands with:

```powershell
platformio run -d firmware/combined
```

Expected: the selected build compiles and no placeholder sensor values or deliberate capture sleeps remain.

### Task 8: Device-to-cloud stress test

- [ ] Record 30 minutes of continuous audio and all available wrist streams.
- [ ] Force a two-minute Wi-Fi outage and server error while sampling continues.
- [ ] Compare expected sample indices with accepted chunks, firmware counters, and server gap ranges.
- [ ] Measure battery current for capture-only, normal upload, reconnect, and backlog drain.
- [ ] Measure audio-only, audio+BLE, audio+Wi-Fi, worst-case retry, sensors-only, sensors+BLE, and sensors+Wi-Fi current as separate rows.
- [ ] Measure ESP32, TP4056, battery, and regulator temperature during charging, upload/backlog drain, and the longest safe run.

### Week 3 exit gate

- Audio playback has correct duration/pitch and no unexplained periodic gaps.
- Real wrist values and quality states reach the cloud.
- Acquisition continues through the forced outage; any bounded-RAM loss is explicit.
- The first measured runtime estimate replaces datasheet-only assumptions.

## Week 4 - Freeze the student protocol, attribution, features, and models

**Goal:** Make the experiment scientifically and ethically executable before student collection.

### Task 9: Study protocol and bias register

**Files:** Create `docs/study/PROTOCOL.md`; create `docs/study/BIAS_REGISTER.md`; create approved forms outside the public repository according to institutional policy.

- [ ] Record the ethics decision, school authorization, guardian permission, student assent, withdrawal/deletion path, distress stop rule, data roles, retention, and bystander-audio procedure.
- [ ] Define four analysis cells using only approved minimal-risk tasks: calm/quiet, calm/speaking, challenge/quiet, and challenge/speaking. The speaking cells use comparable verbal material so “was instructed to talk” is not identical to “stress.”
- [ ] Record task, room, device, operator, condition start/end, and approved age-appropriate self-report after every block.
- [ ] Predefine `label_uncertain`, exclusion, motion, non-wear, insufficient-audio, and aborted-session rules.
- [ ] Perform a pilot sensitivity/power analysis and describe the study as feasibility/pilot when the available participant count cannot support a population claim.
- [ ] Copy every row from the bias table in this plan into the live register with an owner and measurement artifact.

Expected: no student is recruited or recorded until the gate fields are signed and versioned.

### Task 10: Audio attribution worker

**Files:** Create `worker/requirements.txt`; create `worker/psycon_worker/audio/`; create `tests/worker/test_audio_quality.py`; create `tests/worker/test_attribution_gate.py`.

- [ ] Pin one compatible Python/PyTorch/torchaudio/Silero/pyannote/SpeechBrain set after a clean environment install.
- [ ] Add deterministic decode, clipping/level/noise checks, VAD intervals, diarization turns, enrollment embeddings, and wearer similarity scores.
- [ ] Return accepted wearer, other speaker, overlap, or unknown; only accepted ranges reach acoustic feature extraction.
- [ ] Store model identifiers, thresholds, enrollment version, source sample ranges, and decision scores.
- [ ] Test quiet speech, other speakers, overlap, TV/music, low level, clipping, walking, and fabric noise recorded through the actual INMP441 placement.

Run:

```powershell
python -m pip install -r worker/requirements.txt
python -m pytest tests/worker -q
```

Expected: unknown/other/overlap samples cannot contribute to an accepted wearer feature window.

### Task 11: Hardware-compatible features and ablation runner

**Files:** Create `ml/src/hardware_features.py`; create `ml/src/ablation.py`; create `tests/ml/test_ablation.py`; modify `ml/src/models/train.py` only where shared evaluation code is needed.

- [ ] Build 60-second, 10-second-hop wrist and audio windows from sample indices and gap masks.
- [ ] Preserve missing features and quality; do not convert a missing sensor or absent speech to zero.
- [ ] Split by participant/session before fitting transforms, thresholds, feature selection, or models.
- [ ] Implement runs A-H with one stored split manifest and a fixed primary logistic-regression configuration.
- [ ] Export metrics, confidence intervals, per-participant rows, coverage, missingness, and model/package versions.

Run:

```powershell
python -m pytest tests/ml/test_ablation.py -q
python -m pytest tests/ml/test_wesad_pipeline.py -q
```

Expected: synthetic leakage tests fail if a participant/session crosses a split, and WESAD regression tests still pass.

### Week 4 exit gate

- The study gate is complete or student recording remains blocked without blocking bench/adult engineering work.
- Wearer attribution has measured false-acceptance/false-rejection tradeoffs on actual microphone fixtures.
- All packages have a named role and compatible pinned environment.
- Core ablations A-C run from a synthetic or adult-developer synchronized fixture.
- Mechanical talking and every other listed bias has a measurement/mitigation entry.

## Week 5 - Pilot the full procedure and collect approved data

**Goal:** Prove that one complete session produces usable, synchronized, correctly labeled data before scaling collection.

### Task 12: Adult/developer dry run

- [ ] Run the exact approved procedure with consenting adult developers first.
- [ ] Verify device fit, recording indicator, physical mute, labels, self-report timing, Wi-Fi status, and stop/delete actions.
- [ ] Replay the session and inspect PPG, motion, EDA availability, temperature, light, wearer-speech acceptance, and time alignment.
- [ ] Correct protocol or implementation failures and increment the version before student collection.

### Task 13: Approved school-student sessions

- [ ] Confirm the signed gate for each session before device placement.
- [ ] Record pseudonymous participant ID, consent/assent status, protocol version, device ID, room, operator, task order, and start/end events.
- [ ] Monitor distress, device temperature, fit, signal quality, and recording state; stop immediately under the protocol rule.
- [ ] Confirm upload completeness, withdrawal/delete status, and session notes before the participant leaves.
- [ ] Never alter a label after seeing model predictions; corrections require a documented source-event error.

### Task 14: Pilot checkpoint

- [ ] Generate a blinded data-quality report after the first small batch without evaluating the final claim.
- [ ] Report valid wrist coverage, valid audio coverage, attribution errors, label uncertainty, motion, dropouts, and reasons for exclusions by participant.
- [ ] Continue collection only if the protocol and sensors are producing interpretable data; otherwise fix the measured failure and version the change.

### Week 5 exit gate

- At least one approved end-to-end session replays deterministically.
- Every data row traces to participant/session, protocol, device boot, chunk range, label event, and code version.
- No model result has influenced labeling or participant exclusion.

## Week 6 - Complete data, ablations, and reliability tests

**Goal:** Finish the evidence needed for the claim and quantify system runtime/recovery.

### Task 15: Freeze and run the modality experiments

- [ ] Freeze the participant/session split manifest before comparing models.
- [ ] Run wrist-only A, audio-only B, and combined C with the same source windows and primary model.
- [ ] Run diagnostic D-H where the hardware and sample size support them.
- [ ] Produce participant-level bootstrap intervals, per-participant metrics, coverage, missingness, calibration, and error tables.
- [ ] Analyze mechanical talking within comparable speaking tasks and state whether performance changes when task identity is controlled.
- [ ] Report the negative result if combined does not improve over wrist-only; do not retune the test set.

Run:

```powershell
python -m ml.src.ablation --manifest data/manifests/frozen_split.json --output reports/ablations
```

Expected: one generated report contains all mandatory runs, the exact same outer split, and explicit omitted-run reasons.

### Task 16: 24-hour powered engineering soak

- [ ] Use the reviewed external-power arrangement, not a worn charging setup.
- [ ] Run every available sensor, continuous engineering-mode audio, cloud ingest, and worker backlog instrumentation for 24 hours.
- [ ] Inject a Wi-Fi outage, API redeploy/restart, access-point restart, and device reconnect.
- [ ] Record expected/received samples, sequence gaps, retries, queue high-water marks, bytes/day, storage growth, latency, drift, memory, resets, current, voltage, and temperatures.

### Task 17: Untethered 500 mAh discharge

- [ ] Charge the disconnected cell under the documented procedure.
- [ ] Run the final operating mode from full charge to controlled shutdown while recording current/voltage and actual runtime.
- [ ] Calculate the capacity required for 24 hours from measured average current and report the hardware/duty-cycle revision.

### Week 6 exit gate

- All mandatory ablations and coverage/error analyses are generated from frozen splits.
- The powered service has a measured 24-hour completeness/recovery report.
- The 500 mAh cell has an honest measured runtime, even when far below 24 hours.
- Every bias register row has a result or explicitly measured residual limitation.

## Week 7 - Reproduce, freeze, and present

**Goal:** Make a third party able to reproduce the build and distinguish evidence from claims.

### Task 18: Clean-checkout reproduction

**Files:** Modify `README.md`; add `server/README.md`; add `worker/README.md`; generate `reports/reproducibility.md`.

- [ ] Install root, server, worker, protocol, and firmware dependencies from documented files in a clean environment.
- [ ] Run unit tests, local API, simulated upload, saved-session replay, WESAD regression, and frozen ablation report.
- [ ] Record exact OS, Python, Node, PlatformIO, package, model, firmware, protocol, and schema versions.

Run:

```powershell
python -m pytest
cd protocol
npm test
npm run typecheck
cd ..
platformio run -d firmware/ear
platformio run -d firmware/wrist
```

Expected: every applicable command passes from documented inputs; the selected one-board build uses its documented PlatformIO command instead.

### Task 19: Final documentation and paper

**Files:** Modify `README.md`; modify `paper/main.tex`; generate files under `reports/`.

- [ ] Replace planned statements with measured sample rates, coverage, attribution, ablation, runtime, power, and failure results.
- [ ] Include the school-study approvals/protocol version without publishing participant identities or private forms.
- [ ] State that mechanical speech, selected school population, omnidirectional audio, task leakage, sensor bias, small sample, and non-clinical labels limit generalization.
- [ ] Export tables and figures from scripts; do not type metric values manually into the report.

### Joint exit gate

- A third person can build the selected firmware, start or access the server, simulate/device-upload a session, inspect gaps, replay data, and regenerate the ablation report.
- The release contains exact hardware, data lineage, package versions, attribution metrics, modality ablations, bias register, and power/reliability results.
- Claims are limited to the observed protocol, participants, hardware, and coverage.

## Stop conditions and fallbacks

- If only one controller/power set exists, complete the combined benchtop prototype and describe the two-module wearable as unbuilt.
- If the safe GSR front-end is unavailable, omit EDA acquisition and run/report the remaining wrist ablations; never attach bare ADC inputs to participants.
- If direct Wi-Fi cannot sustain capture, keep the packet/server contract and test a dedicated gateway only after documenting the failure.
- If RAM buffering cannot survive the required outage, report the measured limit or add microSD as a separately documented hardware revision.
- If wearer false acceptance is unacceptable, return uncertain speech as unknown and narrow the claim; do not weaken the threshold for coverage.
- If student-study approval is incomplete, finish adult-developer/bench transport, attribution, power, and replay tests without collecting student data.
- If audio does not improve wrist-only classification, publish the negative ablation result and coverage/attribution conditions.
- If the 500 mAh cell does not last 24 hours, report its measured runtime and the required capacity; do not call a powered soak battery life.

## Self-review checklist

- [ ] Every supplied hardware part appears with a role and an electrical/measurement constraint.
- [ ] GSR, regulator, microSD, and second-module quantity gaps are explicit.
- [ ] FastAPI Cloud, Supabase durable storage, secrets, and separate worker boundaries are explicit.
- [ ] Current and planned packages are tied to specific processing stages.
- [ ] Labels come from the protocol and self-report, not a library prediction.
- [ ] Wrist-only, audio-only, and combined runs are mandatory and split identically.
- [ ] Mechanical talking and the broader bias register are measured and reported.
- [ ] School-student experiments remain behind the ethics/school/guardian/assent gate.
- [ ] The 500 mAh battery and TP4056 constraints prevent an unsupported 24-hour or worn-charging claim.

## References

- [FastAPI Cloud quick start](https://fastapicloud.com/docs/getting-started/)
- [FastAPI Cloud deployment behavior](https://fastapicloud.com/docs/builds-and-deployments/how-it-works/)
- [FastAPI Cloud Supabase integration](https://fastapicloud.com/docs/integrations/supabase-integration/)
- [FastAPI Cloud environment variables and secrets](https://fastapicloud.com/docs/builds-and-deployments/environment-variables/)
- [Supabase Storage](https://supabase.com/docs/guides/storage)
- [Supabase PostgreSQL connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [TP4056 module supplied](https://robocraze.com/products/tp4056-battery-charger-c-type-module-with-protection-1)
- [500 mAh LiPo supplied](https://robocraze.com/products/witty-fox-500mah-rechargeable-3-7v-lithium-polymer-battery)
- [MAX30102 module supplied](https://robocraze.com/products/max30102-pulse-oximeter-heart-rate-sensor-module)
- [MPU6050 module supplied](https://robocraze.com/products/mpu-6050-triple-axis-accelerometer-gyroscope-module)
- [ADS1115 module supplied](https://robocraze.com/products/16-bit-i2c-4-channel-ads1115-module)
- [INMP441 module supplied](https://robocraze.com/products/inmp441-mems-high-precision-omnidirectional-microphone-module-i2s)
- [MCP9808 module supplied](https://robocraze.com/products/7semi-mcp9808-i2c-temperature-sensor-breakout)
- [TEMT6000 module supplied](https://robocraze.com/products/smartelex-temt6000-ambient-light-sensor-breakout)
- [Espressif HTTP client](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/protocols/esp_http_client.html)
- [Espressif I2S](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html)
- [openSMILE Python](https://audeering.github.io/opensmile-python/)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [pyannote.audio](https://github.com/pyannote/pyannote-audio)
- [SpeechBrain ECAPA model](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
