# PSYCON: Psychophysiological Condition Observation Network

PSYCON stands for **Psychophysiological Condition Observation Network**. It is a dual-module wearable and mobile software system for estimating calm, mild stress, and high stress using multimodal physiological, motion, and audio-derived signals.

## Current Direction

The first software milestone is to validate the data and machine learning pipeline using the public WESAD dataset. After IRB guidance, the same pipeline will be adapted for data collected from the PSYCON hardware.

This keeps the project moving before human participant data collection begins, while still preserving the final goal: a real-time wearable system that runs on PSYCON's own wrist and ear modules.

The current implementation phase intentionally skips the mobile app. The active software work is the WESAD-first ML pipeline, shared protocol types, firmware starter projects, generated research results, and paper scaffolding.

After IRB approval or official guidance, the main research goal becomes personalization: PSYCON should learn each user's normal physiological baseline and evaluate stress as deviation from that baseline, not as raw sensor values.

## What We Are Building

- Wrist module: collects physiological and motion signals from the biosensing hardware.
- Ear/audio module: captures or derives audio features during trigger-based recording windows.
- Mobile app: planned later; it will connect to both modules, synchronize data, run inference, visualize signals, and store sessions.
- Offline ML pipeline: loads data, preprocesses signals, extracts features, trains models, and evaluates results.
- Protocol layer: defines shared packet formats and data contracts across firmware, mobile, and ML code.
- Research outputs: charts, metrics, model comparisons, and paper artifacts.

## Research Question

Can multimodal sensing improve stress detection accuracy compared to single-modality systems?

The working hypothesis is that combining physiological, behavioral, and audio-derived features can reduce false positives and improve robustness compared with single-sensor stress detection.

## Product Requirements Summary

PSYCON is designed as a hybrid multimodal human-state inference system. The target states are:

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
- Sliding-window feature extraction over 10-30 second windows, updating every 2-5 seconds.
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
   - WESAD `.pkl` files are the current source of truth because they include aligned signals and labels.
   - BLE packet ingestion from PSYCON hardware later.
2. Synchronization
   - Phone acts as central clock for hardware sessions.
   - Packets include timestamps and sequence numbers.
   - Streams are aligned into time-consistent windows.
3. Preprocessing
   - Filtering, outlier removal, missing-value handling, and baseline normalization.
4. Feature extraction
   - Mean HR/BVP, HR variation proxy, GSR level, GSR slope, GSR peak count, temperature change, motion intensity, jerk, audio energy, pitch proxy, and zero-crossing rate.
5. Modeling
   - Rule-based baseline first.
   - Classical ML next: logistic regression, random forest, XGBoost, and LightGBM.
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
  main.py
  README.md
  ml/
    src/
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

- `main.py`: one-command reproducible entrypoint for the current WESAD ML pipeline.
- `ml/`: offline ML code for preprocessing, feature extraction, training, and evaluation.
- `ml/src/`: Python source modules for the ML pipeline.
- `mobile/`: React Native mobile app code.
- `firmware/wrist/`: ESP32 wrist module firmware.
- `firmware/ear/`: ESP32 ear/audio module firmware.
- `protocol/`: shared data contracts, packet formats, schema notes, and its own TypeScript tooling.
- `data/raw/`: raw datasets, including WESAD and future PSYCON session exports.
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
| 2026-05-24 | Do not implement mobile in the current phase. | The immediate goal is to finish WESAD-first research software, protocol code, and firmware starters. |
| 2026-05-24 | Use WESAD `.pkl` files as the ML source of truth. | Pickle files contain the aligned signals and labels needed for reproducible training. |
| 2026-05-24 | Keep raw WESAD data local and ignored by Git. | The dataset is large and should not be committed to the repository. |
| 2026-05-24 | Use root `main.py` as the single reproducible command. | Running `python main.py` should execute the current end-to-end software pipeline. |
| 2026-05-24 | Keep subsystem tooling inside subsystem folders. | Protocol TypeScript tooling belongs under `protocol/`, not the repository root. |
| 2026-05-25 | Define PSYCON as Psychophysiological Condition Observation Network. | The acronym now reflects the actual project identity. |
| 2026-05-25 | Capitalize PSYCON in project-facing docs and paper. | It is an acronym and reads more clearly in research materials. |
| 2026-05-25 | Use 10-second windows with 2-second updates in the current pipeline. | This better matches wearable stress-detection windows than very short 5-second windows. |
| 2026-05-25 | Add baseline-normalized features to the ML pipeline. | Personalized deviation from each user's calm baseline is central to the post-IRB system. |

