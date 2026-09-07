# PSYCON: Psychological Condition Monitoring System

PSYCON is a two-module wearable research prototype for studying whether synchronized physiological, environmental, and speech-derived signals can estimate indicators associated with psychological well-being. The Wrist Module measures PPG, EDA/GSR, temperature, and motion; the Audio Module captures speech and ambient light. The intended experiment compares physiology-only, speech-only, and combined multimodal inference.

PSYCON is a research and screening prototype, not a medical device. It must not be presented as diagnosing depression, anxiety, PTSD, ADHD, autism, stress disorders, or any other clinical condition.

## Current completion

**Overall project completion: approximately 58% as of 8 September 2026.** This weighted estimate measures progress toward the PRD's competition-ready integrated prototype. It credits the Compose-verified Week 4 server, the prepared Week 5 research pipeline, and the Week 6 validation tooling, but records no Week 5 dataset result or Week 6 physical pass.

| Workstream | Weight | Completion | Contribution | Evidence and remaining gap |
| --- | ---: | ---: | ---: | --- |
| Requirements and engineering documentation | 15% | 95% | 14.25% | The tracked 34-chapter PRD, current PDF, reproducibility matrix, protocol specification, device-feature contract, and complete audio/transcription/language contract are present. Verified bibliography sources and completed physical records remain open. |
| Hardware, electrical, and mechanical | 20% | 35% | 7.0% | Components and wiring are documented and reported as individually checked. There is no repository evidence of an integrated wearable, calibrated GSR front end, measured rails/current/temperature, enclosure, or runtime test. |
| Device firmware and acquisition | 20% | 30% | 6.0% | Both firmware targets compile. Audio I2S/BLE and wrist I2C/BLE bring-up exist, but wrist values are placeholders and continuous sensing, quality, storage, recovery, power, and watchdog behavior are absent. |
| Protocol, backend, and synchronization | 15% | 72% | 10.8% | Protocol v2 has cross-language fixtures; the PostgreSQL/S3-compatible Flask service provides authenticated idempotent ingestion, clock correction, jobs, exports, backups, a dashboard, deterministic device simulation, nine failure scenarios, export verification, and a timed load runner. The earlier live Compose path passes, but the new Week 6 scenarios need a running Docker service and physical-device integration remains open. |
| Data science and research pipeline | 15% | 85% | 12.75% | Research questions and records, WESAD results, wrist and audio features, synchronized modality assembly, participant-safe splits, candidate training, grouped validation, confidence intervals, ablations, error analysis, and context/duration code exist. The psychologist marksheets, matching PSYCON sessions, real multimodal results, minimum-duration result, and external validation remain. |
| Verification, safety, and release evidence | 15% | 45% | 6.75% | Evidence records, ordered stage gates, failure-scenario checks, stress tooling, risk rules, and runbooks are implemented. Physical calibration, runtime, electrical, safety, participant study, Week 5 model evidence, external validation, and device demonstrations remain. |
| **Total** | **100%** |  | **57.6% ≈ 58%** | Week 4 server software, Week 5 analysis code, and Week 6 validation controls exist; hardware transport, real synchronization, physical measurements, approved collection, and empirical Week 5 results remain open. |

The narrower end-to-end functional prototype is roughly **34% complete** because the server path runs with simulated devices and now has broader failure checks, but the research path has no real PSYCON dataset. Real sensor acquisition, hardware-to-server transport, power evidence, approved participant data, and external validation remain absent.

## Source of truth

The authoritative product requirements and engineering specification is [`docs/engineering_prd/`](docs/engineering_prd/):

- [`main.tex`](docs/engineering_prd/main.tex) includes all 34 chapters across five volumes.
- [`chapters/`](docs/engineering_prd/chapters/) contains the SRS, engineering designs, integration plan, research method, ethics, test procedures, and final checklist.
- [`main.pdf`](docs/engineering_prd/main.pdf) is the compiled engineering PRD.
- [`references.bib`](docs/engineering_prd/references.bib) contains TODO placeholders, so the package is not yet a submission-ready academic paper.

Chapter-level “completed” labels mean that a topic has been documented. Implementation completion is controlled by Chapter 2's acceptance criteria, Chapter 8's integration gates, Chapter 28's test procedures, and Chapter 33's final checklist.

## System design

| Module | Controller and sensors | Intended output |
| --- | --- | --- |
| Wrist | ESP32, MAX30102, ADS1115 plus GSR electrodes, MCP9808, MPU6050 | Heart rate, raw PPG, EDA/GSR, temperature, acceleration/orientation, battery, and signal quality |
| Audio | ESP32, INMP441, TEMT6000 | Audio or acoustic features, ambient light, battery, and capture status |

