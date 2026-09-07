# Week 6 validation runbook

This runbook turns the Week 6 plan into repeatable tests and evidence records. Run the five integration stages in order. A stage passes only when every required procedure has a `passed` record from `physical_measurement`; fixtures, unit tests, and simulated devices cannot pass a physical gate.

## Safety stop conditions

Stop immediately for a swollen, punctured, hot, or unprotected cell; reversed polarity; exposed conductors; unstable rails; unsafe GSR excitation; unexpected heating; smoke; odor; repeated brownout; or uncontrolled restart. Disconnect the battery in a safe area and record the failure and corrective action before retesting.

- Use protected LiPo cells, insulated terminals, battery restraint, and strain relief.
- Do not connect a charger or wired external power while either module is worn.
- Do not charge while GSR electrodes are attached.
- Do not attach GSR electrodes to a person until its excitation, current limiting, isolation, and fault behavior pass an electrical review on the exact hardware revision.
- Use a current-limited bench supply for initial bring-up, then disconnect it before any battery-powered or worn test.

## Evidence handling

Copy the relevant file from `validation/templates/`, replace every example or `not_recorded` value, and keep measurement logs, photos, serial logs, and instrument exports outside the source tree in the controlled project evidence store. Put stable relative evidence references or hashes in the record's `artifacts` field.

Every record needs a unique record ID, UTC timestamp, operator, hardware revision, firmware versions, conditions, measurements, result, artifacts, notes, and corrective actions. A failed record must name a corrective action. Retesting creates a new record rather than overwriting the failure.

Generate the consolidated report with:

```powershell
python -m validation.report --evidence <evidence.json> --output-dir validation-output/report
```

The command exits with code 2 while any exit gate remains open. This is intentional.

## Stage 1: individual sensor validation

Power and test one sensor path at a time before enabling the full bus. Record raw values and errors, not derived psychological interpretations.

| Procedure ID | Method | Acceptance evidence |
| --- | --- | --- |
| `sensor_max30102` | Confirm address `0x57`, record red/IR values with no contact and stable optical contact, then compare pulse timing with a reference pulse measurement. Check saturation and motion response. | Address is stable, contact and loss of contact are visible, the waveform does not remain saturated, pulse timing is plausibly aligned with the reference, and there are no bus errors during the recorded interval. This is a functional check, not medical accuracy calibration. |
| `sensor_mpu6050` | Confirm address `0x68`, log stationary readings in each known axis orientation, then apply slow known rotations and motion. | Gravity changes to the expected axis and sign, stationary bias and noise are recorded, movement appears on the expected axes, and communication remains stable. |
| `sensor_mcp9808` | Confirm address `0x18` and compare readings with a traceable or identified reference thermometer at two or more stable temperatures after equilibration. | Offset, repeatability, reference instrument, stabilization time, and environmental conditions are recorded; values remain stable enough for the intended research use. |
| `sensor_ads1115_gsr` | Confirm address `0x48`, measure the GSR front end with open circuit and known reference resistors spanning the expected range. Measure electrode excitation and fault current before any human contact. | ADC response is monotonic and unsaturated over the declared range, open/contact loss is detectable, excitation and current limiting satisfy the reviewed circuit limits, and no person was used before electrical approval. |
| `sensor_inmp441` | Capture silence, a known tone, and speech at the intended placement. Inspect channel selection, amplitude, clipping, noise floor, packet continuity, and DMA errors. | The selected channel is correct, silence and signal are distinguishable, the declared working level does not clip, audio is intelligible for the intended pipeline, and no DMA overrun occurs in the recorded interval. |
| `sensor_temt6000` | Record output in covered, stable indoor, and controlled bright conditions alongside an identified lux reference where available. | Output changes monotonically, does not stick at a rail in the intended range, repeatability is recorded, and dark/bright states are distinguishable. |

Calibration records must name the method, environment, firmware, operator, raw result, reference equipment, and acceptance decision. Recalibrate after replacement, rewiring, enclosure changes that affect contact or airflow, or firmware changes that alter acquisition.

## Stage 2: I2C bus validation