## Personalization And First-Wear Routine

The most important post-approval improvement is personalization. PSYCON should not depend only on raw sensor values because every person has a different normal heart rate, GSR level, skin temperature, and motion pattern.

The target runtime pipeline is:

```text
Sensors -> Window -> Feature extraction -> Baseline normalization -> ML model -> Stress output
```

### First-Wear Baseline Routine

After IRB approval or formal confirmation that the planned procedure is allowed, each new user should complete a first-wear routine:

1. Seated calm baseline: sit relaxed for 2-5 minutes.
2. Normal movement baseline: walk normally for 1-2 minutes.
3. Higher-motion baseline: short safe run or brisk movement only if appropriate and approved.
4. Optional labeled task sessions: collect approved relaxed and stressed labels for personal model training.

The goal is not to diagnose stress. The goal is to learn the user's normal physiological range so later predictions can use relative features:

```text
hr_diff = current_hr - baseline_hr
gsr_diff = current_gsr - baseline_gsr
temp_diff = current_temp - baseline_temp
motion_diff = current_motion - baseline_motion
```

The baseline can adapt slowly over time:

```text
baseline = 0.95 * old_baseline + 0.05 * new_calm_observation
```

This is the line we should be able to defend in judging:

> Unlike generic models, PSYCON calibrates to each individual's physiological baseline, improving robustness in real-world scenarios.

### Current Code Support

The current WESAD pipeline already includes the software foundation for this idea:

- WESAD windows are now 10 seconds long with a 2-second hop.
- GSR peak count and signal change features are extracted.
- Per-subject calm baselines are computed from WESAD baseline segments.
- Baseline-difference features are added before model training.

Future PSYCON hardware sessions should use the same pattern with the user's first-wear baseline instead of WESAD's baseline labels.

## Privacy And Safety

- PSYCON is a research prototype, not a medical diagnostic device.
- No medical diagnosis claims should be made from the output.
- Human participant data collection must wait for IRB response, exemption, or approval.
- Data collection should be local-first where possible.
- Audio collection should be minimized.
- The MVP should prefer audio features over continuous raw audio.
- Participants should understand what is collected, why it is collected, and how it is stored before any future study.

## Target Outputs

- Clean WESAD loading and preprocessing pipeline.
- Baseline rule-based stress score.
- Classical ML models for stress classification, including logistic regression, random forest, XGBoost, and LightGBM.
- Single-modality vs multimodal comparison results.
- Charts and evaluation metrics.
- App-ready inference artifacts.
- Mobile dashboard and local data logger later.
- Wrist and ear firmware for the locked hardware.
- Research paper assets in `paper/`.

## Running The Current Software

Run the full reproducible pipeline from the repository root:

```powershell
python main.py
```

This reads WESAD `.pkl` files from `data/raw/wesad/`, writes processed features to `data/processed/`, trains/evaluates models, and writes metrics, charts, and app-model artifacts to `results/`.

The command also prints a terminal summary of:

- discovered WESAD subjects
- labeled window counts
- class balance
- best model results
- generated artifact paths

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Run Python tests:

```powershell
python -m pytest
```

Run a one-subject WESAD smoke test:

```powershell
python main.py --limit-subjects 1
```

Install TypeScript dependencies and run protocol tests:

```powershell
cd protocol
npm install
npm test
npm run typecheck
cd ..
```

Firmware note: PlatformIO is still the intended build tool for `firmware/wrist` and `firmware/ear`. The repository includes `.vscode/c_cpp_properties.json` so the C/C++ extension can find ESP32 Arduino headers after PlatformIO installs the framework packages.

Install PlatformIO when you are ready to build firmware:

```powershell
pip install platformio
cd firmware\wrist
platformio run
cd ..\ear
platformio run
cd ..\.. 
```

## Team And Contributions

PSYCON is being built by two Grade 11 high school students from **City Montessori School, Quality Building, Sector G, LDA Colony, Kanpur Road, Lucknow, Uttar Pradesh 226012, India**.

| Member | Contribution |
| --- | --- |
| **Arjun Vijay Prakash** | Software, ML pipeline, protocol, reproducible results, and paper software methods. |
| **Saksham Yadav** | Hardware design, wiring, biosensing module, audio module, and physical wearable implementation. |