The Wrist I2C bus uses `GPIO21` for SDA and `GPIO22` for SCL. Expected addresses are MAX30102 `0x57`, MPU6050 `0x68`, MCP9808 `0x18`, and ADS1115 `0x48`; GSR enters ADS1115 A0.

| INMP441 | ESP32 |
| --- | --- |
| VCC | 3.3 V |
| GND | GND |
| WS | GPIO25 |
| SCK | GPIO26 |
| SD | GPIO33 |
| L/R | GND |

The paper uses protected LiPo cells and TP4056 USB-C charger modules but explicitly leaves runtime, charge-while-operating behavior, rail stability, thermal behavior, controlled shutdown, and the final GSR excitation/front end for validation. Charging while worn or with GSR electrodes attached is prohibited until the exact power path passes review.

## What exists today

### Firmware

[`firmware/ear/src/main.cpp`](firmware/ear/src/main.cpp) configures 16 kHz I2S, calculates RMS, mean absolute energy, and zero-crossing rate, and publishes a BLE feature packet. It reads only 256 samples before a 250 ms delay, does not read TEMT6000, and lacks continuous buffering, storage, reconnect, quality, battery, watchdog, and recovery behavior.

[`firmware/wrist/src/main.cpp`](firmware/wrist/src/main.cpp) initializes I2C, scans addresses, and publishes a BLE packet. Its BVP, EDA, and acceleration values are placeholders; the real MAX30102, ADS1115/GSR, MPU6050, and MCP9808 drivers are not integrated.

Both PlatformIO targets compile. Compilation proves source/toolchain compatibility, not physical sensor behavior.

### Protocol

[`protocol/`](protocol/) contains the Protocol v2 byte contract, shared binary fixtures, Python and TypeScript decoders, a C++ header, normalized wrist/session/quality/calibration types, validation, and logistic-regression inference. Cross-language fixture tests, Vitest, and `tsc --noEmit` pass; the Flask backend ingests the same packet contract and assigns synchronized timestamps from bounded clock observations.

### Audio analysis

[`ml/src/audio.py`](ml/src/audio.py) decodes Protocol v2 PCM16 packets with the `psycon_audio` extractor for quality, dBFS, pitch statistics, voice stability, prosody, spectral, and timing features. It preserves packet hashes and sample lineage and returns explicit `usable`, `insufficient_audio`, `clipped`, `too_noisy`, `corrupt`, or `missing_audio` states before inference.

[`ml/src/transcription.py`](ml/src/transcription.py) quality-gates and transcribes consented usable regions locally with segment and word timestamps, language detection, confidence, source-sample offsets, and explicit failure states. [`ml/src/language_features.py`](ml/src/language_features.py) implements the transparent English baseline; unsupported languages abstain and filler-word classification is excluded.

[`ml/src/speaker_analysis.py`](ml/src/speaker_analysis.py) adds optional local pyannote diarization, encrypted three-recording wearer enrollment with SpeechBrain ECAPA embeddings, conservative wearer verification, anonymous speaker labels, word attribution, per-speaker speaking rates, pauses, response gaps, overlaps, interruptions, and conversational voice-quality estimates. [`ml/src/voice_quality.py`](ml/src/voice_quality.py) uses Praat's waveform-aligned raw-cross-correlation path for local absolute and relative jitter, RAP, PPQ5, and DDP, including an optional controlled sustained-vowel measurement. Heavy models load only when requested, and deterministic tests use fakes so the normal suite does not need gated downloads.

[`demo/audio_demo.py`](demo/audio_demo.py) processes deterministic generated fixtures and writes [`results/demo/audio_demo.json`](results/demo/audio_demo.json). This proves the software path and abstention behavior without using personal recordings; it does not prove the INMP441, TEMT6000, continuous DMA, placement, clock, or transport behavior.

[`demo/audio_web_app.py`](demo/audio_web_app.py) provides a local upload page for consented WAV, MP3, and OGG recordings. It enrolls or deletes one encrypted wearer profile, keeps uploaded audio and an optional 3--8 second sustained `/a/` vowel in memory, runs optional local transcription and speaker analysis, and displays quality, speaker turns, attributed words, conversation timing, speaking rates, conversational jitter estimates, controlled-vowel jitter, language features, and provenance. It does not send recordings to a speech API or make a psychological or diagnostic inference.

### Week 4 backend and dashboard

[`backend/`](backend/) implements the hardware-facing Flask service with PostgreSQL metadata, S3-compatible immutable storage, per-device and operator credentials, Protocol v2 idempotency, common-epoch synchronization with offset/drift uncertainty, independent status/error events, PostgreSQL-backed jobs, feature processing, research exports, and backup verification. [`docker-compose.yml`](docker-compose.yml) supplies PostgreSQL and MinIO locally, while [`backend/simulator.py`](backend/simulator.py) sends deterministic dual-device sessions through the real HTTP contract. The local dashboard runs at port 8000 and polls stored session state; deployment and physical hardware connection remain open. See [`docs/BACKEND.md`](docs/BACKEND.md).

