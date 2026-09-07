# Data required before Week 5 evaluation

PSYCON currently has no real Week 5 training dataset. Completed psychologist marksheets can provide reference observations, but training a model that predicts from the wearable and audio modules also requires the matching timestamped device recordings. Results will be generated only after these sources are joined and validated.

## What the marksheet provides

For each participant and session, provide the following fields in CSV or XLSX form:

- Anonymous participant code and session ID
- Observation start time or duration, psychologist or rater code, session number, and language
- Room, seating layout, discussion topic, background-noise score, recording-quality score, and structured session-event codes
- Scores from `A` through `T`, each recorded as `1` through `5` or blank for `N/O`
- Evidence timestamps where available, especially when a score depends on a specific speaking turn or event
- Completion status and any protocol-approved exclusion reason

Do not convert `N/O` to zero or one. It means the rater lacked enough evidence, so the analysis must treat it as missing. Keep names, phone numbers, email addresses, dates of birth, signatures, and unrestricted free-text notes out of the analytical dataset.

If more than one psychologist rates the same session, keep every rating as a separate row with an anonymous rater code. This allows agreement analysis before choosing a consensus or aggregate label. Do not average ratings until the scoring policy is frozen.

The existing marksheet covers 20 observable behavioral domains. It explicitly avoids mental-health diagnosis, so its scores can support behavioral prediction or association analysis but cannot become a depression, anxiety, PTSD, or other diagnostic label.

## What the device session must provide

Each marksheet row needs a matching `participant_id` and `session_id` in the device data. The minimum device package is:

- Wrist data with PPG or BVP, EDA or GSR, temperature, acceleration, acquisition timestamps, sequence numbers, units, sample rates, quality flags, and contact or saturation states
- Audio data or approved derived speech features with timestamps, capture status, clipping and noise quality, transcription status, and speaker attribution when the protocol permits it
- Ambient-light and motion context aligned to the same clock
- Firmware and hardware versions, calibration record IDs, battery values, sensor status, synchronization uncertainty, and error logs
- Session start and stop records, stop reason, raw-file hashes, and consent state for each processed modality

The clock alignment must be good enough to connect a marksheet evidence timestamp with the relevant sensor and speech window. A session total with no timestamps can support session-level analysis, but it cannot support claims about moment-to-moment behavior.

## What marksheets alone can support

With only completed marksheets, the project can calculate score distributions, missingness, domain correlations, internal consistency where appropriate, rater agreement when repeated ratings exist, and differences across recorded session conditions. It cannot train or validate a model that takes PSYCON sensor or audio features as input.

If the goal is only to digitize or summarize psychologist observations, the marksheets may be sufficient. If the goal is to demonstrate that PSYCON predicts those observations, the matching device recordings are required.

## Preferred delivery layout

```text
handoff/
  marksheets.xlsx
  metadata/
    sessions.json
    calibrations.json
  wrist/
    SESSION-ID.csv
  audio/
    SESSION-ID.wav
  context/
    SESSION-ID.csv
  logs/
    SESSION-ID.jsonl
```

Before sending data, replace names with random participant codes and keep the identity key elsewhere. Confirm that consent covers physiological recording, audio, transcription, intended analysis, retention, and access. If raw audio cannot be shared, provide approved acoustic and conversation features with their extraction version and time windows.

## Work performed after delivery

1. Validate consent, anonymity, eligibility, schema, files, hashes, timestamps, and calibration references.
2. Audit missingness, corruption, class and score coverage, rater agreement, session counts, and participant counts.
3. Agree with the psychologist on the prediction target and treatment of `N/O`, repeated ratings, evidence timestamps, and exclusions.
4. Synchronize marksheet targets with physiology, speech, light, motion, quality, and error records.
5. Freeze participant-level splits and the analysis plan before evaluating the test participants.
6. Train physiology-only, speech-only, and combined candidates, then report confidence intervals, errors, ablations, environment and motion effects, duration stability, and limitations.

Until those steps finish, Week 5 has an implemented pipeline and no empirical result.

