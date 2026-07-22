# PSYCON Seven-Week Build Plan

**Owners:** Arjun Vijay Prakash — software; Saksham Yadav — software, hardware and device firmware

**Build target:** A continuously logging wrist module and a continuously capturing audio module whose server can isolate likely wearer speech, calculate acoustic features, align both modalities, and compare wrist-only, audio-only, and late-fusion acute-stress models.

**Starting point:** Components have been purchased and checked individually. The repository has a working WESAD-first software pipeline, protocol skeleton, firmware starters, tests, result artifacts, and paper scaffolding. The integrated device and audio server still have to be built.

## The decision that controls this plan

The project's novelty is the measured relationship between **wearer-attributed voice acoustics and wrist physiology during acute stress**. The long PRD's depression, anxiety-disorder, PTSD, ADHD, autism, cognitive-decline, and emotion-diagnosis ideas are deferred. Seven weeks is enough to build and evaluate one research system; it is not enough to validate a catalogue of medical claims.

The primary architecture is direct audio upload from the ESP32 over Wi-Fi. The phone app, BLE audio gateway, NLP, and cloud speech APIs are not on the critical path.

## Definition of done

At the end of Week 7, a clean checkout and documented hardware build must demonstrate:

1. Continuous 16 kHz mono I2S capture without deliberate 250 ms gaps or silent DMA overruns.
2. Numbered PCM16 chunks sent over authenticated persistent HTTPS, buffered during a measured outage, and acknowledged only after durable server storage.
3. Continuous PPG, GSR, and accelerometer acquisition with real sample rates, units, contact/quality flags, sequence accounting, and local logging.
4. A server pipeline that validates audio, detects speech, separates speakers, verifies the enrolled wearer, rejects uncertainty, and calculates reproducible acoustic features.
5. A shared timeline for wrist and audio windows with measurable drift, loss, late arrival, and missing-modality masks.
6. Wrist-only, audio-only, and quality-aware late-fusion results with subject-independent evaluation and an `insufficient_signal` outcome.
7. A 24-hour powered engineering soak, plus a measured untethered discharge test that reports the actual runtime even if it is below 24 hours.
8. Reproducible code, packet fixtures, saved-session replay, a power budget, failure reports, and claims limited to what the measurements support.

## Frozen system design

### Device-to-server path

```text
INMP441 -> I2S DMA -> PCM16 chunker -> RAM queue -> microSD retry queue
                                               -> Wi-Fi -> HTTPS ingest
                                                            |
                                                            v
                                       durable bytes + metadata -> ACK
                                                            |
                                                            v
                                          asynchronous acoustic worker
```

- Capture and upload run in separate FreeRTOS tasks. A slow request may fill a queue, but it must never pause I2S reads.
- Start with one-second chunks. At 16 kHz/16-bit/mono, each payload is 32,000 bytes and raw traffic is about 2.76 GB/day before overhead.
- Send a fixed-size, versioned, little-endian binary header followed by PCM bytes as `application/octet-stream`, not JSON/base64. HTTPS headers carry authentication and the idempotency key.
- Keep one authenticated HTTPS connection alive and reconnect with bounded exponential backoff.
- Use microSD for unacknowledged audio if outages longer than a few seconds must be survived. ESP32 RAM is only a short shock absorber; internal flash is not a continuous queue.
- Delete a local chunk only after an idempotent server acknowledgement.
- Start with continuous PCM in engineering mode. Add speech-active upload only after the full-stream reference proves that the gate preserves the required features.

### Audio chunk contract

Freeze these fields by the end of Week 1:

| Field | Purpose |
| --- | --- |
| `protocol_version` | Allows future decoders to reject incompatible packets. |
| `device_id`, `session_id`, `boot_id` | Identifies the device, recording, and reboot epoch. |
| `sequence` | Detects missing, duplicate, and reordered chunks. |
| `first_sample_index` | Reconstructs time even if the wall clock jumps. |
| `captured_at_unix_us` | Aligns the device to the server and wrist timeline. |
| `sample_rate`, `channels`, `sample_format` | Makes decoding explicit rather than guessed. |
| `sample_count`, `payload_bytes`, `checksum` | Detects truncation and corruption. |
| `battery_mv`, `queue_depth` | Connects transport failures with power and backlog. |
| `clip_count`, `dma_overrun_count` | Prevents damaged recordings from looking valid. |

