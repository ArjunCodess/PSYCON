# PSYCON Seven-Week Build Plan

**Assessment date:** 7 September 2026

**Owners:** Arjun Vijay Prakash, software and research; Saksham Yadav, hardware and device firmware

**Current completion:** approximately 55% overall; approximately 32% of end-to-end functional acceptance demonstrated

This plan implements the 34-chapter engineering design in `docs/engineering_prd/`. It covers the complete Wrist Module, Audio Module, shared protocol, backend, multimodal study, electrical validation, safety, documentation, and competition demonstration.

## Status and evidence rules

- **Verified:** A repeatable test, measurement, log, dataset, or generated artifact proves the claim.
- **Implemented:** Code or hardware exists and passes a local check, but physical/end-to-end validation remains.
- **Designed:** The paper specifies it, but it has not been built.
- **Blocked:** A named part, approval, input, or failure prevents progress.

Documentation proves documentation only. A diagram of a driver, backend, calibration, or power path does not prove its implementation.

## Current baseline

| Area | State | Evidence |
| --- | --- | --- |
| Engineering PRD | Tracked and reproducible | 34 TeX chapters, a current 37-page PDF, reproducibility matrix, device-feature contract, and audio contract; placeholder bibliography entries remain release blockers |
| Hardware | Partial reported bring-up | BOM, GPIO, wiring, and power design; no integrated or measured evidence in repository |
| Wrist firmware | Scaffold | Compiles and scans I2C; sensor samples are placeholders |
| Audio firmware | Scaffold | Compiles and initializes 16 kHz I2S; capture is discontinuous and TEMT6000 is absent |
| Protocol | Versioned transport and server ingestion implemented | Protocol v2 fixtures decode identically in Python, TypeScript, and C++; authenticated Flask ingestion preserves immutable packet identity and synchronization metadata |
| Backend | Week 4 software complete | PostgreSQL, S3-compatible storage, authentication, validation, synchronization, jobs, dashboard, export, backup verification, containers, and deterministic device simulation pass the live Compose smoke test |
| ML | Week 5 research pipeline prepared | WESAD models/artifacts, audio and language analysis, synchronized multimodal assembly, participant-safe splits, candidate selection, group cross-validation, confidence intervals, ablations, and context/duration analysis code exist; psychologist marksheets, matching PSYCON sessions, real multimodal results, and external validation remain absent |
| Validation | Software checks only for Week 5 | Repository checks, deterministic model unit tests, audio and upload-page tests, and local-model transcription pass; no synthetic Week 5 dataset or generated metric is retained as study evidence |

## PRD-resolved implementation decisions

The Engineering PRD is the sole design authority for the remaining build. These are settled inputs, not open questions:

1. The system uses two 30-pin ESP32 DevKit boards with ESP32-WROOM-32 controllers. The Wrist Module uses MAX30102, MPU6050, MCP9808, ADS1115, and GSR electrodes; the Audio Module uses INMP441 and TEMT6000.
2. Wrist I²C uses `GPIO21` SDA and `GPIO22` SCL with MCP9808 at `0x18`, ADS1115 at `0x48`, MAX30102 at `0x57`, and MPU6050 at `0x68`. The GSR front end enters ADS1115 A0.
3. Audio wiring is INMP441 BCLK `GPIO26`, WS/LRCLK `GPIO25`, DATA `GPIO33`, and L/R tied to ground for the left channel. TEMT6000 SIG uses `GPIO32` ADC. Sensors use 3.3 V logic and a common ground.
4. Power uses two TP4056 USB-C HW-373 V1.2.1 charger/protection modules and three HLCY 651735P 500 mAh LiPo cells. The Wrist Module uses two cells in parallel; the Audio Module uses one. The PRD notes that TP4056 has no true load sharing and does not recommend wearable operation while charging; charging is disconnected before GSR electrodes contact a participant. The recommended light-load cutoff is approximately 3.2–3.3 V.
5. The PRD targets continuous monitoring through continuous heart, motion, GSR, and audio acquisition plus periodic temperature and light tasks; speech may be continuous or scheduled. Chapter 6 deliberately leaves exact frequencies to empirical testing, so selected values are recorded as configuration and calibration evidence rather than treated as a new architecture decision.
6. Firmware uses non-blocking tasks, timestamps, sequence numbers, checksums, fixed-size or circular buffers, retry-and-log error handling, battery warning and graceful shutdown, watchdog recovery, and continued operation when another sensor or module fails.
7. Engineering capture may transport PCM samples as described in Chapter 6. The deployed Audio-to-Backend record described in Chapter 25 contains header, timestamp, audio features, ambient light, battery voltage, microphone status, and checksum. Both modes retain timestamps and checksums.
8. The backend sequence is API gateway, authentication, packet validation, time synchronization, database, feature extraction, AI inference, visualization dashboard, and research export. Synchronization uses backend time, a common epoch, and continuous offset correction.
9. Stored research material includes raw sensor files, processed features, metadata, model outputs, and logs. Firmware, hardware, PCB, dataset, model, and documentation versions are tracked.
10. The minimum runtime target is six hours; 24 hours is a stretch goal. Outputs remain research indicators and must never be presented as clinical diagnoses.

