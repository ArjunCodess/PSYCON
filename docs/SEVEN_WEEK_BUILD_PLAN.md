# PSYCON Seven-Week Build Plan

**Assessment date:** 4 August 2026

**Owners:** Arjun Vijay Prakash, software and research; Saksham Yadav, hardware and device firmware

**Starting completion:** 40% overall; approximately 15% of end-to-end functional acceptance demonstrated

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
| Engineering paper | Mostly complete design | 34 TeX chapters and 36-page PDF; placeholder references and stale PDF email remain |
| Hardware | Partial reported bring-up | BOM, GPIO, wiring, and power design; no integrated or measured evidence in repository |
| Wrist firmware | Scaffold | Compiles and scans I2C; sensor samples are placeholders |
| Audio firmware | Scaffold | Compiles and initializes 16 kHz I2S; capture is discontinuous and TEMT6000 is absent |
| Protocol | Partial implementation | Four tests and type-check pass; no cross-language byte-level contract |
| Backend | Designed | No API, authentication, validator, synchronizer, database, dashboard, or export |
| ML | Wrist baseline | WESAD models/artifacts exist; no speech or fusion evaluation |
| Validation | Procedures only | No calibration, integrated logs, runtime, discharge, thermal, or demo evidence |

## Definition of done

1. All six sensors initialize and produce real values with documented rates, units, configurations, quality, and errors.
2. Each module continues when the other module or backend fails.
3. Acquisition is continuous and exposes every sequence gap, corruption, reboot, contact loss, saturation, and overrun.
4. C++, TypeScript, and Python decode identical versioned wire fixtures.
5. Authentication, validation, synchronization, durable storage, features, inference, visualization, and research export work end to end.
6. A long run reports offset, drift, late data, loss, queue depth, and reboot epochs.
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

Week 1 must decide whether consented research sessions transmit raw audio, on-device acoustic features, or both in separate modes. The shared packet contract must include protocol version, module/device/session IDs, sequence, acquisition timestamp/common epoch, battery, status/quality, checksum, and the paper-defined modality payload.

## Week 1: Reproducible and electrically safe baseline

**Goal:** Reconcile the paper, code, compiled artifacts, hardware variants, and test environment.

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

**Goal:** Produce continuous, interpretable audio and synchronized light data without hidden gaps.

### Arjun

1. Add deterministic audio tests for silence, impulses, tones, clipping, speech, and noise.
2. Implement quality, dBFS/level, pitch/prosody, timing, and a versioned standardized feature vector where licensing permits.
3. Preserve provenance from source samples to feature windows.
4. Implement explicit insufficient, corrupt, clipped, noisy, and missing-audio outcomes.

### Saksham

1. Remove the 250 ms delay and use continuous I2S DMA with multiple buffers and overrun counters.
2. Verify channel, sign, bit shift, sample rate, clipping, DC behavior, playback speed, and noise floor.
3. Integrate TEMT6000 and document ADC configuration and units.
4. Freeze placement/enclosure after speech, walking, fabric, Wi-Fi, and nearby-speaker tests.
5. Add battery, microphone status, quality, sequence, timestamp, and errors to the real packet path.

### Exit gate

- A one-hour capture has the expected sample count, measured clock error, and no unexplained gaps.
- Known tones reproduce expected duration/frequency; bad fixtures abstain.
- Light readings align with the audio timeline.
- Capture continues through a temporary transport failure and exposes any loss.

## Week 4: Backend, synchronization, and data management

**Goal:** Turn both devices into one durable, replayable research session.

### Arjun

1. Implement API gateway, authentication, validation, time synchronization, durable storage, feature jobs, inference, status/visualization, and export.
2. Store hardware, firmware, session, packet, calibration, feature, model, error, and deletion versions.
3. Implement idempotency, checksums, gaps, duplicates, reboot epochs, late data, and crash recovery.
4. Reconstruct the common timeline and record offsets, corrections, and drift.
5. Add deterministic saved-session replay and raw-to-result lineage.
6. Implement access control, pseudonymous IDs, retention/deletion state, backups, and audit logs.

### Saksham

1. Implement the chosen BLE/Wi-Fi path without blocking acquisition.
2. Test access-point/backend loss, reconnect, reboot, queue saturation, and recovery.
3. Measure current and temperature during normal, reconnect, and backlog operation.
4. Prove independent operation when the other module/backend is unavailable.

### Exit gate

- A two-hour dual-module session survives a ten-minute interruption without hidden loss or duplicate processing.
- Reports contain expected/received samples, gaps, corruptions, duplicates, offsets, drift, reboots, queues, and latency.
- The backend never acknowledges data before durable storage.
- Export links raw records, features, versions, outputs, and deletion state.