The server uses `(device_id, session_id, boot_id, sequence)` as the idempotency key. It returns `accepted`, `already_present`, or a retryable/non-retryable error; an HTTP response by itself is not proof that the bytes are durable.

### Server pipeline

Keep the first server deployable by two people:

- FastAPI ingest and session endpoints.
- PostgreSQL for devices, sessions, chunk metadata, feature windows, quality flags, results, and deletion records.
- A controlled filesystem volume for transient raw chunks. Ingest writes a temporary file, flushes it, atomically renames it, commits metadata, and then acknowledges; startup reconciliation resolves a crash between the file and database steps.
- A separate Python worker that polls pending chunks or jobs; add Redis only if measurements show the database queue is insufficient.
- Structured logs and a small status page for last sequence, backlog, battery, gaps, and processing delay.

The worker stages are:

```text
decode -> quality checks -> VAD -> diarization -> wearer verification
       -> wearer-only rolling windows -> openSMILE/eGeMAPS + audit features
       -> wrist alignment -> modality outputs -> late fusion -> retention/deletion
```

### Wearer attribution

The INMP441 is a single omnidirectional microphone, so speaker attribution has three independent jobs:

- Silero VAD or an equivalent local VAD decides whether speech exists.
- pyannote.audio separates speaker turns; its labels identify different speakers, not the wearer's identity.
- A SpeechBrain ECAPA-TDNN speaker embedding compares each turn with a wearer enrollment template.

Enrollment uses three or more 30-second samples recorded with the final microphone placement in quiet, ordinary, and moderately noisy conditions. The accepted threshold is tuned on held-out wearer speech and at least three other voices. Overlap, television, music, short turns, and uncertain similarity return `unknown`, and unknown audio is excluded from stress inference.

Required attribution metrics are VAD precision/recall, diarization error rate, wearer false-acceptance rate, wearer false-rejection rate, overlap rejection, and the fraction of session time with accepted wearer speech. Accuracy on a few clean voice clips is not enough.

### Acoustic features

Use local libraries rather than an external feature API:

- openSMILE `eGeMAPSv02` 88 functionals as the standardized primary vector.
- F0 median/IQR/range/slope; RMS, peak and dBFS; perceptual loudness; jitter, shimmer and HNR; MFCC and spectral summaries; VAD-derived speech/pause measurements.
- Thirty-second rolling windows with at least five seconds of accepted wearer speech. Anything below the threshold is `insufficient_audio`.
- Relative dBFS and loudness are valid. Absolute dB SPL is not claimed without acoustic calibration and fixed geometry.
- Transcript content, sentiment, word choice, and speaking rate from ASR are deferred until the acoustic pipeline passes the 24-hour test.

### Fusion

Use late fusion first because speech is intermittent. Each modality emits a probability or score plus a quality value; the fusion layer weights valid modalities and falls back to the wrist when audio is missing. Train and report wrist-only, audio-only, and late-fusion variants from the same splits and windows.

The main experiment answers one question: **Does accepted wearer speech improve subject-independent acute-stress estimation beyond the wrist-only system?** If the answer is no, the system is still a useful result because the attribution, missingness, and ablation evidence explain why.

## Questions Saksham must close

These are design inputs, not optional documentation. Record the answer, measurement method, photograph/schematic, and consequence for every item.

### Power and 24/7 operation — close in Week 1