### PRD-required evidence still to record

These are measurements required by Chapters 4, 5, 8, 13, 14, and 28, not unanswered design questions:

- Verify the assembled ESP32 power-input path, regulator, stable 3.3 V rail under wireless load, TP4056 charge current, peak current, brownout behavior, charging temperature, and discharge runtime.
- Finalize sample rates and sensor ranges through testing, then record them with firmware version, date, operator, environmental conditions, method, and results.
- Validate the GSR analog front end, safe excitation, protection, contact behavior, calibration, and the rule prohibiting charging while electrodes are attached.
- Save I²C detection, real sensor samples, clean INMP441 recordings, TEMT6000 dark/bright response, DMA stability, packet integrity, reconnect, watchdog, and graceful-shutdown results.
- Record final assembly, insulation, connector, enclosure, strain-relief, wearability, microphone-port, and safety inspection evidence.

### Questions for Saksham

- Can the project-controlled server access the gated `pyannote/speaker-diarization-community-1` model, and who will provision its `HF_TOKEN` without committing the token?
- Which consented multilingual, multi-speaker recordings may be used to calibrate wearer-match thresholds, ambiguity margins, diarization error, and false-match/false-rejection rates?
- What are the measured INMP441 noise floor, clipping limit, clock accuracy, microphone placement, and channel/sign/shift settings on the assembled Audio Module?
- Can Saksham capture the ADC/I2S path recording a known laboratory tone so sampling-clock sidebands can be measured separately from human vocal jitter?
- Does the intended server GPU have enough memory and throughput to run local Whisper, pyannote diarization, and ECAPA speaker embeddings for the expected recording length and concurrency?

## Definition of done

1. All six sensors initialize and produce real values with documented rates, units, configurations, quality, and errors.
2. Each module continues when the other module or backend fails.
3. Acquisition is continuous and exposes every sequence gap, corruption, reboot, contact loss, saturation, and overrun.
4. C++, TypeScript, and Python decode identical versioned wire fixtures.
5. Authentication, validation, synchronization, durable storage, features, inference, visualization, and research export work end to end.
6. Stress and runtime tests record synchronized timestamps, temperature, memory use, packet loss, unexpected resets, battery voltage, runtime, charging time, and communication status.
7. Physiology-only, speech-only, and combined models use identical subject-independent splits and honest missing-signal behavior.
8. Rail, current, battery, charging, brownout, thermal, insulation, GSR excitation, strain relief, and shutdown tests pass.
9. Both modules meet the paper's six-hour minimum; 24 hours is claimed only if an actual stretch test passes.
10. A third person can build, run, interrupt, recover, replay, and regenerate results from the release.
11. Live and recorded demonstrations show startup through safe shutdown.
12. All claims remain research indicators, never clinical diagnoses, and human recording follows approval and consent.

## Frozen architecture

```text
Wrist sensors -> Wrist ESP32 ----+
                                 +-> versioned packets -> authentication
Audio + light -> Audio ESP32 ----+                      -> validation/sync
                                                        -> durable sessions
                                                        -> features/inference
                                                        -> visualization/export
```

The Week 1 transport decision is frozen: consented engineering mode uses protocol-v2 raw PCM so capture and feature correctness can be audited; a later research mode may transmit derived features only after equivalence tests pass. The normalized software contract carries session, battery, status, quality, and error context alongside the binary audio/wrist chunks.

