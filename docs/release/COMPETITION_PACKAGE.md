# PSYCON competition package

## Executive summary

PSYCON is a two-module research prototype for synchronized collection of Wrist physiology, motion, temperature, central audio, and ambient light during supervised group discussion. The project asks whether these inputs can estimate defined observable behaviours or research stress labels with calibrated uncertainty. It does not diagnose a participant or replace a psychologist.

The Wrist Module assigns MAX30102 PPG, ADS1115-based GSR, MCP9808 temperature, and MPU6050 motion to one focal wearer. The Audio Module uses an INMP441 microphone and TEMT6000 light sensor. A Flask service stores immutable Protocol v2 chunks, corrects bounded device-clock observations, processes features and inference, reports quality and errors, and creates hashed research exports.

## Problem statement

Questionnaires and isolated measurements miss how physiology, speaking behaviour, movement, environment, and group context change together. A synchronized research record can test these associations, but only if speaker attribution, participant separation, consent, data quality, uncertainty, and physical safety remain visible.

## What is new in this implementation

The system keeps its two sensing modules independent, uses one binary packet contract across Python, TypeScript, and C++, preserves raw-chunk hashes and timing uncertainty, isolates missing or corrupt streams, and compares physiology-only, speech-only, and combined models on the same participant split. The audio path abstains on unusable input and identifies at most one separately consented enrolled wearer. Week 6 evidence rules prevent simulated results from passing physical gates.

## Demonstration configuration

With one hardware set, four to six students sit in numbered positions around the center Audio Module. One focal participant wears the Wrist Module. The team rotates the wearable across later sessions rather than assigning one person's physiology to the group. The center recording can produce anonymous speaker clusters, but overlap or insufficient clean speech remains unknown. The observer and approved self-report provide labels; the behavioural marksheet itself is not stress ground truth.

## Hardware and software architecture

The Wrist ESP32 uses I2C on `GPIO21` and `GPIO22`. Expected sensor addresses are MAX30102 `0x57`, MPU6050 `0x68`, MCP9808 `0x18`, and ADS1115 `0x48`. The Audio ESP32 uses I2S with WS `GPIO25`, SCK `GPIO26`, SD `GPIO33`, and INMP441 L/R tied to ground. Both modules have independent protected LiPo power paths.

The server uses Flask, PostgreSQL, and S3-compatible object storage. It authenticates devices and operators, accepts idempotent Protocol v2 chunks, records clock offset and uncertainty, processes stored sessions, renders a local dashboard, and exports a ZIP with a hash-checked manifest. Local transcription, diarization, speaker verification, and acoustic analysis run only when requested and configured.

## AI method and current results

The checked-in WESAD development table contains 13,698 windows from 15 subjects. Its best recorded model is EDA XGBoost with 0.932 accuracy. The exported multimodal-wrist logistic model records 0.915 accuracy, 0.895 F1, 0.995 recall, and 0.130 false-positive rate on one grouped holdout. These are public-dataset development results. They do not establish PSYCON hardware performance, student stress prediction, clinical validity, or external validity.

The Week 5 evaluator can join approved marksheets and synchronized device sessions, preserve missing inputs, freeze participant-level assignments, compare logistic regression and random forest, calculate grouped validation and participant-bootstrap intervals, run ablations, analyze errors and context, and estimate useful duration. No real PSYCON study dataset has been supplied, so the project has no PSYCON model result.

## Verification status

Software tests cover protocol compatibility, audio quality and abstention, backend logic, synchronization, research controls, evidence rules, failure-scenario assessment, stress-runner metrics, release packaging, and integrity verification. The PRD compiles from source. A previous Week 4 Compose path passed, but the Week 6 live scenario suite could not be rerun because Docker Desktop was unavailable.

Physical Stage 1 through Stage 5, integrated sensor acquisition, GSR electrical safety, enclosure inspection, calibration, power measurements, one-hour stress, six-hour battery runtime, and live or recorded hardware demonstrations remain open. These gaps block a final or competition-ready claim.

## Safety and ethics statement

PSYCON requires ethics approval, anonymous IDs, informed consent and assent where applicable, separate audio and biometric-profile choices, withdrawal and deletion handling, restricted encrypted storage, and a bystander policy. The device may not be worn until its exact revision passes electrical and mechanical review. Charging and wired power are prohibited during wear, and charging is prohibited with GSR electrodes attached.

## Limitations

- One Wrist Module measures only one focal wearer per session.
- One center microphone loses certainty during overlapping, distant, short, or noisy speech.
- Current code stores one encrypted wearer profile, while other speakers remain anonymous within the recording.
- Wrist firmware still emits placeholder sensor values and cannot collect valid PSYCON physiology.
- The GSR front end and battery behavior have no supplied physical acceptance record.
- WESAD results cannot be transferred to the intended student discussion population without a new study and external validation.
- The system has no diagnostic indication and must abstain when input or identity quality is inadequate.

## Future work

Finish real continuous Wrist drivers, finalize and review the GSR circuit, measure and pass the full hardware gates, run the approved rotating-wearer pilot, test marksheet reliability, freeze a powered sample-size plan, and validate the final model on untouched participants and a separate school or site. Multiple consented microphones or a microphone array may improve overlap handling, but that is a later hardware revision and needs new validation.

## Budget

The BOM fixes quantities but the repository contains no dated supplier quotations, taxes, shipping, fabrication cost, or verified purchased part numbers. A defensible total cannot be claimed yet. Before submission, enter the actual vendor, part number, quantity, unit price, shipping, tax, purchase date, and invoice reference for both modules, cells, chargers, enclosure materials, electrodes, wiring, connectors, and backup parts. Keep tools and reusable equipment separate from per-unit cost.

## Timeline record

| Week | Delivered scope | Open dependency |
| --- | --- | --- |
| 1 and 2 | Requirements, architecture, protocol, hardware allocation, firmware scaffolds | Physical integration |
| 3 | Audio features, quality, transcription, speaker analysis, and local demo | Intended-microphone validation |
| 4 | Backend, synchronized ingestion, dashboard, processing, export, backup, and simulation | Physical transport |
| 5 | Study controls, dataset join, grouped evaluation, and reporting | Approved marksheets and matching sessions |
| 6 | Evidence records, ordered gates, failure scenarios, stress tooling, and safety procedures | All physical records and live rerun |
| 7 | Candidate release packaging, operating guides, competition record, evidence matrix, and demo procedure | Hardware, study, external validation, and demonstrations |

## Submission decision

This package is a reproducible software and documentation release candidate. Present it as a working software architecture with unverified physical integration. Do not call it a completed wearable, validated stress detector, or competition-ready final system until every blocker in `release_tools/versions.json` is closed with accepted evidence.