1. What is the exact LiPo manufacturer, part number, nominal capacity, maximum discharge current, protection circuit, connector polarity, and physical condition for each module?
2. What exact TP4056 board was purchased, what is its charge-program resistor/current, and does its schematic contain a true load-sharing/power-path circuit? A charger with `OUT+/-` labels is not automatically a power path.
3. Can the board run while charging without mis-terminating charge, overheating, or routing uncontrolled current through the cell? If this is unknown, will the build add a power-path charger such as a BQ24074-class board or define charging downtime?
4. What voltage reaches the ESP32 across the full LiPo discharge curve? Is the present connection within the development board's input requirements, or is a buck/boost or regulated rail required?
5. What are average and peak currents for audio capture only, capture plus continuous Wi-Fi upload, reconnect/backlog upload, microSD write, and worst-case retry? Measure at the battery, not from software estimates.
6. What are average and peak currents for wrist acquisition, local logging, and radio activity with every sensor at its final sample rate?
7. What battery capacity follows from `average_mA * 24 / usable_fraction`, and does the physical battery actually deliver it in a discharge test?
8. What is the brownout threshold, low-battery warning, queue-flush procedure, and controlled shutdown behavior?
9. What temperatures occur at the ESP32, charger, regulator, and battery during charging, Wi-Fi backlog upload, and a 24-hour powered run?
10. Can a microSD module be added to the audio build, and what capacity, filesystem, wiring, peak current, and corruption-recovery behavior will it use?
11. Will any device be charged while worn or connected to GSR electrodes? The answer should remain no until the power path and isolation are reviewed.

### Microphone and enclosure — close by Week 3

1. Where is the microphone mounted relative to the mouth, and what level difference is measured between the wearer and another person one metre away?
2. Does the enclosure block the acoustic port or add resonance, wind, cable, or fabric-contact noise?
3. Is there a visible recording indicator and a physical microphone disable control?
4. Do walking, head movement, Wi-Fi transmission, charging, or microSD writes contaminate the recordings?
5. Is the `L/R` channel, I2S bit alignment, gain, clipping margin, and DC removal verified with a known recording rather than assumed?
6. Can continuous I2S run while the network stalls, and are DMA overruns counted and exposed?

### Wrist acquisition — close by Week 3

1. What exact PPG, accelerometer/gyroscope, and GSR sampling rates are used, and why are they sufficient for the chosen features?
2. Are raw PPG samples preserved, and how are FIFO overflow, contact loss, saturation, ambient light, and motion artifact reported?
3. What ADS1115 gain and rate are used, what is the GSR circuit's safe excitation, and how are codes converted to documented units?
4. What electrode material, spacing, attachment pressure, and replacement procedure produce repeatable contact?
5. Are batches timestamped at acquisition rather than transmission, and can every missing sample be counted?
6. Does sensor logging continue through audio silence, Wi-Fi outage, server failure, and module reboot?

## Questions Arjun must close

### Server and protocol — close by Week 2

- Where will the development and demonstration server run, who owns its credentials, and what happens if that network has no internet route?
- How are device secrets provisioned and rotated without committing them to Git?
- What exactly makes an acknowledgement durable, and how are duplicate, corrupt, late, and out-of-order chunks represented?
- How long can the server be offline before the device queue fills, and what deterministic policy applies when it does?
- How are NTP correction, sample-index time, wall-clock jumps, reboot epochs, and long-run drift recorded?
- What raw-audio retention period applies to engineering tests and approved research sessions, and how is deletion verified?

### Research — close by Week 4

- Which final wrist features can the purchased sensors reproduce without WESAD temperature data?
- What public audio or multimodal dataset is licensed for the intended experiments, and what domain mismatch remains against the INMP441 placement?
- What constitutes ground truth, and how will labels be collected without leaking task boundaries into the model?
- What subject-independent split, metrics, confidence intervals, and quality-abstention analysis will be reported?
- What result would falsify the claim that audio contributes useful information beyond the wrist?

## Week 1 — Make continuous audio real

**Goal:** Prove the microphone, bit format, server boundary, and power assumptions before adding models.

### Arjun

1. Add a `server/` FastAPI skeleton with a simulated-device upload endpoint, binary-body validation, file spool, metadata schema, and structured log.
2. Define protocol v2 and make one golden chunk fixture decodable in Python, TypeScript, and C++.
3. Build a simulator that sends numbered one-second PCM chunks, duplicates one, skips one, corrupts one, and retries after a disconnect.
4. Add a session manifest containing code versions, device/boot IDs, expected sample counts, actual chunks, gaps, and checksums.
5. Freeze the research scope and update project issues so diagnosis, NLP, mobile UI, and extra sensors cannot enter the sprint.