## Week 5: Multimodal research comparison

**Goal:** Test the paper's primary question with identical splits and honest missingness.

### Arjun

1. Make WESAD acquisition and external-data tests reproducible without committing restricted raw data.
2. Build a licensed public-audio development path and ethically permitted final-device engineering dataset.
3. Create aligned physiology-only, speech-only, and combined windows.
4. Use repeated group validation or leave-one-subject-out evaluation with confidence intervals and no leakage.
5. Report balanced accuracy, macro-F1, sensitivity, specificity, false-positive rate, calibration, confusion matrices, per-subject results, motion/environment strata, missingness, and errors.
6. Implement quality-aware fusion with explicit `insufficient_signal` behavior.
7. Report a negative ablation if speech does not improve the wrist baseline.

### Saksham

1. Record consented calibration/engineering sessions with frozen hardware and firmware.
2. Capture calm, speech, movement, non-wear, contact-loss, and controlled-environment conditions without clinical claims.
3. Record motion, contact, light, microphone placement, and device state for every session.
4. Freeze the tested BOM, wiring, enclosure, rates, and calibration settings.

### Exit gate

- Saved sessions reproduce identical features and inputs.
- One report compares all three modalities on identical subject-independent splits.
- Bad or missing signals abstain/fall back explicitly.
- No clinical accuracy or unsupported improvement is claimed.

## Week 6: Integration, calibration, runtime, and safety

**Goal:** Produce the physical evidence required by the paper's integration and final checklists.

### Saksham

1. Assemble the final wearable with fixed wiring, labels, insulation, strain relief, controls, indicators, battery restraint, sensor contact, microphone opening, and charging access.
2. Complete calibration records with date, operator, versions, environment, method, reference, result, limitations, and pass/fail.
3. Measure rails, current, discharge, charging, brownout, low-battery behavior, queue flush, shutdown, temperature, and restart.
4. Run the six-hour minimum test; attempt 24 hours only with a reviewed safe power arrangement.
5. Inspect the complete build before and after the run.

### Arjun

1. Automate the integration report from device/backend logs and result provenance.
2. Inject communication loss, backend restart, reboot, disconnect, corruption, missing data, and replay failures.
3. Verify memory, watchdog/reset cause, loss, drift, latency, storage growth, and deletion.
4. Update the risk register with measured evidence, owners, mitigation, and residual risk.

### Exit gate

- The integrated system passes six hours with quantified completeness, stability, drift, current, temperatures, and recovery.
- Untethered runtime comes from a measured discharge curve; 24 hours is claimed only if achieved.
- Critical safety checks pass, including GSR excitation and charging policy.
- Calibration records, test logs, failures, and risks are stored with the release.

## Week 7: Freeze, reproduce, and demonstrate

**Goal:** Turn measured evidence into the competition package. New features are prohibited.

### Arjun

1. Freeze protocol, backend, dataset, feature, model, configuration, and report versions.
2. Document setup, firmware build, backend start, session creation, replay, evaluation, and report generation.
3. Replace bibliography placeholders with verified sources, rebuild the current PDF, and align claims with results.
4. Produce the executive summary, architecture/method, results, limitations, references, safety/ethics, budget, and timeline.
5. Generate all tables/plots from scripts.

### Saksham

1. Freeze BOM, schematics, wiring, power tree, hardware revision, enclosure, calibration, configuration, and maintenance.
2. Complete assembly, user, safety, troubleshooting, and recovery guides with photographs.
3. Rehearse startup, sensors, physiology, consented audio, synchronization, visualization, inference, recovery, and shutdown.
4. Record and verify a backup demonstration.

### Joint exit gate

- A third person can reproduce the build and replay a session.
- Every SRS and final-checklist claim links to evidence.
- Live and recorded demonstrations pass.
- The release separates verified results, limitations, open risks, and future work.

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

The 40% baseline is recomputed with fixed weights:

| Workstream | Weight | Completion rule |
| --- | ---: | --- |
| Requirements and documentation | 15% | Current, consistent, cited, reproducible documents and guides |
| Hardware, electrical, mechanical | 20% | Integrated hardware with measurements, calibration, safety, wearability |
| Device firmware and acquisition | 20% | Real continuous sensing, buffering, quality, errors, power, recovery |
| Protocol, backend, synchronization | 15% | Cross-language contract and durable synchronized replay path |
| Data science and research | 15% | Reproducible physiology/audio/fusion evaluation and external validation |
| Verification, safety, release | 15% | Integration/runtime evidence, risk closure, guides, and demonstrations |

Partial credit is awarded only when the result is usable by the next stage. Prose cannot replace failed or missing evidence.
