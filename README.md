# Psycon: Multimodal Psychological State Detection Wearable System

Psycon is a dual-module wearable and mobile software system for estimating calm, mild stress, and high stress using multimodal physiological, motion, and audio-derived signals.

## Current Direction

The first software milestone is to validate the data and machine learning pipeline using the public WESAD dataset. After IRB guidance, the same pipeline will be adapted for data collected from the Psycon hardware.

This keeps the project moving before human participant data collection begins, while still preserving the final goal: a real-time wearable system that runs on Psycon's own wrist and ear modules.

## What We Are Building

- Wrist module: collects physiological and motion signals from the biosensing hardware.
- Ear/audio module: captures or derives audio features during trigger-based recording windows.
- Mobile app: connects to both modules, synchronizes data, runs inference, visualizes signals, and stores sessions.
- Offline ML pipeline: loads data, preprocesses signals, extracts features, trains models, and evaluates results.
- Protocol layer: defines shared packet formats and data contracts across firmware, mobile, and ML code.
- Research outputs: charts, metrics, model comparisons, and paper artifacts.

## Research Question

Can multimodal sensing improve stress detection accuracy compared to single-modality systems?

The working hypothesis is that combining physiological, behavioral, and audio-derived features can reduce false positives and improve robustness compared with single-sensor stress detection.

## Product Requirements Summary

Psycon is designed as a hybrid multimodal human-state inference system. The target states are:

| Score | State |
| --- | --- |
| 0.0-0.3 | Calm |
| 0.3-0.6 | Mild Stress |
| 0.6-1.0 | High Stress |

The intended processing flow is:

```text
Sensors
-> Data synchronization
-> Preprocessing
-> Feature extraction
-> Sub-models
-> Fusion model
-> Post-processing
-> Stress output
-> Storage
```

Core software requirements:

- Dual BLE connectivity for wrist and ear modules.
- Real-time dashboard for heart rate, GSR, motion, audio activity, and stress level.
- Local event logging with timestamps.
- Stress visualization graphs.
- Data synchronization with packet loss and delay handling.
- Moving-average filtering, outlier removal, missing-value handling, and per-user normalization.
- Sliding-window feature extraction over 3-5 second windows.
- Lightweight on-device inference with target latency under 2 seconds.
- SQLite-based local storage for raw signals, features, labels, and predictions.
- Labeling interface for research sessions.
- Debug dashboard for raw signals, feature trends, and model outputs.
- Power-aware processing with adaptive sampling and trigger-based audio.

## Locked MVP Hardware

### Module 1: Biosensing Wrist Module

- ESP32-WROOM-32E dev board
- MAX30102
- MPU6050
- ADS1115
- GSR electrodes
- RC filter
- TP4056
- MCP1700
- LiPo battery

### Module 2: Audio Module

- ESP32-WROOM-32E
- INMP441
- TP4056
- LiPo battery

### Important Hardware Note

The original PRD mentions ESP32-S3, MLX90614, and BH1750. The locked MVP hardware is ESP32-WROOM-32E and does not include temperature or ambient-light sensing unless those sensors are added later.

## Wiring Notes

### Power

- Battery positive to TP4056 `B+`.
- Battery negative to TP4056 `B-`.
- TP4056 `OUT+` to ESP32 `5V`.
- TP4056 `OUT-` to ESP32 `GND`.
- MCP1700 is for clean sensor power only:
  - `IN` to ESP32 `5V`
  - `GND` to common ground
  - `OUT` to clean `3.3V` for sensors
  - Add `1uF` capacitor between `IN` and `GND`
  - Add `1uF` capacitor between `OUT` and `GND`

### Wrist I2C Bus

ESP32 pins:

- `GPIO21` -> SDA
- `GPIO22` -> SCL

Shared I2C devices:

| Device | SDA | SCL | VCC | GND |
| --- | --- | --- | --- | --- |
| MAX30102 | GPIO21 | GPIO22 | 3.3V | GND |
| MPU6050 | GPIO21 | GPIO22 | 3.3V | GND |
| ADS1115 | GPIO21 | GPIO22 | 3.3V | GND |

Additional wiring:

- MAX30102 `INT` is not connected for MVP.
- MPU6050 `AD0` to `GND`.
- ADS1115 `ADDR` to `GND`, using address `0x48`.
- ADS1115 `A0` reads the GSR signal.

### GSR Circuit

```text
3.3V --[100k resistor]---*------ Electrode 1
                         |
                         +------ ADS1115 A0
                         |
                       [0.1uF]
                         |
                        GND
                         |
                   Electrode 2
```

The `100k` resistor creates the voltage divider, skin resistance changes the measured voltage, and the `0.1uF` capacitor reduces noise.