### Saksham

1. Replace the firmware's short read and 250 ms delay with continuous I2S DMA capture and double/triple buffering.
2. Save or stream a five-minute known speech recording and verify channel, sign, bit shift, sample rate, clipping, playback speed, and absence of periodic gaps.
3. Measure capture-only and capture-plus-Wi-Fi current at the battery, including peaks and board temperature.
4. Identify every battery, charger, regulator, and board variant and answer the Week 1 power questions.
5. Decide whether a microSD breakout and a true power-path charger must be purchased immediately.

### Exit gate

- Thirty minutes of continuous device audio reaches the ingest service with no unexplained sample gaps.
- The server detects the intentionally missing, duplicate, and corrupt chunks.
- A recorded file plays correctly and its exact sample count matches elapsed capture time within the measured clock error.
- The first power table and 24-hour capacity estimate use measured current.
- Any required microSD or power-path part is ordered now; waiting until Week 6 is a plan failure.

## Week 2 — Make Wi-Fi failure recoverable

**Goal:** Separate capture from transport and prove the acknowledgement/retry contract.

### Arjun

1. Implement authenticated persistent HTTPS upload, idempotent database insertion, durable file writes, and explicit acknowledgements.
2. Add metadata tables for device, session, chunk, retry, processing state, and deletion state.
3. Implement clock-sync records and timeline reconstruction from `first_sample_index`.
4. Add automated integration tests for timeout before/after durable write, duplicate retry, reconnect, reboot with a new `boot_id`, bad checksum, and queue-full policy.
5. Build a minimal status endpoint/page for last sequence, missing ranges, backlog, battery, and ingest delay.

### Saksham

1. Run capture, chunking, upload, and storage as independent tasks with bounded queues and observable high-water marks.
2. Implement microSD write/replay if the part is present; otherwise quantify the exact RAM-only outage limit and resulting limitation.
3. Add NTP startup/periodic sync, monotonic sample indexing, reconnect backoff, watchdog reason, and persistent error counters.
4. Test a forced ten-minute Wi-Fi outage, access-point restart, server timeout, and DNS failure while capture continues.
5. Begin real wrist drivers with explicit configurations; no placeholder values may cross the protocol boundary.

### Exit gate

- A two-hour audio run includes a ten-minute outage and automatically drains its backlog without duplicate processing.
- I2S sample accounting continues throughout the outage and DMA overrun count remains zero, or the failure is explained and fixed before Week 3.
- The server can restart between write and acknowledgement without losing or double-processing the chunk.
- Wrist firmware emits real, versioned sensor batches or a documented blocker with a dated fix.

## Week 3 — Build the acoustic feature worker

**Goal:** Turn stored PCM into reproducible quality decisions and acoustic vectors.

### Arjun

1. Implement decode and golden-waveform tests for duration, amplitude, clipping, RMS, dBFS, and known fundamental frequency.
2. Add signal-quality rules and Silero VAD with stored speech intervals and confidence.
3. Add openSMILE `eGeMAPSv02` extraction plus transparent audit features for pitch, level, spectrum, and timing.
4. Assemble 30-second rolling windows across chunk boundaries and require five seconds of voiced audio.
5. Store the extractor version, parameters, source chunk range, quality decision, and vector checksum so replay is deterministic.

### Saksham

1. Freeze microphone placement after tests for distance, fabric, wind, walking, Wi-Fi, enclosure, and another nearby speaker.
2. Finish real PPG, GSR, and motion acquisition with timestamps, batching, quality flags, and local logging.
3. Measure the integrated audio build's current with microSD and final Wi-Fi behavior.
4. Produce calibration recordings with quiet speech, background noise, TV/music, clipping, very low level, walking, and fabric rub.

### Exit gate

- Known tones and fixture recordings produce expected duration, frequency, level, and deterministic features.
- A four-hour session processes asynchronously while ingest continues, with reported backlog and latency.
- Silence, clipping, very noisy audio, and insufficient speech abstain rather than create a usable feature window.
- Wrist logs contain continuous real samples with detectable contact and loss states.

