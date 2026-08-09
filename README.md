# PSYCON: Psychological Condition Monitoring System

PSYCON is a two-module wearable research prototype for studying whether synchronized physiological, environmental, and speech-derived signals can estimate indicators associated with psychological well-being. The Wrist Module measures PPG, EDA/GSR, temperature, and motion; the Audio Module captures speech and ambient light. The intended experiment compares physiology-only, speech-only, and combined multimodal inference.

PSYCON is a research and screening prototype, not a medical device. It must not be presented as diagnosing depression, anxiety, PTSD, ADHD, autism, stress disorders, or any other clinical condition.

## Current completion

**Overall project completion: 49% as of 9 August 2026.** This weighted estimate measures progress toward the PRD's competition-ready integrated prototype. It does not count completed software, documentation, or generated-speech tests as completed hardware.

| Workstream | Weight | Completion | Contribution | Evidence and remaining gap |
| --- | ---: | ---: | ---: | --- |
| Requirements and engineering documentation | 15% | 95% | 14.25% | The tracked 34-chapter PRD, current PDF, reproducibility matrix, protocol specification, device-feature contract, and complete audio/transcription/language contract are present. Verified bibliography sources and completed physical records remain open. |
| Hardware, electrical, and mechanical | 20% | 35% | 7.0% | Components and wiring are documented and reported as individually checked. There is no repository evidence of an integrated wearable, calibrated GSR front end, measured rails/current/temperature, enclosure, or runtime test. |
| Device firmware and acquisition | 20% | 30% | 6.0% | Both firmware targets compile. Audio I2S/BLE and wrist I2C/BLE bring-up exist, but wrist values are placeholders and continuous sensing, quality, storage, recovery, power, and watchdog behavior are absent. |
| Protocol, backend, and synchronization | 15% | 34% | 5.1% | Protocol v2 has shared fixtures and Python, TypeScript, and C++ conformance tests; normalized wrist/session/quality/calibration schemas and audio packet provenance are implemented. The backend and synchronization service remain absent. |
| Data science and research pipeline | 15% | 78% | 11.7% | WESAD processing/results, a hardware-compatible wrist converter, deterministic acoustic analysis, local timestamped transcription, and English language/conversation features exist. Recorded participant speech, hardware data, fusion, repeated validation, confidence intervals, and external validation remain. |
| Verification, safety, and release evidence | 15% | 35% | 5.25% | Repository checks, dependency audit, fixture conformance, firmware builds, PRD compilation, audio quality fixtures, webpage tests, and an actual local-model transcription test pass. Physical calibration, runtime, safety, and device demonstration evidence remain. |
| **Total** | **100%** |  | **49.30% ≈ 49%** | Week 1 through Week 3 software are complete. Physical Wrist/Audio integration and the Week 4 backend are the next critical path. |

The narrower end-to-end functional prototype is roughly **21% complete** because real sensor acquisition, synchronized backend sessions, power evidence, and multimodal validation are still absent. The 49% overall figure gives reusable credit to the specification, verified software contracts, firmware scaffolds, WESAD pipeline, device converters, deterministic audio analysis, local transcription/language features, and generated results.

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

[`protocol/`](protocol/) contains the Protocol v2 byte contract, shared binary fixtures, Python and TypeScript decoders, a C++ header, normalized wrist/session/quality/calibration types, validation, and logistic-regression inference. Cross-language fixture tests, Vitest, and `tsc --noEmit` pass; the backend transport and synchronized session service remain unimplemented.

### Audio analysis

[`ml/src/audio.py`](ml/src/audio.py) decodes Protocol v2 PCM16 packets with the `psycon_audio` extractor for quality, dBFS, pitch statistics, voice stability, prosody, spectral, and timing features. It preserves packet hashes and sample lineage and returns explicit `usable`, `insufficient_audio`, `clipped`, `too_noisy`, `corrupt`, or `missing_audio` states before inference.

[`ml/src/transcription.py`](ml/src/transcription.py) now quality-gates and transcribes consented usable regions locally with timestamped segments, language detection, confidence, source-sample offsets, and explicit no-speech, skipped-quality, unavailable, and failed states. [`ml/src/language_features.py`](ml/src/language_features.py) implements the English baseline for vocabulary diversity, sentence length, sentiment, emotion-related word counts, topic transitions, speech duration, pauses, and speaking rate. Unsupported languages abstain from language features, and speaker diarization is not claimed.

[`demo/audio_demo.py`](demo/audio_demo.py) processes deterministic generated fixtures and writes [`results/demo/audio_demo.json`](results/demo/audio_demo.json). This proves the software path and abstention behavior without using personal recordings; it does not prove the INMP441, TEMT6000, continuous DMA, placement, clock, or transport behavior.

[`demo/audio_web_app.py`](demo/audio_web_app.py) provides a local upload page for consented PCM or floating-point WAV recordings. It keeps the upload in memory, downmixes and resamples it to mono 16 kHz PCM16, analyzes balanced Protocol v2 windows of at most two seconds, transcribes accepted regions with a local faster-whisper model, and displays quality, timestamped text, language features, and provenance. It does not send recordings to a transcription API or make a psychological inference.

### WESAD baseline

[`main.py`](main.py) runs WESAD loading, resampling, overlapping 10-second windows, wrist feature extraction, subject-group train/test splitting, five model families, and artifact generation.

The checked-in processed table contains **13,698 windows from 15 subjects**: 8,760 calm and 4,938 high-stress. The best recorded accuracy is 0.932 for EDA XGBoost; the exported multimodal-wrist logistic run records 0.915 accuracy, 0.895 F1, 0.995 recall, and 0.130 false-positive rate on one grouped holdout. These are WESAD development results, not PSYCON hardware or clinical validation.

There is no recorded-speech dataset, synchronized device dataset, physiology/audio/fusion ablation, repeated group validation, confidence interval, or external validation. Raw WESAD pickles are absent, so preprocessing cannot be reproduced from a clean checkout without separately obtaining WESAD.

## Paper requirements versus implementation

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-1 physiological monitoring | Hardware/interfaces documented; firmware data are placeholders | Partial |
| FR-2 audio monitoring | Short-buffer I2S compiles; acoustic analysis, local transcription, language features, provenance, quality decisions, fixtures, and real/synthetic demos pass | Partial |
| FR-3 ambient light | TEMT6000 documented; no driver | Planned |
| FR-4 synchronization | Timestamp fields designed; no common epoch or drift correction | Planned |
| FR-5 communication | BLE notifications exist in both starters | Partial |
| FR-6 local processing | Basic audio features exist; failure isolation/logging do not | Partial |
| FR-7 independent modules | Separate projects exist; physical independence is untested | Partial |
| FR-8 expandability | Modular architecture is documented | Designed |
| Six-hour minimum runtime | No current, discharge, thermal, or continuous-run record | Not demonstrated |
| Backend and research export | Architecture only; no `server/` implementation | Not implemented |
| Multimodal comparison | Wrist-only WESAD baseline; no speech or fusion result | Partial |
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

The web demo opens at `http://127.0.0.1:5000`; stop it with `Ctrl+C`. Python currently passes all repository-safe tests, the synthetic demo writes a reproducible JSON decision report, and web tests exercise valid and invalid real-WAV uploads. Three raw-WESAD integration tests skip when `data/raw/wesad/S*/S*.pkl` is absent; after obtaining WESAD under its terms, place the files there and rerun `python main.py` and the tests.

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