## Week 1: Reproducible and electrically safe baseline

**Goal:** Reconcile the paper, code, compiled artifacts, hardware variants, and test environment.

**Software status: complete.** Clean-checkout tests, dependency audit, three-language protocol fixtures, documentation reconciliation, and the PRD build pass. The remaining Week 1 exit items are listed under “PRD-required evidence still to record.”

### Arjun

1. Create a clean-checkout matrix for Python, TypeScript, both firmware projects, and the paper.
2. Resolve or explicitly fixture/mark the three raw-WESAD-dependent Python tests.
3. Upgrade vulnerable protocol test dependencies and regenerate the lockfile.
4. Freeze protocol v2 and add valid wrist, valid audio, and invalid-checksum fixtures decoded by Python, TypeScript, and C++.
5. Resolve the legacy `paper/` scaffold, rebuild the Engineering PRD PDF, and track bibliography TODOs as release blockers.
6. Freeze the research endpoint as physiology/speech/combined estimation of non-clinical experimental indicators.

### Saksham

1. Record manufacturer, revision, photograph, polarity, supply, address selection, and condition for every component.
2. Draw the as-built power paths, including batteries, TP4056 boards, regulators, ESP32 inputs, sensors, connectors, and ground.
3. Measure boot/idle rails, current peaks, charger current, and temperature.
4. Verify the exact charger/load behavior and define a safe external-test supply; prohibit unreviewed charge-while-operating.
5. Verify GSR excitation and insulation before worn testing.
6. Save physical I2C and I2S bring-up logs.

### Exit gate

- Firmware builds, protocol tests/type-check, and repository-safe Python tests pass from documented commands.
- Cross-language fixtures prove the wire contract.
- Exact hardware, power paths, photographs, and initial measurements are recorded.
- Paper/PDF/reference inconsistencies are fixed or release-blocked.
- No human-worn or long audio study begins before power and ethics approval.

## Week 2: Complete the Wrist Module

**Goal:** Replace all placeholder values with real, timestamped, quality-aware acquisition.

**Software status: complete.** Python and TypeScript schemas cover session, batch, quality, error, battery, and calibration data; fixtures/tests cover gaps and quality failures; the device-to-feature converter and hardware-compatible feature surface are implemented. Real firmware fields and sensor evidence remain with Saksham.

### Arjun

1. Add session, sensor-batch, quality, error, battery, and calibration types.
2. Add fixtures for real batches, gaps, disconnect, saturation, contact loss, and checksum failure.
3. Build a raw-device-packet to feature converter independent of WESAD dataframes.
4. Freeze a feature set reproducible by the purchased hardware.

### Saksham

1. Integrate MAX30102 raw RED/IR, heart rate, FIFO, contact, saturation, and motion-quality behavior.
2. Integrate MPU6050 acceleration/gyroscope with verified axis, range, rate, and units.
3. Integrate MCP9808 with stable temperature readings.
4. Integrate ADS1115/GSR with gain, rate, safe excitation, units, electrode procedure, contact, and saturation checks.
5. Add scheduled acquisition, buffering, error logging, watchdog, battery measurement, and per-sensor failure isolation.

### Exit gate

- Devices are stable at `0x57`, `0x68`, `0x18`, and `0x48` for one hour.
- Real samples include rates, units, acquisition timestamps, sequence counts, and quality flags.
- Disconnecting one sensor does not stop the others.
- A saved wrist session replays through the device-compatible feature converter.

## Week 3: Complete the Audio Module

**Goal:** Complete the PRD speech-and-environment pipeline from continuous capture through acoustic and language features.

**Software status: implemented and unit-tested; real-audio exit validation open.** The acoustic extractor, word-timestamped multilingual transcription, English language features, local diarization adapter, encrypted three-sample wearer enrollment, conservative participant matching, anonymous speaker metrics, conversation timing, and Praat jitter analysis are implemented behind explicit consent. Deterministic tests do not require gated model downloads. Week 3 becomes verified only after the complete webpage succeeds on consented multi-speaker recordings from the intended microphone and server.

### Arjun

