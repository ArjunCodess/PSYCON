# PSYCON model card

## Release status

The checked-in model is `psycon_wesad_logistic_multimodal` version `0.1.0`. It is a WESAD development artifact, not a PSYCON student-discussion model. Do not use it for diagnosis, treatment, discipline, grading, selection, or unsupervised participant assessment.

## Intended use

The artifact demonstrates the software path for binary calm versus high-stress inference from WESAD-derived Wrist features. Its supported use is engineering replay and interface development. It does not support claims about the current PSYCON hardware, group discussions, children, a specific school, audio stress, the psychologist marksheet, or clinical conditions.

## Inputs and output

The model expects 36 named features derived from EDA, BVP, motion, temperature, and participant-baseline differences. `results/app_model.json` stores the feature order, standardization parameters, linear coefficients, intercept, class mapping, and presentation thresholds. The backend validates the feature contract before inference.

The binary classes are `calm` and `high_stress` according to the WESAD experimental labels. Display terms such as `mild_stress` are interface bands on the model probability, not independently validated clinical categories.

## Training and evaluation record

`main.py` loads WESAD subject data, resamples signals, creates overlapping 10-second windows, extracts features, and separates subjects between training and test data. The checked-in processed table has 13,698 windows from 15 subjects, with 8,760 calm and 4,938 high-stress windows.

The exported logistic artifact records 0.915 accuracy, 0.895 F1, 0.995 recall, 0.814 precision, and 0.130 false-positive rate on one grouped holdout. The best row in `results/metrics.json` is EDA XGBoost at 0.932 accuracy. These figures are development results from one small public dataset and do not establish external validity.

## Quality and abstention

The backend records feature quality and confidence. Audio analysis can return missing, corrupt, clipped, noisy, insufficient-audio, unavailable-transcription, unknown-speaker, and related abstention states. A model output must remain unavailable when required inputs, feature versions, or quality criteria fail.

## Known limitations

- WESAD has 15 subjects and controlled laboratory tasks, so it does not represent the intended discussion setting.
- The exported artifact uses Wrist features only despite the historical `multimodal` name; it does not contain speech features.
- The current Wrist firmware emits placeholder sensor values and cannot produce valid model inputs.
- No psychologist marksheet has been joined to matching PSYCON recordings.
- No calibration, six-hour runtime, physical end-to-end, subgroup, school-site, or external-dataset result exists for PSYCON.
- Probability thresholds and labels need a new frozen target definition, calibration analysis, and approval before participant use.

## Required replacement study

Use anonymous approved sessions, matching marksheets and device data, a psychologist-approved target, participant-level splits, grouped nested validation, participant-bootstrap confidence intervals, missingness and context slices, physiology-only and speech-only baselines, combined-model ablation, calibration, error review, and an untouched external site. Publish negative results and abstention coverage. Rotate the single Wrist set across focal participants rather than treating center audio as physiology for everyone.

## Version and rollback

`release_tools/versions.json` freezes this artifact as `wesad-development-0.1.0`. Any dataset, label, feature, preprocessing, threshold, coefficient, or dependency change requires a new model and dataset version. Preserve the old artifact, manifest, metrics, split, and code revision for rollback.