1. Run repeated address scans through boot, idle, acquisition, and wireless transmission. `i2c_address_scan` passes only when `0x57`, `0x68`, `0x18`, and `0x48` appear without duplicates or intermittent loss.
2. Run the assembled Wrist I2C bus continuously for one hour. `i2c_one_hour_stability` records scan/read counts, errors, retries, sensor starvation, timestamps, free heap, resets, and temperature. Any unexplained disappearance, bus lock, or reset fails the test.

## Stage 3: integrated Wrist Module

- `wrist_continuity` records simultaneous PPG, GSR, temperature, and motion acquisition with timestamps, sequence gaps, free heap, resets, and current.
- `wrist_sensor_isolation` disconnects or faults one sensor under controlled bench conditions and proves the failure is reported without fabricating its values or stopping the remaining sensors.
- `wrist_buffer_recovery` interrupts communication within the designed queue limit and proves buffered sequence handling, visible loss beyond capacity, and orderly recovery.

Do not proceed unless all three records pass and Stage 2 already passed.

## Stage 4: integrated Audio Module

- `audio_continuity` records continuous I2S acquisition and transmission with buffer counts, overruns, gaps, free heap, resets, and temperature.
- `light_response` proves TEMT6000 readings remain responsive while audio and wireless transmission run concurrently.
- `audio_buffer_recovery` interrupts communication within the designed queue limit and verifies recovery without silent corruption; loss beyond capacity must be counted and exposed.

## Stage 5: full system

- `module_independence` proves one module can restart or disconnect without resetting or corrupting the other.
- `time_sync` records measured offsets, drift, uncertainty, corrected timestamps, and a shared observable event across both devices.
- `communication_recovery` covers repeated connect/disconnect and temporary communication loss, with gaps and recovery visible in the backend.
- `safe_shutdown` proves low-battery or commanded shutdown stops acquisition, flushes within the declared limit, closes the session, and rejects later writes.
- `backend_e2e` covers physical acquisition, synchronization, storage, feature extraction, quality/confidence or abstention, dashboard display, hashed research export, and missing/corrupt input handling in one session.

## Assembly, enclosure, and electrical checks

Complete `validation/templates/assembly_checklist.md` for each build. Photograph the PCB, battery restraint, insulation, connectors, strap, strain relief, sensor contact surfaces, microphone port, reset access, and charging access.

Use `validation/templates/electrical_record.json` to record instrument IDs and calibrated measurements for the 3.3 V rail during boot, idle, sensing, and peak wireless transmission; idle and peak current; charge current and time; discharge behavior; low-battery warning; brownout voltage and recovery; controlled shutdown; and maximum component and enclosure temperature. A visual inspection or nominal component rating is not a measurement.

## Reliability and runtime

Run rapid reboot cycles, repeated connect/disconnect cycles, sensor failure, communication loss, watchdog recovery, corrupt data, missing data, continuous transmission, memory stability, and shutdown. Record the exact cycle count, failure count, firmware versions, logs, and corrective actions.

The one-hour test uses the complete physical system and records voltage, current where practical, temperature, free heap, packet attempts, accepted packets, sequence gaps, retries, overruns, resets, synchronization uncertainty, and sensor errors. The six-hour test must be battery-powered with both modules operating in their intended mode; use `validation/templates/runtime_record.json`, and do not connect charging or wired power during the run. A powered bench test does not establish battery runtime.

Attempt the 24-hour stretch goal only after the six-hour test passes and the measured temperature, discharge curve, cell protection, and remaining capacity make the extended test safe. Report the actual measured duration if the system stops early.

## Software and simulated-stack validation

Start the local backend before running these commands:

```powershell
docker compose up --build -d
python -m validation.api_validation --url http://localhost:8000 --output validation-output/software-api.json
python -m validation.stress --url http://localhost:8000 --duration-seconds 3600 --interval-seconds 1 --output validation-output/stress.json
docker compose down
```

The API runner checks normal ingestion, idempotent duplicates, corrupt CRC rejection, missing audio, overrun reporting, isolated sensor failure, communication gaps and reconnect, watchdog reporting, safe shutdown, feature creation, inference/confidence, dashboard access, and hashed research export integrity. The stress runner exercises the simulated transport path. Its output deliberately contains `physical_evidence: false`, so it cannot satisfy the one-hour physical or battery-runtime procedures.

## Completion rule

Week 6 passes only when the report shows every procedure and all five ordered stages passed with the required evidence source. If hardware or the Docker service is unavailable, record the item as blocked and leave the exit gate open.