1. Keep the existing deterministic tests for silence, impulses, tones, clipping, speech-like input, noise, corrupt packets, missing audio, and real WAV/MP3/OGG uploads.
2. Complete acoustic features for speaking activity, pause duration, pitch statistics, energy/loudness, voice stability, and spectral characteristics while retaining explicit insufficient, clipped, noisy, corrupt, and missing states.
3. Add local speech-to-text processing for consented recordings, with timestamped transcript segments, transcription confidence, no-speech, failed-transcription, and unsupported-language outcomes.
4. Implement the PRD language features: vocabulary diversity, sentence length, sentiment, emotion-related language, topic transitions, and basic conversation-level summaries. Keep these as research features, not clinical interpretations.
5. Preserve lineage from source recording and Protocol v2 samples to acoustic windows, transcript segments, language features, extractor identity, and quality decisions.
6. Apply the acoustic quality gate before transcription and support a feature-only path when raw speech recording is not consented or retained.
7. Extend the local webpage to display playback, acoustic decisions, timestamped transcription, language features, and clear privacy/consent boundaries.
8. Run local pyannote diarization and align Faster Whisper word timestamps to exclusive speaker turns while retaining regular turns for overlap measurement.
9. Enroll one wearer from three quality-checked 5--10 second clips, retain only an encrypted averaged ECAPA embedding, and provide replacement and deletion controls.
10. Identify at most one participant only above the verification threshold and ambiguity margin; otherwise return `not_enrolled`, `not_identified`, `ambiguous_match`, or `insufficient_speech`, and keep other speakers anonymous.
11. Report per-speaker speaking duration/share, turn statistics, articulation/session rates, within-speaker pauses, response gaps, signed transition latency, overlaps, and interruptions.
12. Calculate Praat local absolute and relative jitter, RAP, PPQ5, and DDP through raw-cross-correlation pitch and waveform-aligned pulses. Label quality-gated conversation results as research estimates, and aggregate clean regions by valid pulse count.
13. Accept an optional 3--8 second steady `/a/` vowel, select a clean central two-second region, and report the controlled jitter result separately with engine provenance and abstention reasons.

### Saksham

1. Implement the PRD audio task chain: initialize I²S, allocate DMA and circular buffers, record continuously or on the scheduled mode, extract/package frames, and transmit without blocking acquisition.
2. Use the fixed PRD wiring: INMP441 left channel on `GPIO26/25/33`, TEMT6000 on `GPIO32`, 3.3 V logic, common ground, and an unobstructed microphone port away from switching power circuitry.
3. Verify clean INMP441 recordings, correct I²S configuration, acceptable noise floor, no clipping, and no excessive DMA overruns; record the empirically selected rate and configuration.
4. Integrate continuous TEMT6000 acquisition and verify smooth dark-to-bright response on the same timestamped session timeline.
5. Produce PRD audio records containing timestamp, PCM or derived audio features as appropriate, ambient light, battery voltage, microphone status, checksum, sequence, and error/log context.
6. Implement buffer-overrun, reconnect, battery-warning, brownout, memory-failure, watchdog-reset, and graceful-shutdown logging.

### Exit gate

- A consented real multi-speaker WAV, MP3, OGG, or live capture passes quality review and produces word-timestamped transcription, acoustic/language features, anonymous diarization, a conservative wearer-match decision, conversation gaps/overlaps/interruptions, speaking rates, and quality-gated conversational jitter estimates in the local webpage.
- A separate consented 3--8 second steady `/a/` vowel produces a controlled Praat measurement, while a missing or inadequate vowel abstains without blocking conversation analysis.
- Enrollment persists only an encrypted averaged embedding; replacement and deletion work, and enrollment audio or raw embeddings never appear in storage, responses, or logs.
- Silence, noise, clipping, missing audio, corrupt packets, no speech, and failed transcription never produce a normal inference input.
- The integrated Audio Module records cleanly for the PRD one-hour stress test with no dropped buffers, while TEMT6000 readings vary smoothly and remain timestamp-aligned.
- Temporary communication loss is buffered and retried; microphone, light, battery, error, sequence, timestamp, and checksum information reach the receiver.

## Week 4: Backend, synchronization, and data management

**Goal:** Implement the complete backend chain and produce synchronized, stored, visualized, and exportable research sessions.