## Week 4 — Identify the wearer

**Goal:** Stop surrounding speech from entering the wearer model.

### Arjun

1. Add pyannote diarization over sensible multi-chunk segments and map turns back to exact sample ranges.
2. Add the SpeechBrain ECAPA enrollment and verification service with versioned templates and cosine scores.
3. Implement the decision policy: accepted wearer, other speaker, overlap, or unknown; only accepted wearer ranges reach the feature aggregator.
4. Build an evaluation notebook/script reporting VAD metrics, diarization error, false acceptance/rejection, coverage, and errors by condition.
5. Add tests proving unknown and other-speaker segments cannot leak into an accepted feature window.

### Saksham

1. Record consented engineering fixtures using the final placement: wearer plus at least three other speakers, speaker turns, overlap, television, music, several distances, walking, and fabric noise.
2. Record at least three enrollment sessions on different takes rather than copying one clip.
3. Compare at least two feasible placements and document the wearer-to-background level difference and usability.
4. Add and verify the microphone-active indicator and physical mute behavior.

### Exit gate

- The evaluation set has no train/test clip overlap and includes all listed background conditions.
- A threshold is selected from measured false-acceptance/false-rejection tradeoffs, not intuition.
- Overlap and uncertain turns are rejected.
- If false acceptance remains unacceptable, narrow the claim and record the required microphone revision instead of weakening the threshold to increase coverage.

## Week 5 — Align wrist and audio, then test the claim

**Goal:** Produce the first valid modality ablation on one synchronized timeline.

### Arjun

1. Convert wrist logs into hardware-compatible feature windows and remove dependencies on sensors the device does not have.
2. Align wrist and acoustic windows using session, boot, timestamp, sample index, and gap masks; quantify residual drift.
3. Train/evaluate wrist-only, audio-only, and quality-aware late-fusion baselines using identical subject/session splits.
4. Separate cold-start from per-user-baseline evaluation and prevent calibration samples from appearing in test windows.
5. Generate one report with balanced accuracy, macro-F1, false-positive rate, calibration, per-subject results, missingness, accepted-audio coverage, and modality ablation.

### Saksham

1. Assemble the stable wearable form with fixed wiring, placement, strain relief, controls, indicators, and battery mounting.
2. Run scripted calm, speech, movement, and non-wear engineering sessions that expose motion and contact confounders without making clinical claims.
3. Measure whether Wi-Fi, microSD, enclosure, or audio placement changes PPG/GSR quality.
4. Update the final BOM and wiring diagram to match the tested physical build.

### Exit gate

- An eight-hour integrated session replays to identical window features and results.
- Missing audio falls back to the wrist; missing or bad wrist data produces a documented result rather than silent imputation.
- The report shows all three modality variants and does not claim improvement unless the comparison supports it.
- The integrated power measurement is sufficient to plan Week 6's powered and untethered tests.

## Week 6 — Prove 24-hour service and measure battery truth

**Goal:** Find the failures that only appear after hours of continuous operation.

### Test A: 24-hour powered engineering soak

Use the reviewed power arrangement, continuous PCM engineering mode, all wrist sensors, server processing, and complete instrumentation. Inject one ten-minute Wi-Fi outage, one server restart, one access-point restart, and one device reconnect. Do not inject failures while nobody is observing battery or thermal behavior.

Record expected/received samples, sequence gaps, retries, duplicate attempts, queue high-water marks, filesystem use, database growth, upload bandwidth, processing latency, clock drift, memory, resets, battery/rail voltage, current, and temperature.

### Test B: untethered discharge

Run the final batteries from full charge to controlled shutdown under the chosen operating mode. Record the discharge curve and actual runtime. If it is below 24 hours, calculate the required capacity or duty-cycle change and report that result; do not rename a powered test as battery life.

### Arjun

1. Automate a soak summary from manifests, device status, database records, and server logs.
2. Implement and verify raw-audio retention/deletion jobs.
3. Compare continuous PCM with candidate speech-active upload; evaluate power, bytes, wearer-feature coverage, and feature differences.
4. Profile storage and compute per device-day and set practical queue/disk alerts.

### Saksham

