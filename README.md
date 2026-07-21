# PSYCON: Psychophysiological Condition Observation Network

PSYCON is a two-module research wearable for testing whether **wearer-attributed speech acoustics improve acute-stress estimation over wrist physiology alone**. The project combines a continuously logging wrist module, a Wi-Fi audio module, a server-side acoustic pipeline, and the existing WESAD-based machine-learning pipeline.

This is a research prototype, not a medical device. It does not diagnose stress disorders, depression, anxiety, ADHD, autism, PTSD, or any other condition.

## Current state

The purchased components have been powered and checked individually. The repository already contains a reproducible WESAD preprocessing and classical-ML pipeline, result artifacts, shared TypeScript protocol code, firmware starters, tests, and paper scaffolding.

The integrated system does **not** exist yet. In particular, the current firmware does not provide production-quality continuous capture, reliable upload, real wrist acquisition, clock synchronization, wearer identification, or 24-hour power behavior. The next milestone is defined in the [seven-week build plan](docs/SEVEN_WEEK_BUILD_PLAN.md).

## Scope for the next seven weeks

Build and validate one end-to-end path:

```text
INMP441 microphone
  -> ESP32 I2S DMA capture
  -> numbered one-second PCM chunks
  -> Wi-Fi + persistent HTTPS
  -> durable server ingest and acknowledgement
  -> speech and quality detection
  -> speaker diarization and wearer verification
  -> acoustic feature extraction
  -> alignment with wrist windows
  -> wrist-only, audio-only, and late-fusion comparison
```

The success criterion is evidence, not a polished consumer product. By Week 7 the system must complete a repeatable 24-hour engineering soak, quantify gaps and power use, reject audio that cannot be assigned safely to the wearer, and produce a reproducible modality comparison.

The following are outside this milestone:

- Mental-health or neurodevelopmental diagnosis.
- NLP-based interpretation of what somebody says.
- A mobile application, cloud product, alerts, recommendations, or chatbot.
- Deep learning trained from a small private dataset.
- Claims that voice alone can determine whether somebody is stressed.

## Hardware

### Wrist module

- ESP32-WROOM-32E development board
- MAX30102 for PPG
- MPU6050 for motion
- ADS1115 with GSR electrodes
- TP4056 charger module and LiPo battery
- MCP1700 as a clean sensor rail only

The wrist module logs continuously, including while nobody is speaking or the audio server is unavailable. It must preserve raw samples or documented batches, sequence numbers, timestamps, battery state, contact/quality flags, and error counters.

### Audio module

- ESP32-WROOM-32E development board
- INMP441 omnidirectional I2S microphone
- TP4056 charger module and LiPo battery
- A microSD module is the recommended addition for outage buffering

The microphone is sampled at **16 kHz, mono**. The INMP441 places 24 useful bits in 32-bit I2S slots; firmware converts these to signed PCM16 only after verifying the bit shift and channel configuration with known recordings. Capture runs continuously through I2S DMA and must never wait for a network request.

### Existing wiring

Wrist I2C uses `GPIO21` for SDA and `GPIO22` for SCL. The MAX30102, MPU6050, and ADS1115 share this bus; MPU6050 `AD0` and ADS1115 `ADDR` are grounded, and ADS1115 `A0` reads the GSR circuit.

| INMP441 | ESP32 |
| --- | --- |
| VCC | 3.3 V |
| GND | GND |
| WS | GPIO25 |
| SCK | GPIO26 |
| SD | GPIO33 |
| L/R | GND |

The MCP1700 must not power the ESP32 because its current capability is intended for the sensor rail. The present TP4056 arrangement also cannot be assumed to provide safe load sharing while charging; Saksham must identify the exact board and validate its power path before any worn charging test.

## Audio transport

The primary path is **ESP32 -> Wi-Fi access point -> HTTPS server**. BLE and a phone gateway remain contingency options only if measured ESP32 Wi-Fi power or reliability makes direct upload unusable.

Firmware uses independent FreeRTOS tasks:

1. **Capture task.** It continuously drains I2S DMA into double or triple buffers and records overruns.
2. **Chunk task.** It creates one-second chunks with an immutable header and CRC/checksum.
3. **Upload task.** It sends binary bodies over a persistent authenticated HTTPS connection and retries without blocking capture.
4. **Storage task.** It writes unacknowledged chunks to microSD and removes them only after a durable server acknowledgement.

Each request body uses a versioned, fixed-size little-endian binary header followed by PCM bytes. The header includes `protocol_version`, `device_id`, `session_id`, `boot_id`, `sequence`, `first_sample_index`, capture time, sample rate, format, sample count, payload length, CRC32, battery voltage, and clipping/overrun flags. HTTPS headers carry the device credential and idempotency key. The server's idempotency key is `(device_id, session_id, boot_id, sequence)`, so retrying a request cannot process the same audio twice.