**Software status: complete and Compose-verified; physical exit validation deferred until hardware is available.** The PostgreSQL/S3-compatible Flask service, authenticated Protocol v2 ingestion, clock offset/drift estimation, immutable raw storage, PostgreSQL-backed processing, polling dashboard, deterministic dual-device simulation, research export manifests, backup verification, and cloud-ready containers are implemented. On 13 August 2026 the live Compose integration test passed with healthy API, PostgreSQL, and MinIO services; the worker completed processing, six packets from two simulated devices remained idempotent, inference abstained against an incomplete model contract, and a hashed export was retrieved. Firmware connection, simultaneous real-device timing, outage recovery, and sensor/module independence remain named physical validation gates rather than unfinished server work.

### Arjun

1. Implement the Chapter 27 modules as independently testable components: API gateway, authentication layer, packet validator, time synchronizer, database, feature extraction, AI inference engine, visualization dashboard, and research export.
2. Validate module ID, sensor ID, timestamp, payload, battery, quality/error flags, sequence number, and checksum for Wrist and Audio records.
3. Synchronize both devices from backend time to a common epoch and apply continuous offset correction so wrist, audio, transcript, and light records share one timeline.
4. Store the Chapter 7 and Chapter 18 records: user/anonymous participant ID, session ID, timestamps, raw sensor data, audio metadata, features, predicted class or score, confidence, data-quality indicators, and logs.
5. Use the PRD data structure for participants, sessions/raw, sessions/features, models, results, docs, and firmware; provide secure storage, limited access, encryption in transmission, regular backups, and research export.
6. Track firmware, hardware, PCB, dataset, model, configuration/calibration, and documentation versions with every session and result.
7. Implement dashboard views for sensor status, synchronized signals, audio/transcription quality, extracted features, inference output, confidence, and errors.

### Saksham

1. Transmit timestamped, sequenced, checksum-protected Wrist and Audio records over the PRD BLE/Wi-Fi path without blocking sensor acquisition.
2. Use fixed-size transmission queues and retry temporary communication failures while logging reconnects and buffer overruns.
3. Verify that either wearable module continues acquisition when the other module or backend is unavailable.
4. Provide the backend with startup/self-test, sensor status, battery warning, error, watchdog/reset, and graceful-shutdown events.

### Exit gate

- Both modules create one complete synchronized dataset with no undetected packet corruption.
- The dashboard shows live/replayed physiology, audio/light context, synchronization, system status, model output, confidence, and errors.
- Temporary communication loss recovers through buffering/retry, and a failed sensor or module does not stop the remaining acquisition.
- Research export contains raw data, processed features, metadata, model outputs, logs, and every PRD-required version.

## Week 5: Multimodal research comparison

**Goal:** Execute the PRD study and compare physiology-only, speech-only, and combined models without clinical claims.

**Implementation status:** the research questions, study workflow, consent and data-management materials, anonymous metadata validation, synchronized dataset builder, participant-level split, candidate training, grouped validation, statistical outputs, ablations, context and duration analyses, and model lifecycle are implemented. No Week 5 dataset or model result is claimed. Evaluation waits for completed psychologist marksheets and their matching synchronized PSYCON sessions; collection also depends on ethics approval, consent, calibration, and the earlier electrical-safety gates.

### Arjun

1. Freeze the research questions: multimodal improvement, environmental robustness, motion effects, and minimum duration for stable features.
2. Prepare the PRD study workflow: recruitment, informed consent, calibration, collection, quality review, feature extraction, training, validation, analysis, and reporting.
3. Use anonymous participant IDs and record approved age group, optional biological sex, recording date/time, session duration, environmental conditions, firmware version, system status, and error logs; apply the PRD inclusion and exclusion criteria.
4. Explain speech collection, processing, retention, and access in consent materials; support withdrawal, data minimization, secure storage, limited access, and transparent reporting.
5. Create synchronized physiological features, acoustic features, transcript/language features, and ambient-light/motion context, with explicit handling of missing or corrupted data.
6. Build physiology-only, speech-only, and combined datasets using the same participant-level training, validation, and test separation.
7. Train and validate candidate models, report confidence and data-quality indicators, and complete dataset integrity, feature validation, training reproducibility, cross-validation, performance evaluation, error analysis, and external validation.
8. Produce descriptive statistics, correlations, accuracy, precision, recall, F1, ROC-AUC where applicable, confusion matrices, ROC curves, false-positive/false-negative analysis, ablations, limitations, and confidence intervals where possible.
9. Document the PRD model-update lifecycle: collect new data, review quality, retrain, validate, assign dataset/model versions, and release.