### Ear Audio Module

INMP441 I2S wiring:

| INMP441 Pin | ESP32 Pin |
| --- | --- |
| VCC | 3.3V |
| GND | GND |
| WS | GPIO25 |
| SCK | GPIO26 |
| SD | GPIO33 |
| L/R | GND |

### Hardware Failure Points

- Do not power the ESP32 from the MCP1700.
- Keep common ground within each module.
- Check battery polarity before powering on.
- Do not swap SDA/SCL.
- Use the `100k` resistor and `0.1uF` capacitor in the GSR circuit.
- Keep electrode contact firm.
- Avoid loose wires because they produce noisy readings.

## Software Architecture

The software system is split into these layers:

1. Data loading and acquisition
   - WESAD dataset loading for initial research.
   - BLE packet ingestion from Psycon hardware later.
2. Synchronization
   - Phone acts as central clock for hardware sessions.
   - Packets include timestamps and sequence numbers.
   - Streams are aligned into time-consistent windows.
3. Preprocessing
   - Filtering, outlier removal, missing-value handling, and baseline normalization.
4. Feature extraction
   - Heart-rate deviation, GSR level, GSR slope, motion intensity, jerk, audio energy, pitch proxy, and zero-crossing rate.
5. Modeling
   - Rule-based baseline first.
   - Classical ML next: logistic regression, random forest, and XGBoost.
   - Compare single-modality models against multimodal fusion.
6. Mobile inference
   - Lightweight model execution in the app.
   - Target inference latency under 2 seconds.
7. Storage and visualization
   - Local SQLite storage in the mobile app.
   - Charts and result artifacts saved under `results/`.
8. Research evaluation
   - Accuracy, precision, recall, false-positive rate, confusion matrix, and stability over time.

## Folder Structure

```text
psycon/
  README.md
  ml/
  mobile/
  firmware/
    wrist/
    ear/
  protocol/
  data/
    raw/
    processed/
  results/
    charts/
  tests/
  paper/
    main.tex
    references.bib
```

- `ml/`: main code files and folders for offline ML, preprocessing, feature extraction, training, and evaluation.
- `mobile/`: React Native mobile app code.
- `firmware/wrist/`: ESP32 wrist module firmware.
- `firmware/ear/`: ESP32 ear/audio module firmware.
- `protocol/`: shared data contracts, packet formats, and schema notes.
- `data/raw/`: raw datasets, including WESAD and future Psycon session exports.
- `data/processed/`: cleaned, synchronized, windowed, and feature-ready datasets.
- `results/`: metrics, model outputs, generated reports, and experiment artifacts.
- `results/charts/`: generated visualizations and plots.
- `tests/`: tests for ML, protocol, mobile-independent logic, and data processing.
- `paper/`: research paper source, generated PDF, and bibliography.

## Decisions Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-05-24 | Use WESAD-first pipeline for initial ML validation. | It lets the software and research pipeline start before human participant data collection. |
| 2026-05-24 | Contact IRB at `IRBassist@isb.edu` before participant data collection. | Human participant physiological and stress data requires proper ethics guidance before collection. |
| 2026-05-24 | Plan the mobile app in React Native + TypeScript. | One codebase can support Android-first hardware testing while keeping an iOS path open. |
| 2026-05-24 | Use BLE as the phone communication path. | Phones do not directly support ESP-NOW; BLE is the practical phone-to-ESP32 path. |
| 2026-05-24 | Do not use ESP-NOW for phone communication. | ESP-NOW can be used only between ESP32 devices if needed, not between phone and modules. |
| 2026-05-24 | Ear module sends audio features for MVP, not continuous raw audio. | Feature packets are lower bandwidth and better for privacy than raw audio streaming. |
| 2026-05-24 | Start with rule-based baseline plus classical ML before deep learning. | Small datasets and ISEF-style evaluation are better served by interpretable baselines first. |

## Privacy And Safety

- Psycon is a research prototype, not a medical diagnostic device.
- No medical diagnosis claims should be made from the output.
- Human participant data collection must wait for IRB response, exemption, or approval.
- Data collection should be local-first where possible.
- Audio collection should be minimized.
- The MVP should prefer audio features over continuous raw audio.
- Participants should understand what is collected, why it is collected, and how it is stored before any future study.

## Target Outputs

- Clean WESAD loading and preprocessing pipeline.
- Baseline rule-based stress score.
- Classical ML models for stress classification.
- Single-modality vs multimodal comparison results.
- Charts and evaluation metrics.
- App-ready inference artifacts.
- Mobile dashboard and local data logger.
- Wrist and ear firmware for the locked hardware.
- Research paper assets in `paper/`.