### WESAD baseline

[`main.py`](main.py) runs WESAD loading, resampling, overlapping 10-second windows, wrist feature extraction, subject-group train/test splitting, five model families, and artifact generation.

The checked-in processed table contains **13,698 windows from 15 subjects**: 8,760 calm and 4,938 high-stress. The best recorded accuracy is 0.932 for EDA XGBoost; the exported multimodal-wrist logistic run records 0.915 accuracy, 0.895 F1, 0.995 recall, and 0.130 false-positive rate on one grouped holdout. These are WESAD development results, not PSYCON hardware or clinical validation.

There is no approved recorded-speech dataset, synchronized device dataset, real physiology/audio/fusion result, or external validation. Raw WESAD pickles are absent, so preprocessing cannot be reproduced from a clean checkout without separately obtaining WESAD.

### Week 5 research workflow

Week 5 built the study controls and the full analysis path, but it produced no PSYCON study result. The repository has no completed psychologist marksheets or matching participant recordings, and the previously generated fake-data results were removed.

[`research/schema.py`](research/schema.py) validates anonymous session metadata, approval, consent, withdrawal state, calibration references, timestamps, and synchronization quality. [`research/dataset.py`](research/dataset.py) joins physiology, speech, and context on common time windows, rejects conflicting labels and duplicate windows, and preserves missing or unusable inputs. [`research/evaluation.py`](research/evaluation.py) freezes one participant-level split across all comparisons, trains logistic-regression and random-forest candidates, selects by validation F1, and prepares grouped cross-validation, participant-level intervals, errors, ablations, environment and motion slices, duration summaries, confusion matrices, and ROC curves. [`research/run_study.py`](research/run_study.py) connects those stages for approved data and hashes every source file used by a run.

The psychologist marksheet supplies 20 behavioral ratings, session context, recording quality, and evidence timestamps. It does not supply the physiological and speech inputs needed for a PSYCON model. We can analyze the marksheets alone, but model training requires matching wrist and audio records with the same participant and session IDs.

See the complete [Week 5 implementation record](docs/WEEK_5_IMPLEMENTATION.md), [data handoff requirements](docs/research/DATA_REQUIREMENTS.md), and [research operating instructions](docs/research/README.md). Week 5 currently counts as implemented software and documentation with an open research exit gate.

### Week 6 validation and integration

Week 6 now has evidence-backed validation tooling, but it has not passed its physical exit gate. [`validation/evidence.py`](validation/evidence.py) records the operator, versions, conditions, measurements, artifacts, result, and corrective actions for each test. [`validation/stages.py`](validation/stages.py) enforces the five physical stages in order and rejects simulated evidence for physical passes. Templates cover build, electrical, runtime, assembly, and safety records.

[`validation/api_validation.py`](validation/api_validation.py) tests normal ingestion, duplicate delivery, corrupt CRC, missing audio, overrun reporting, sensor failure, communication loss, watchdog recovery, and safe shutdown against a live backend. It also checks processing, synchronization, features, inference/confidence, dashboard access, and research-export hashes. [`validation/stress.py`](validation/stress.py) supplies a timed simulated load runner, while [`validation/report.py`](validation/report.py) and [`validation/risk.py`](validation/risk.py) compile accepted evidence and keep unsupported gates and risks open.

The [Week 6 runbook](docs/validation/WEEK_6_RUNBOOK.md) defines calibration, assembly, electrical, runtime, safety, and end-to-end acceptance procedures. The [current test report](docs/validation/WEEK_6_TEST_REPORT.md) records that all physical gates remain blocked because no hardware measurements were supplied. A fresh live-stack Week 6 run is also pending because Docker Desktop was unavailable during this implementation; this does not invalidate the earlier Week 4 Compose result.

## Paper requirements versus implementation

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-1 physiological monitoring | Hardware/interfaces documented; firmware data are placeholders | Partial |
| FR-2 audio monitoring | Short-buffer I2S compiles; acoustic analysis, local transcription, language features, provenance, quality decisions, fixtures, and real/synthetic demos pass | Partial |
| FR-3 ambient light | TEMT6000 documented; no driver | Planned |
| FR-4 synchronization | Backend common-epoch offset/drift estimation is implemented and simulator-tested; physical clock measurements remain | Implemented in software |
| FR-5 communication | BLE notifications exist in both starters | Partial |
| FR-6 local processing | Basic audio features exist; failure isolation/logging do not | Partial |
| FR-7 independent modules | Separate projects exist; physical independence is untested | Partial |
| FR-8 expandability | Modular architecture is documented | Designed |
| Six-hour minimum runtime | No current, discharge, thermal, or continuous-run record | Not demonstrated |
| Week 6 validation controls | Evidence schema, ordered physical gates, failure scenarios, stress runner, report generator, risk mapping, and procedures exist | Implemented in software; physical gates open |
| Backend and research export | Flask API, PostgreSQL metadata, immutable S3-compatible objects, processing jobs, dashboard, hashed ZIP export, and backup verification pass the live Compose test | Implemented in software |
| Multimodal comparison | Participant-separated evaluation code exists; no psychologist marksheet dataset, matching PSYCON sessions, or real result | Partial |
| Competition demonstration | Written plan only | Not demonstrated |