### Saksham

1. Calibrate the hardware before collection and record date, firmware version, environmental conditions, operator, method, and result.
2. Run the PRD session procedure: hardware check, battery check, wrist attachment, audio placement, synchronized start, status monitoring, stop, save, backup, and quality review.
3. Collect only approved and consented physiological, speech, light, motion, battery, sensor-status, and error data with frozen hardware and firmware.
4. Record the device configuration and environmental/motion conditions needed to answer the PRD robustness questions.

### Exit gate

- The dataset package contains raw files, processed features, metadata, model outputs, logs, backups, and tracked versions.
- A reproducible report compares physiology-only, speech-only, and combined models on participant-separated data and includes the PRD statistical analyses and external validation.
- Missing, corrupted, low-quality, or untranscribable signals are identified and handled explicitly.
- Results report overall performance, error analysis, environmental and motion effects, minimum useful duration, limitations, and no diagnostic claim.

### Current evidence and blockers

- `docs/WEEK_5_IMPLEMENTATION.md` maps every Week 5 item to its code, documentation, current evidence, and blocker.
- `docs/research/` contains the frozen questions, approved-order session procedure, consent draft, data controls, and model lifecycle. `research/templates/` contains session, calibration, and operator records.
- `research/` validates anonymous approved metadata, preserves bad and missing modalities, builds identical modality views, freezes participant assignments, evaluates two candidate model families, and produces the required metrics and analyses.
- `docs/research/DATA_REQUIREMENTS.md` defines the psychologist marksheet fields, matching device records, synchronization keys, delivery layout, privacy checks, and analysis sequence required before evaluation.
- Participant collection, physical calibration, real device configuration evidence, backup verification for human data, real multimodal comparison, stable minimum duration, and external validation remain blocked. The owners must complete these with approved marksheets, matching device sessions, the assembled devices, and a named compatible external dataset.

## Week 6: Integration, calibration, runtime, and safety

**Goal:** Pass the PRD's five integration stages and complete hardware, electrical, firmware, AI, mechanical, calibration, runtime, and safety validation.

### Saksham

1. Complete Stage 1 sensor validation, Stage 2 I²C validation, Stage 3 Wrist integration, Stage 4 Audio integration, and Stage 5 full-system integration in that order.
2. Assemble lightweight enclosures with rounded edges, battery restraint, insulation, accessible charging/reset, ventilation where required, strain relief, flush optical contact, isolated electronics, and an unobstructed microphone port.
3. Pass assembly quality control: PCB inspection, polarity, orientation, soldering, connectors, wiring, stable rails, sensor detection, firmware version, enclosure fit, strap integrity, button access, and charging access.
4. Complete calibration records for MAX30102, GSR, MCP9808, TEMT6000, and MPU6050 with date, firmware, environment, operator, method, and results; recalibrate after hardware changes or replacement.
5. Measure supply rails, current consumption, peak wireless load, battery charge/discharge, charging time, runtime, low-battery detection, brownout handling, controlled shutdown, and device temperature.
6. Run the six-hour minimum battery-powered test. Attempt and claim the 24-hour stretch goal only if it is actually measured and safely achieved.
7. Enforce protected batteries, insulated terminals, safe GSR excitation, no wired external power during wear, and no charging while GSR electrodes are attached.

### Arjun

1. Produce the PRD test report covering visual/connector/battery inspection, electrical measurements, boot reliability, initialization, error recovery, watchdog, memory stability, long-duration operation, AI validation, and mechanical checks.
2. Run rapid reboot cycles, repeated connection/disconnection, temporary communication loss, continuous wireless transmission, sensor failure, corrupt data, missing data, and safe-shutdown tests.
3. Verify feature extraction, timestamp synchronization, inference, confidence reporting, dashboard behavior, research export, and missing/corrupted-data handling end to end.
4. Record hardware revision, firmware version, date, tester, sensor initialization, I²C scan, battery voltage, runtime, charging time, communication status, notes, and corrective actions for each build.
5. Update the PRD risk register with evidence for battery depletion, sensor disconnect, I²C failure, motion artifacts, audio noise, GSR contact loss, firmware crash, wireless interruption, and data corruption.

