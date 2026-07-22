# PSYCON: Psychophysiological Condition Observation Network

PSYCON is a research prototype for testing one narrow question: **does wearer-attributed speech acoustics improve short-term stress classification over wrist sensing alone?** The intended experiment compares wrist-only, audio-only, and quality-aware combined models on the same participant and session splits.

PSYCON is not a medical device. It does not diagnose a stress disorder or any mental-health, developmental, or neurological condition.

## Current repository state

The repository contains a working WESAD preprocessing and classical machine-learning pipeline, model artifacts, a TypeScript protocol package, and starter ESP32 firmware. It does not yet contain the production FastAPI server, real wrist sensor drivers, continuous audio upload, synchronized study data, or a validated combined model.

| Area | What works now | What still has to be built |
| --- | --- | --- |
| Wrist ML | WESAD loading, windowing, feature extraction, grouped split, and classical classifiers | Features from the actual MAX30102, ADS1115/GSR, MPU6050, MCP9808, and TEMT6000 build |
| Audio firmware | INMP441 I2S starter and simple RMS/energy/ZCR calculation | Continuous capture, Wi-Fi upload, queueing, checksums, and overrun accounting |
| Wrist firmware | I2C scan and placeholder BLE packets | Real sensor drivers, calibrated units, quality flags, and continuous batching |
| Protocol | TypeScript inference and validation tests | A binary device-to-server chunk contract shared with Python and firmware |
| Server | Not implemented | FastAPI ingest API, database/storage adapters, session status, and replay worker |
| Human study | Not started | Approved protocol, consent/assent, labels, synchronized recordings, and ablations |

The implementation sequence is in [docs/SEVEN_WEEK_BUILD_PLAN.md](docs/SEVEN_WEEK_BUILD_PLAN.md).

## Simplest working architecture

The most practical first version is:

```text
ESP32 sensor stream(s)
  -> HTTPS POST of small numbered chunks
  -> FastAPI Cloud ingest API
  -> private Supabase Storage for raw chunks
  -> Supabase PostgreSQL for metadata and labels
  -> separate local/batch Python worker for audio and ML
  -> wrist-only / audio-only / combined evaluation report
```

FastAPI Cloud is the recommended deployment target for the API. A local app that runs with `fastapi dev` can be deployed with `fastapi deploy`, and FastAPI Cloud can inject encrypted secrets. It should not be treated as the durable audio disk or as the first home for the PyTorch-based diarization and speaker models: cloud instances autoscale and may scale to zero, while the documented default is 0.5 vCPU and 500 MB memory. Keep requests short, write each accepted audio object to private durable storage, commit its metadata, and acknowledge only after both operations succeed.

For the seven-week prototype:

- Deploy the HTTP API to FastAPI Cloud.
- Connect a Supabase project for PostgreSQL and a private `audio-chunks` storage bucket.
- Store `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and per-device API-key hashes as secrets, never in Git or firmware source.
- Run VAD, diarization, speaker verification, openSMILE, and model experiments as a separate reproducible batch worker on the development computer. Move that worker to dedicated compute only after its resource use is measured.
- Keep a local storage adapter for offline bench testing. Student recordings must use only storage and regions approved by the study's data-protection review.

This is easier and more reliable than running FastAPI, raw files, PostgreSQL, and heavy audio models in one process.

## Hardware actually listed

The following table reflects the supplied part list. Quantities and exact breakout revisions still need to be recorded from the physical parts; the links establish the part type, not the exact board schematic.

| Part | Intended use | Interface / important constraint |
| --- | --- | --- |
| Generic 30-pin ESP32 development board | Sampling, timestamping, buffering, Wi-Fi | Exact module and regulator are unverified; the PlatformIO target is currently generic `esp32dev` |
| [TP4056 Type-C charger with protection](https://robocraze.com/products/tp4056-battery-charger-c-type-module-with-protection-1) | Charge one 1S cell | Saksham identifies DW01A + FS8205A protection and no true load sharing. The likely 1 A charge current assumes a 1.2 kOhm PROG resistor and must be verified on the board. The load remains off while charging |
| [Witty Fox 500 mAh 3.7 V LiPo](https://robocraze.com/products/witty-fox-500mah-rechargeable-3-7v-lithium-polymer-battery) | Prototype power | 1S, 500 mAh per module, JST 2-pin, 3.7 V nominal and 4.2 V full. Verify polarity and maximum discharge current; inspect for swelling/damage before every charge |
| [MAX30102](https://robocraze.com/products/max30102-pulse-oximeter-heart-rate-sensor-module) | Raw reflective PPG and pulse features | I2C; the linked listing warns that this revision may use 1.8 V logic. Inspect the board before connection and never pull an ESP32 I2C line up to 5 V |
| [MPU6050](https://robocraze.com/products/mpu-6050-triple-axis-accelerometer-gyroscope-module) | Motion and artifact context | I2C; accelerometer and gyroscope must be calibrated in the final orientation |
| [ADS1115](https://robocraze.com/products/16-bit-i2c-4-channel-ads1115-module) | External analog conversion | I2C, four single-ended channels, up to 860 samples/s; it is an ADC, not a GSR sensor by itself |
| [INMP441](https://robocraze.com/products/inmp441-mems-high-precision-omnidirectional-microphone-module-i2s) | 16 kHz speech capture | I2S, 24-bit data in 32-bit slots, 1.8-3.3 V, omnidirectional and bottom-ported |
| [MCP9808](https://robocraze.com/products/7semi-mcp9808-i2c-temperature-sensor-breakout) | Skin-adjacent or enclosure temperature | I2C; it measures local sensor temperature, not core body temperature |
| [TEMT6000](https://robocraze.com/products/smartelex-temt6000-ambient-light-sensor-breakout) | Ambient-light/contact context | Analog output to an ADS1115 channel; treat it as a quality/context signal, not direct evidence of stress |

### Missing or unresolved hardware

- **GSR/EDA front-end and electrodes:** ADS1115 alone must not be connected to skin. The build needs a documented low-voltage, current-limited excitation/front-end and Ag/AgCl electrodes with fixed spacing/pressure before electrical review and human use.
- **Power regulation:** a protected charger is not a regulated ESP32 supply or a true power-path charger. Record how the ESP32 is powered across the LiPo discharge range.
- **Offline storage:** no microSD module appears in the supplied list. The first build therefore uses a bounded RAM retry queue and reports gaps. If outage tolerance requires it, add a 16-32 GB FAT32 SPI microSD, use append-only files with periodic flushes, and test recovery after forced power loss.
- **Physical quantities:** two physical modules require two ESP32 boards, two safe supply paths, and normally two cells. If only one of each exists, build a combined benchtop prototype first and treat wrist/audio as logical modalities. Do not claim a two-module wearable until the quantities are verified.
- **Human controls:** the recording LED and physical microphone mute switch are currently absent and must be added before participant recording.

### Status from Saksham's hardware review

Resolved decisions:

- Use power-off charging for the MVP; the device never operates or is worn while charging.
- Treat the TP4056 board as charger/protection only, not a power-path supply.
- Mount the microphone 10-20 cm from the mouth as the first placement and measure wearer level against another speaker one metre away.
- Timestamp every sensor batch at acquisition, before buffering or Wi-Fi transport, and attach sequence numbers.
- Use raw PPG plus contact, saturation, motion, and FIFO-overflow flags.

Still unmeasured or unimplemented:

- Battery maximum discharge current, exact charge current, ESP32 low-voltage cutoff, brownout/recovery, and real light/heavy-load runtime.
- Audio-only, BLE, Wi-Fi, upload/retry, sensor-only, and combined current draw.
- ESP32, charger, battery, and regulator temperature during charge, upload, and long runs.
- INMP441 sample rate/bit alignment/channel/gain/clipping/DC offset, DMA loss, queue overflow, and enclosure/clothing noise.
- Low-battery warning, queue flush, graceful shutdown, recording LED, and physical mute.

## Proposed pin map

This map matches the starter firmware and avoids known input-only/boot-strap pins. Confirm labels on the exact 30-pin board before wiring.

| Bus / signal | ESP32 pin | Connected part |
| --- | --- | --- |
| I2C SDA | GPIO21 | MAX30102, MPU6050, ADS1115, MCP9808 |
| I2C SCL | GPIO22 | MAX30102, MPU6050, ADS1115, MCP9808 |
| I2S WS | GPIO25 | INMP441 WS |
| I2S BCLK | GPIO26 | INMP441 SCK |
| I2S data in | GPIO33 | INMP441 SD |
| ADS1115 A0 | External analog only | Approved GSR front-end output |
| ADS1115 A1 | External analog only | TEMT6000 output |

Typical default I2C addresses are expected to be distinct (`MAX30102 0x57`, `MPU6050 0x68`, `ADS1115 0x48`, `MCP9808 0x18`), but firmware must scan and record the addresses found on the physical build. Power every bus pull-up from a logic-safe rail.

### Starting acquisition settings

These are Saksham's initial settings and must be validated on the integrated build:

| Stream | Starting configuration |
| --- | --- |
| MAX30102 | 100 Hz raw red/IR PPG |
| MPU6050 | 100 Hz accelerometer and gyroscope |
| Reviewed GSR front-end through ADS1115 | 128 samples/s, +/-4.096 V gain initially; reduce the range only after measuring circuit output |
| MCP9808 | 1 Hz |
| TEMT6000 through ADS1115 | 10 Hz |
| INMP441 | 16 kHz mono; verify I2S bit alignment before PCM16 conversion |

For the LiPo, 500 mAh at an assumed 80% usable capacity permits only about 16.7 mA average for 24 hours. Saksham's preliminary, unmeasured estimates are roughly 5-7 hours at light load and 2-4 hours under heavy Wi-Fi use; only a logged discharge test may be reported as runtime.

## Device and server data path

Audio is captured at 16 kHz mono. One second of PCM16 is 32,000 bytes, or about 2.76 GB/day before protocol overhead if uploaded continuously. Engineering mode sends continuous PCM so completeness and feature fidelity can be measured. A later research mode may send speech-active segments plus explicit silence/gap records, but only after comparison with the continuous reference.

Each device packet needs at least:

```text
protocol_version, device_id, session_id, boot_id, sequence,
first_sample_index, captured_at_unix_us, stream_type,
sample_rate, sample_format, sample_count, payload_bytes, crc32,
battery_mv, queue_depth, quality_flags, error_counters
```

The idempotency key is `(device_id, session_id, boot_id, stream_type, sequence)`. A retry of the same bytes returns `already_present`; the same key with different bytes is a conflict. Capture, chunking, and upload run independently so a slow network cannot block I2S or sensor reads.

## Libraries and what they do

Libraries provide implementations; they do not create valid stress labels or prove that a classifier works on students. Labels must come from the approved study protocol, task timing, and participant self-report. Training and evaluation must keep every participant out of either train or test, never both.

### Already used in this repository

| Package | Current role |
| --- | --- |
| NumPy, pandas, SciPy | Signal tables, resampling, numerical features, peak detection |
| scikit-learn | Grouped splitting, scaling, logistic regression, random forest, metrics |
| XGBoost, LightGBM | Optional gradient-boosted classifiers |
| joblib | Saved scikit-learn pipeline |
| matplotlib, seaborn | Reproducible charts and confusion matrices |
| pytest | Python and static firmware tests |
| TypeScript, Vitest | Shared protocol validation and inference tests |
| PlatformIO, Arduino framework, NimBLE-Arduino | Current ESP32 builds and BLE starter code |

The current code trains a rule baseline, logistic regression, random forest, XGBoost, and LightGBM on WESAD wrist features. WESAD results are development baselines only; they are not results from this hardware or the school-student population.

### Planned server and audio packages

| Package | Planned role |
| --- | --- |
| `fastapi[standard]`, Pydantic | HTTP API, validation, local server, FastAPI Cloud CLI |
| SQLAlchemy/SQLModel, Alembic, psycopg | PostgreSQL models, migrations, and connections |
| Supabase Python client | Private object storage and service access |
| HTTPX | API and simulated-device integration tests |
| librosa, openSMILE | Auditable audio features and eGeMAPSv02 functionals |
| PyTorch/torchaudio, Silero VAD | Local voice-activity detection |
| pyannote.audio | Speaker-turn diarization |
| SpeechBrain | Enrollment embeddings and wearer verification |

Versions will be pinned after the first working install because PyTorch, torchaudio, pyannote, and SpeechBrain must be tested as one compatible set.

## Experiment and mandatory ablations

The primary analysis uses identical windows, labels, participant groups, and evaluation metrics for all variants:

1. **Wrist only:** PPG-derived pulse features, approved EDA features, motion, and quality/context signals.
2. **Audio only:** wearer-accepted acoustic features. Windows without enough accepted speech return `insufficient_audio`; they are not silently dropped from coverage reporting.
3. **Combined:** quality-aware late fusion. It uses both streams when valid and falls back to wrist-only when audio is absent.

Diagnostic ablations should include PPG-only, EDA-only, wrist physiology with/without motion context, combined fusion with/without quality gating, and population versus participant-baseline features. Report balanced accuracy, macro-F1, sensitivity, specificity/false-positive rate, calibration, confidence intervals, per-participant results, accepted-speech coverage, and missingness.

The outcome label is not “whatever a library predicts.” The study must predefine calm/stressor segments and collect an approved age-appropriate self-report. Windows with contradictory or missing ground truth remain uncertain or are analyzed separately.

## Biases and limitations to record

- **Mechanical or instructed talking:** a participant may speak unnaturally because the protocol asks them to talk. This cannot be removed after collection. Use the same speaking task in calm and stress conditions where possible, record task identity, compare within speaking task, and state that natural conversation is not validated.
- **Speech-availability bias:** quiet participants and silent stress periods produce fewer audio windows. Report coverage for every participant and never evaluate audio only on an unexplained easy subset.
- **Age, puberty, sex, language, accent, and speaking style:** these affect voice features and may be spuriously predictive in a small school sample. Use participant-grouped splits and report the sample composition without treating demographics as stress signals.
- **Skin tone, fit, perfusion, movement, and ambient light:** these affect wrist PPG. Record contact quality and motion, use TEMT6000 as context, and stratify signal failure rather than hiding it.
- **Motion/task leakage:** timed arithmetic, speaking, and movement can identify the experimental task. Balance or model task and motion; do not claim the model has isolated stress if it only recognizes the protocol.
- **Speaker-attribution error:** an omnidirectional microphone records bystanders. Reject overlap and uncertainty, report false acceptance/rejection, and keep the raw bucket private.
- **Room and device bias:** classroom noise, temperature, Wi-Fi behavior, microphone placement, and device unit can leak session identity. Randomize order where approved and keep device/session groups out of both train and test.
- **Overlapping windows:** adjacent windows are highly correlated. Split by participant/session before windowing or group every derived window with its source session.
- **Small and selected sample:** one school cannot support population-wide or clinical claims. Report confidence intervals and negative results.
- **Observer and consent effects:** being recorded or evaluated can alter behavior. Include this as a study limitation.

## Run the existing code

Python 3.11 or newer is required.

```powershell
python -m pip install -r requirements.txt
python -m pytest
python main.py --limit-subjects 1
```

The WESAD command requires raw subject pickle files under `data/raw/wesad/`. The repository currently contains processed features but may not contain the raw licensed dataset in a clean checkout.

Run the TypeScript protocol tests:

```powershell
cd protocol
npm install
npm test
npm run typecheck
cd ..
```

Build both current firmware starters:

```powershell
python -m pip install platformio
platformio run -d firmware/ear
platformio run -d firmware/wrist
```

## Study gate for school students

Because participants are school students and may be minors, the team doing the experiments does not remove the need for independent approval. Before recruitment or recording, obtain the applicable institutional ethics decision, school authorization, parental/guardian permission, participant assent, a withdrawal and deletion process, a distress/stop procedure, approved task limits, secure pseudonymous IDs, an audio retention period, and a bystander-recording procedure.

No participant should wear the unit while it is charging. Bench and voluntary adult-developer recordings can validate electronics, transport, and signal processing before the study gate is complete.

## Repository layout

```text
main.py                         Existing WESAD experiment entry point
ml/src/                         Current preprocessing, features, and classifiers
firmware/wrist/                 Current wrist firmware starter
firmware/ear/                   Current audio firmware starter
protocol/                       Current TypeScript contracts and tests
tests/                          Current Python and firmware-static tests
results/                        Existing WESAD-derived artifacts
paper/                          LaTeX paper scaffold
docs/SEVEN_WEEK_BUILD_PLAN.md   Active implementation plan
```

The plan adds `server/`, `worker/`, hardware-compatible feature code, packet fixtures, study manifests, and evaluation reports. They are future paths until implemented.

## References

- [FastAPI Cloud quick start](https://fastapicloud.com/docs/getting-started/)
- [FastAPI Cloud deployment behavior](https://fastapicloud.com/docs/builds-and-deployments/how-it-works/)
- [FastAPI Cloud Supabase integration](https://fastapicloud.com/docs/integrations/supabase-integration/)
- [FastAPI Cloud secrets](https://fastapicloud.com/docs/builds-and-deployments/environment-variables/)
- [Supabase Storage](https://supabase.com/docs/guides/storage)
- [Espressif I2S documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html)
- [openSMILE Python documentation](https://audeering.github.io/opensmile-python/)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [pyannote.audio](https://github.com/pyannote/pyannote-audio)
- [SpeechBrain ECAPA speaker verification model](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