Audio is uploaded as `application/octet-stream`; JSON/base64 would add bandwidth and parsing work without adding information. At 16 kHz, 16-bit mono PCM, raw audio is 32 kB/s, about **2.76 GB/day per device** before protocol overhead. One second is a sensible starting chunk because it fits several buffers in ESP32 RAM while keeping retry cost and HTTP overhead manageable.

Internal flash is not a 24-hour queue. If microSD is not added, the device can buffer only a short outage in RAM and the project must report the resulting data loss honestly. The server acknowledges a chunk only after both its metadata and bytes are durably stored.

Two operating modes will be evaluated:

- **Engineering mode** uploads continuous PCM so missing samples, feature fidelity, bandwidth, and power can be measured.
- **Research mode** still captures continuously but uploads speech-active regions with pre/post-roll plus explicit silence intervals, after the gate has been validated against engineering mode.

Compression is deferred until the raw baseline works. IMA ADPCM or Opus can be evaluated later only by comparing downstream pitch, loudness, and eGeMAPS stability against the PCM reference.

## What happens on the server

The first implementation should stay small: a FastAPI ingest service, PostgreSQL metadata, files on a controlled server volume, and a separate Python worker. The ingest service writes to a temporary file, flushes it, atomically renames it, commits the chunk record, and only then acknowledges; startup reconciliation handles an orphaned file from a crash between those steps. Redis, Kafka, MinIO, Kubernetes, and a public cloud speech API would add operations work before the core experiment is proven.

```text
HTTPS request
  -> authenticate device
  -> validate header, length, order, and checksum
  -> write bytes and metadata durably
  -> acknowledge idempotently
  -> assemble rolling analysis windows
  -> measure signal quality and detect speech
  -> diarize speakers
  -> verify wearer
  -> extract features only from accepted wearer speech
  -> align with wrist features and quality masks
  -> store features, results, and deletion status
  -> delete raw audio according to the approved retention rule
```

Processing is asynchronous, so a slow acoustic worker cannot hold up capture. The server records every missing, duplicate, late, corrupt, or rejected chunk, which makes a 24-hour completeness claim auditable.

## Distinguishing the wearer from the surroundings

A single omnidirectional microphone cannot physically isolate its wearer, so this is a staged rejection problem rather than a magic filter:

1. **Signal quality** rejects clipping, extremely low level, excessive noise, and corrupt windows.
2. **Voice activity detection** separates speech from silence and non-speech using a local streaming model such as [Silero VAD](https://github.com/snakers4/silero-vad).
3. **Speaker diarization** separates turns from different speakers using [pyannote.audio](https://github.com/pyannote/pyannote-audio).
4. **Wearer verification** compares each diarized turn with an enrolled wearer template using a 16 kHz ECAPA-TDNN embedding model such as [SpeechBrain's VoxCeleb model](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb).
5. **Abstention** marks overlapping speakers, TV/music, weak similarity, and too little voiced audio as unknown; those segments never enter stress inference.

Enrollment should collect at least three 30-second samples from the wearer in quiet, normal, and moderately noisy conditions. The verification threshold must be tuned with the actual microphone and placement against the wearer, at least three other speakers, a television, music, overlap, walking, and fabric noise. Report false acceptance, false rejection, diarization error rate, and accepted-speech coverage.

Placement matters as much as software. A collar, lapel, or near-mouth mount improves the wearer's level relative to the room, while an exposed omnidirectional board on the wrist will often capture everybody equally. If the seven-week tests cannot reach an acceptable false-acceptance rate, the honest next hardware revision is a second microphone or contact/throat microphone; the software must not invent certainty.

## Acoustic features

No paid feature API is required. The server calculates features locally, which keeps the pipeline reproducible and avoids sending identifiable audio to another provider.

[openSMILE](https://audeering.github.io/opensmile-python/) supplies the standardized **eGeMAPSv02 88-functionals** set for research use. Its license must be checked again before any commercial use. NumPy/librosa can provide audit calculations and plots, while optional speech-to-text is postponed until acoustic processing is reliable.

| Feature family | Initial measurements | Why it is included |
| --- | --- | --- |
| Pitch/prosody | F0 median, IQR, standard deviation, range, slope | Captures relative prosodic change while avoiding a single unstable pitch value. |
| Level | RMS, peak, clipping rate, dBFS | Detects signal strength and bad capture; dBFS is relative to the digital scale. |
| Perceptual voice | openSMILE loudness, jitter, shimmer, HNR | Provides standardized voice-quality descriptors used in affective speech research. |
| Spectrum | MFCCs, spectral slope, centroid/roll-off, flux, ZCR | Describes timbre and change, but quality masks are required because noise also changes them. |
| Timing | voiced fraction, speech/pause ratio, pause count and duration | Works directly from VAD and remains interpretable. |

Absolute sound pressure level in dB SPL cannot be recovered from microphone samples without an acoustic calibrator, fixed gain, and controlled geometry. PSYCON will report dBFS, perceptual loudness, and deviation from the enrolled user's own baseline unless Saksham performs a documented SPL calibration.

Features are extracted only from wearer-accepted segments and aggregated in 30-second rolling windows containing at least five seconds of accepted voiced speech. Windows below that threshold return `insufficient_audio`, allowing the late-fusion model to fall back to the wrist rather than fabricate an audio score.

## Wrist processing and multimodal experiment

The wrist pipeline will use PPG-derived heart rate/variability measures, EDA tonic/phasic measures, and accelerometer magnitude/motion flags. Movement is a required confounder signal because exercise can produce the same direction of heart-rate and electrodermal changes as stress.

The two papers shared in the conversation guide the method rather than supply code to copy:

- The [Stress-Predict pilot study](https://pmc.ncbi.nlm.nih.gov/articles/PMC9654418/) used 64 Hz PPG, controlled tasks, task-boundary labels, accelerometry, and personalized adaptive reference ranges. It supports personalization and careful labeling, while its reported individual variability warns against universal raw thresholds.
- The [2024 Frontiers systematic review](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2024.1478851/full) summarizes the standard collect-preprocess-feature-model pipeline across wearable stress studies and the tradeoff between controlled and free-living evaluation. It is a review, not a complete PSYCON implementation.

Audio and wrist clocks are aligned using session IDs, NTP-corrected device time, monotonically increasing sample indices, and explicit gap masks. The experiment must compare:

- Wrist-only baseline.
- Audio-only baseline on wearer-accepted speech.
- Quality-aware late fusion, which can operate when speech is absent.

The central research claim is supported only if late fusion improves subject-independent metrics over wrist-only and the improvement survives motion, speaker-attribution, and missing-data analysis. Public data such as WESAD supports wrist development, and an appropriately licensed multimodal dataset such as StressID can support early audio experiments; neither replaces validation on the final hardware after ethics approval.

## Power and 24-hour operation

“Always on” creates two separate requirements:

- **24-hour service** may use a reviewed external-power or power-path arrangement while acquisition continues.
- **24-hour untethered runtime** must be proven from measured current and an actual discharge test.

Battery capacity is estimated as:

```text
required_mAh = measured_average_mA * target_hours / usable_fraction
```

Use a conservative usable fraction such as 0.8 until discharge measurements establish a better value. Wi-Fi upload, retries, microSD writes, LEDs, sensors, regulators, and current peaks all have to be active during measurement. A claimed 24-hour runtime based only on a component datasheet is invalid.

The direct questions and acceptance tests for Saksham are in the [power section of the seven-week plan](docs/SEVEN_WEEK_BUILD_PLAN.md#questions-saksham-must-close).

## Repository layout

```text
PSYCON/
  main.py                         # Existing WESAD experiment entrypoint
  ml/src/                         # Loading, preprocessing, features, models
  firmware/wrist/                 # Wrist firmware starter
  firmware/ear/                   # Audio firmware starter
  protocol/                       # Shared TypeScript contracts and tests
  tests/                          # ML and firmware static tests
  results/                        # Existing metrics, charts, model artifacts
  paper/                          # Current LaTeX paper scaffold
  docs/SEVEN_WEEK_BUILD_PLAN.md   # Active execution plan
```

The plan will add `server/`, server tests, packet fixtures, session manifests, and soak-test reports. These folders are described as future work until they actually exist.

## Run the existing software

Install Python dependencies and run the WESAD pipeline:

```powershell
pip install -r requirements.txt
python main.py
```

Run a one-subject smoke test and the Python tests:

```powershell
python main.py --limit-subjects 1
python -m pytest
```

Test the TypeScript protocol:

```powershell
cd protocol
npm install
npm test
npm run typecheck
cd ..
```

Build firmware after installing PlatformIO:

```powershell
pip install platformio
cd firmware\ear
platformio run
cd ..\wrist
platformio run
cd ..\..
```

## Privacy and study gate

Twenty-four-hour audio records identifiable speech from the wearer and bystanders. Before recording participants, the project needs the applicable school/IRB decision, informed consent and minor assent/parental permission where required, a visible recording indicator, a physical mute control, encryption in transit, access control, pseudonymous identifiers, a raw-audio retention/deletion policy, and a procedure for bystander speech and deletion requests.

Bench tests, generated speech, public recordings, and voluntary developer recordings can be used to build transport and processing, but stress-induction studies and long personal recordings must follow the approved protocol. Charging a worn device connected to GSR electrodes must also wait for an electrically reviewed power design.

## Team

| Member | Primary ownership |
| --- | --- |
| Arjun Vijay Prakash | Server, protocols, acoustic pipeline, synchronization, ML, evaluation, and reproducibility |
| Saksham Yadav | Electronics, firmware integration, microphone placement, wrist signal quality, battery/power path, enclosure, and physical reliability |

Both owners share weekly integration gates. A subsystem is complete only when the other owner can reproduce its acceptance test from a recorded fixture or the real device.