### Exit gate

- All sensors initialize, expected I²C addresses appear without intermittent failure, audio records correctly, physiological streams remain continuous, modules operate independently, timestamps synchronize, and temporary communication loss recovers.
- The system completes the one-hour stress test and the six-hour minimum battery-powered test while recording temperature, memory, packet loss, resets, voltage, runtime, and charging behavior.
- Electrical, mechanical, wearability, calibration, GSR, battery, charging, shutdown, and safety checks pass with completed test logs and corrective actions.
- Hardware, firmware, backend, dashboard, AI, export, and failure handling pass one end-to-end validation session.

### Current implementation and blockers

- `validation/evidence.py`, `validation/stages.py`, `validation/report.py`, and `validation/risk.py` now provide validated evidence records, ordered physical stage gates, an exit report, and evidence-linked risk status.
- `validation/api_validation.py` covers normal operation, duplicates, corrupt input, missing audio, overruns, isolated sensor failure, communication loss, watchdog recovery, shutdown, dashboard access, processing, synchronization, inference, and research-export integrity against a live stack.
- `validation/stress.py` supplies the one-hour-capable simulated backend load runner and labels its output as non-physical. It cannot satisfy firmware memory, radio, temperature, battery, charging, or physical packet-loss requirements.
- `validation/templates/` contains build, electrical, runtime, assembly, and safety record templates. `docs/validation/WEEK_6_RUNBOOK.md` defines the measurement and calibration procedures, and `docs/validation/WEEK_6_TEST_REPORT.md` records current evidence.
- Validation unit tests pass. A fresh live-stack Week 6 run is blocked on the unavailable local Docker service, and all five physical stages, enclosure/assembly checks, electrical/GSR safety checks, one-hour physical stress, six-hour battery runtime, and physical end-to-end session remain blocked until completed records and artifacts are supplied.

## Week 7: Freeze, reproduce, and demonstrate

**Goal:** Freeze the complete PRD deliverable package and prove that it can be maintained, reproduced, presented, and demonstrated.

### Arjun

1. Freeze firmware, hardware, PCB, dataset, model, feature/transcription, backend, configuration/calibration, results, and documentation versions.
2. Complete the user manual, software setup, firmware build/flash, backend start, session collection, backup, replay, model evaluation, dashboard, export, and safe-shutdown instructions.
3. Prepare the competition package: executive summary, abstract, problem statement, innovation, hardware/software architecture, AI methodology, testing results, limitations, future work, verified references and official component datasheets, safety, ethics, budget, and timeline.
4. Rebuild the Engineering PRD and ensure every implementation claim is supported by test, calibration, study, or demonstration evidence; unresolved items remain clearly labeled limitations or future work.
5. Package AI documentation, dataset description, training and validation procedures, model performance, error analysis, version history, ethics, and user documentation.
6. Generate final tables, plots, reports, and research exports reproducibly from the frozen data and models.

### Saksham

1. Freeze the hardware prototype, BOM, schematics, wiring diagrams, GPIO map, power tree, assembly drawings, PCB/design files where applicable, enclosure CAD/STL, calibration records, validation records, and risk assessment.
2. Complete assembly, user, safety, troubleshooting, recovery, and maintenance guides with the PRD before-use, weekly, and monthly tasks.
3. Prepare backup firmware and practical backup hardware, then rehearse the full live demonstration: startup, sensor initialization, physiology, consented audio, synchronization, backend visualization, AI output, and safe shutdown.
4. Record and verify the required backup demonstration.

### Joint exit gate

- A third person can assemble, operate, maintain, troubleshoot, reproduce, and replay the system from the delivered package.
- The final hardware, firmware, AI, backend/interface, testing, validation, research, safety/ethics, user, assembly, maintenance, risk, and competition deliverables are present.
- Every SRS acceptance item and Chapter 33 checklist item links to evidence or is explicitly identified as an unmet limitation.
- Live and recorded demonstrations both show the complete PRD sequence and all outputs remain clearly non-diagnostic.