1. Own current, voltage, temperature, charging/power-path, battery condition, and physical inspections during both tests.
2. Verify low-battery flush/shutdown, restart, microSD recovery, and safe transition to/from the reviewed external supply.
3. Inspect sensor contact, connectors, enclosure, acoustic port, and battery for changes after the test.
4. Produce the final measured power budget and the concrete hardware revision if 24-hour untethered use fails.

### Exit gate

- The powered system completes 24 hours with quantified availability and data completeness.
- Every injected failure is visible and recovery is explained by logs, not memory.
- Actual untethered runtime, average/peak current, storage/day, bandwidth/day, drift, and temperatures are reported.
- No uncontrolled charging, overheating, silent queue loss, or unrecoverable storage corruption remains.

## Week 7 — Freeze, reproduce, and present

**Goal:** Turn the tested build into evidence. New features are forbidden this week.

### Arjun

1. Fix only Week 6 failures and freeze protocol, server, extractor, model, dataset, and configuration versions.
2. Add a clean setup path plus commands for server startup, simulated upload, saved-session replay, WESAD experiments, evaluation, and soak-summary generation.
3. Update the paper and README with measured results, failure cases, privacy limits, and an architecture that matches the code.
4. Export the final ablation tables, attribution metrics, power/reliability tables, and plots from scripts rather than editing numbers manually.

### Saksham

1. Freeze the BOM, wiring, power path, battery, enclosure, sample rates, firmware configuration, placement, and controls.
2. Produce labeled photographs, final schematics, calibration notes, power measurements, runtime plots, and recovery instructions.
3. Prepare a tested spare power source/cable and a physical demo checklist without silently swapping hardware from the documented build.

### Joint exit gate

- A third person can start the server, power the devices, create a session, observe capture/upload/processing, interrupt Wi-Fi, see recovery, stop the session, and replay it from the documentation.
- The release includes exact versions, raw-to-result lineage, attribution metrics, modality ablations, and the 24-hour report.
- The presentation clearly separates measured results, current limitations, and future ideas.

## Weekly operating rule

Only two tracks stay active: Arjun's server/data/ML track and Saksham's device/power track. Interfaces freeze on Monday, each owner builds against fixtures through Thursday, integration happens Friday, failures are measured Saturday, and Sunday is for blockers and the next gate. A failed gate moves unfinished work forward and removes optional work; it does not cause seven new parallel tasks.

Every daily update answers four questions:

1. What became demonstrably true today?
2. What artifact or measurement proves it?
3. What failed or remains blocked, and who owns the next action?
4. Did an interface, part, assumption, or claim change?

## Stop conditions and fallbacks

- If direct Wi-Fi cannot sustain capture within the power budget by the Week 2 gate, retain the packet/server contract and test a phone or dedicated gateway. Do not redesign both paths in parallel.
- If microSD cannot be integrated reliably, reduce the promised outage tolerance to the measured RAM capacity and keep the loss visible.
- If wearer false acceptance remains high, return uncertain speech as unknown and narrow the audio claim; never trade privacy and validity for more accepted minutes.
- If audio does not improve the wrist-only model, report the negative ablation result and the conditions under which it failed.
- If the battery does not last 24 hours, report actual untethered runtime while retaining the separately proven 24-hour powered-service result.
- If ethics approval is not available, finish transport, public-data modeling, fixture evaluation, and developer engineering soaks; do not run a human stress study.

## References used for the design

- [Stress-Predict wearable pilot study](https://pmc.ncbi.nlm.nih.gov/articles/PMC9654418/)
- [Frontiers systematic review of wearable stress detection](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2024.1478851/full)
- [Espressif HTTP client documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/protocols/esp_http_client.html)
- [Espressif I2S documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html)
- [openSMILE Python documentation](https://audeering.github.io/opensmile-python/)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [pyannote.audio](https://github.com/pyannote/pyannote-audio)
- [SpeechBrain ECAPA speaker verification model](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- [ESP32-WROOM-32E datasheet](https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.html)
- [INMP441 datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf)
- [BQ24074 power-path charger documentation](https://www.ti.com/product/BQ24074)
