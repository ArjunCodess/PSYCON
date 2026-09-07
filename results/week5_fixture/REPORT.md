# Week 5 fixture evaluation

This report verifies the research software with deterministic synthetic records. It does not contain participant or hardware data, does not satisfy external validation, and does not support a clinical claim.

## Versions and split

- Dataset: `week5-fixture-1.0.0`
- Model run: `week5-fixture-model-1.0.0`
- Participant assignment hash: `6f8d0a1cb9508ec205280e603b7ff7a2c0fcc613fd7bfc697e64252ca6729e9f`
- Participants by split: `{'test': 3, 'train': 9, 'validation': 3}`

Every modality used the same participant assignment. Preprocessing and model selection stayed inside the development participants, and the test participants were evaluated after selection.

## Test comparison

| Modality | Selected model | Accuracy | Precision | Recall | F1 | ROC-AUC | F1 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| physiology | logistic_regression | 0.889 | 0.818 | 1.000 | 0.900 | 0.988 | 0.857 to 1.000 |
| speech | logistic_regression | 0.944 | 1.000 | 0.889 | 0.941 | 0.994 | 0.909 to 1.000 |
| combined | random_forest | 0.972 | 0.947 | 1.000 | 0.973 | 1.000 | 0.923 to 1.000 |

The combined-minus-physiology F1 difference is 0.073; the combined-minus-speech difference is 0.032. These fixture differences verify the ablation calculation and say nothing about real multimodal benefit.

## Data quality and analysis coverage

The run contains 180 windows from 15 synthetic participants. It preserves 39 windows with a missing or bad modality. The machine-readable report contains candidate validation metrics, grouped cross-validation scores, confusion matrices, false-positive and false-negative counts, participant-level bootstrap intervals, environment slices, motion slices, and 10, 30, and 60 second duration summaries.

## Open gates

External validation remains blocked because no separate compatible dataset was supplied. Approved participant collection remains blocked by ethics approval, consent, physical calibration, and the earlier hardware safety gates. The duration analysis is descriptive until the approved protocol freezes its stability tolerance.

## Limitations

- Outputs are research indicators and are not clinical diagnoses.
- Performance on fixture or public data does not validate PSYCON hardware or a target participant population.
- Context slices are descriptive and may be unreliable when participant or class counts are small.