### Current implementation and blockers

- `release_tools/versions.json` freezes `psycon-1.0.0-rc1` as a candidate and names every remaining blocker. `release_tools/package.py` creates and verifies a deterministic tracked-file archive with sizes and SHA-256 hashes while excluding audio, secrets, study paths, and release output.
- `docs/release/` contains the user manual, software and firmware commands, one-set circle procedure, assembly and maintenance guide, recovery steps, competition package, verified official links, AI model card, dataset card, evidence matrix, release checklist, and live and recorded demonstration runbook. Budget and demonstration templates are under `release_tools/templates/`.
- The Engineering PRD and root documentation include the Week 7 release state. Software tests and archive verification can establish the candidate package, but they cannot freeze absent hardware, calibration, participant data, model results, or demonstrations.
- Final hardware and PCB files, real Wrist acquisition, physical Week 6 evidence, a priced BOM, approved PSYCON sessions, the final model and external validation, third-person reproduction, backup hardware, and live and recorded demonstration evidence remain blocked. The release tool rejects `final` while blockers remain.

## PRD coverage map for Weeks 3–7

| Week | Engineering PRD coverage |
| --- | --- |
| Week 3 | Audio hardware, wiring, firmware, buffering, ambient light, acoustic features, transcription required for language features, conversation analysis, privacy, audio packet fields, and audio troubleshooting from Chapters 2–8, 15, 17, 19, 25, 26, and 30 |
| Week 4 | Communication, common-epoch synchronization, API/authentication/validation, database, feature and inference services, dashboard, export, storage structure, backups, and version control from Chapters 3, 6–8, 18, 25, and 27 |
| Week 5 | Research questions, participant/session protocol, recorded variables, ethics/privacy, data management, model workflow, statistical analysis, ablation, external validation, limitations, and AI checklist from Chapters 7, 17–20, 23, and 33 |
| Week 6 | Five-stage integration, manufacturing/assembly, calibration, test logs, risk mitigation, hardware/electrical/firmware/AI/mechanical tests, six-hour runtime, and safety acceptance from Chapters 2, 4–6, 8, 9, 13–15, 28, and 33 |
| Week 7 | Complete deliverables, competition documentation, live/recorded demonstration, maintenance, troubleshooting, references, revision history, final checklist, and conclusion from Chapters 8–10, 12, 16, 18, 19, and 21–34 |

## Operating and fallback rules

Interfaces freeze at the start of each week. Failed gates move forward and remove optional work; later weeks cannot claim completion over an unverified dependency.

Every update states what became true, its evidence, the acceptance criterion advanced, the owner/next action for failures, and any changed part, interface, safety assumption, research claim, or version.

- If a sensor is unstable, isolate it and narrow the evaluated modality; never substitute placeholder values.
- If audio cannot be handled ethically/reliably, use consented engineering fixtures or documented on-device features; never collect undisclosed speech.
- If transport loses data, report the queue limit and visible loss rather than calling it continuous.
- If six hours fails, stop readiness claims and fix the cause before attempting 24 hours.
- If 24 hours fails, report actual runtime; a powered run is not battery-life evidence.
- If audio does not improve the model, publish the negative ablation and error analysis.
- Without ethics approval, finish bench/public-data/fixture work without a human psychological study.
- Stop worn testing for unsafe charging, GSR excitation, exposed conductors, damaged batteries, or excessive temperature.

## Completion calculation

The approximately 59% score is recomputed with fixed weights:

| Workstream | Weight | Completion rule |
| --- | ---: | --- |
| Requirements and documentation | 15% | Current, consistent, cited, reproducible documents and guides |
| Hardware, electrical, mechanical | 20% | Integrated hardware with measurements, calibration, safety, wearability |
| Device firmware and acquisition | 20% | Real continuous sensing, buffering, quality, errors, power, recovery |
| Protocol, backend, synchronization | 15% | Cross-language contract and durable synchronized replay path |
| Data science and research | 15% | Reproducible physiology/audio/fusion evaluation and external validation |
| Verification, safety, release | 15% | Integration/runtime evidence, risk closure, guides, and demonstrations |

Partial credit is awarded only when the result is usable by the next stage. Prose cannot replace failed or missing evidence.