## Repository layout

```text
PSYCON/
  main.py                         # WESAD experiment entrypoint
  ml/src/                         # Loading, preprocessing, features, models
  demo/                           # Deterministic local software demonstrations
  data/processed/                 # Checked-in feature table
  results/                        # Metrics, model exports, charts
  firmware/wrist/                 # Compiling wrist scaffold with placeholders
  firmware/ear/                   # Compiling I2S/BLE audio scaffold
  protocol/                       # TypeScript protocol and inference tests
  tests/                          # Python ML and firmware static tests
  validation/                     # Week 6 evidence, stage, scenario, stress, report, and risk tools
  paper/                          # Earlier short LaTeX scaffold
  docs/engineering_prd/           # Authoritative 34-chapter engineering PRD
  docs/SEVEN_WEEK_BUILD_PLAN.md   # Evidence-gated implementation plan
```

## Reproduce and verify

The clean-checkout expectations are maintained in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -m demo.audio_demo
python -m demo.audio_web_app
```

The web demo opens at `http://127.0.0.1:5000`; stop it with `Ctrl+C`. Set `PSYCON_PROFILE_KEY` to a random secret of at least 32 characters before enrollment, and supply `HF_TOKEN` after accepting the Community-1 model terms to enable real diarization. Python tests use deterministic model fakes, the synthetic demo writes a reproducible JSON decision report, and web tests exercise uploads and encrypted profile lifecycle without downloading gated models. Three raw-WESAD integration tests skip when `data/raw/wesad/S*/S*.pkl` is absent; after obtaining WESAD under its terms, place the files there and rerun `python main.py` and the tests.

The audio webpage automatically loads these values from the repository-root `.env` file without overriding variables already set in the PowerShell process. `.env` is ignored by Git. Paste a fine-grained Hugging Face read token into `HF_TOKEN`, keep the supplied profile key stable across restarts, and restart the webpage after changing either value.

```powershell
cd protocol
npm ci
npm test
npm run typecheck
cd ..
```

The protocol passes its TypeScript tests and type-checking with zero `npm audit` vulnerabilities. Python, TypeScript, and C++ consume the same canonical audio, wrist, and corrupt-CRC fixtures.

```powershell
python -m pip install platformio
python -m platformio run --project-dir firmware/ear
python -m platformio run --project-dir firmware/wrist
```

Both builds pass; flashing, serial logs, real readings, recordings, and duration tests remain physical work.

Run the Week 6 unit checks and, when Docker is running, the live scenario and timed simulated-load checks:

```powershell
python -m pytest tests/validation
docker compose up --build -d
python -m validation.api_validation --url http://localhost:8000
python -m validation.stress --url http://localhost:8000 --duration-seconds 3600
docker compose down
```

These commands validate software and the simulated transport path. They do not replace the physical one-hour stress, six-hour battery, calibration, electrical, GSR safety, assembly, or wearability records required by the [Week 6 runbook](docs/validation/WEEK_6_RUNBOOK.md).

## Safety, privacy, and study gate

Human recording requires the applicable ethics/school review, informed consent or guardian permission, withdrawal and deletion procedures, and a policy for bystander speech. Data handling must define pseudonymous IDs, access control, encryption, retention, deletion verification, backups, and version lineage.

Before worn use, verify battery polarity/protection, LiPo condition, rails, GSR excitation, insulation, strain relief, charging, brownout, component temperatures, and controlled shutdown. Do not charge while worn or while electrodes are attached until an electrical review approves the exact build.

## Next milestone and team

The evidence-gated implementation sequence is in [`docs/SEVEN_WEEK_BUILD_PLAN.md`](docs/SEVEN_WEEK_BUILD_PLAN.md).

| Member | Primary ownership |
| --- | --- |
| Arjun Vijay Prakash | Protocol, backend, synchronization, data management, ML evaluation, reproducibility, and software documentation |
| Saksham Yadav | Hardware, electrical safety, sensor integration, firmware, calibration, power/runtime, enclosure, and physical evidence |

An item is complete only when a repeatable test, measurement, log, dataset, or generated artifact proves it.
