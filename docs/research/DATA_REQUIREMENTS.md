# Data required before Week 5 evaluation

PSYCON has two separate Week 5 paths. The group-observation path is the one that matches the current marksheet. The earlier binary stress comparison in `research/evaluation.py` remains available for the wrist-and-speech study, and it cannot train 0–4 or N/O ratings as written.

## Group observation path

Marksheet version **4.0** scores items A–T as **0, 1, 2, 3, 4, or N/O**. A zero means the behaviour was not observed despite a fair opportunity. N/O means there was no fair opportunity, the recording cannot support a rating, or the speaker identity is uncertain. Do not convert N/O to zero, and do not turn a score into a diagnosis.

Each training row comes from one submitted marksheet for one participant slot in one group recording. It keeps:

- `group_session_id`, anonymous `participant_id`, and `rater_id`
- marksheet version, item letter, and the score or N/O
- evidence start and end, the context note, and baseline and trigger intervals for items Q–T
- recording quality and the source recording SHA-256

The whole group session stays in one data split. If the same anonymous research code appears in another session, those sessions stay in that split too. Model predictions are stored separately and never replace the psychologist's rating. A paper PDF may be attached to a slot for review, but its text is not a training label.

Consent version `group-consent-2.0` has to cover the video, the extracted audio, transcription, model training, access, retention, and withdrawal before a session can enter a training export. Names and signatures stay on the restricted consent record.

There is no empirical group-observation result until approved sessions and completed ratings pass that export and a held-out evaluation says which items had enough evidence.

## Earlier device-study path

The binary comparison still expects matched wrist and speech features for one participant per device session. Its label is not the marksheet. Completed marksheets alone do not train that comparison. A shared table microphone does not attribute physiology to one person; a later wrist study needs its own wearer mapping and protocol.

If more than one psychologist rates the same device session, keep every rating as a separate row with an anonymous rater code. Do not average ratings until the scoring policy is frozen. Marksheet scores can support behavioural prediction. They cannot become a depression, anxiety, PTSD, or other diagnostic label.

## What the device session must provide

Each marksheet row needs a matching `participant_id` and `session_id` in the device data. The minimum device package is:

- Wrist data with PPG or BVP, EDA or GSR, temperature, acceleration, acquisition timestamps, sequence numbers, units, sample rates, quality flags, and contact or saturation states
- Audio data or approved derived speech features with timestamps, capture status, clipping and noise quality, transcription status, and speaker attribution when the protocol permits it
- Ambient-light and motion context aligned to the same clock
- Firmware and hardware versions, calibration record IDs, battery values, sensor status, synchronization uncertainty, and error logs
- Session start and stop records, stop reason, raw-file hashes, and consent state for each processed modality

The clock alignment must be good enough to connect a marksheet evidence timestamp with the relevant sensor and speech window. A session total with no timestamps can support session-level analysis, but it cannot support claims about moment-to-moment behavior.

## What marksheets alone can support

With only completed marksheets, the project can calculate score distributions, missingness, domain correlations, rater agreement, and differences across recorded session conditions. The group-observation model also needs the shared recording, seat map, and reviewed speaker map. Marksheets alone do not train the earlier wrist-and-speech comparison.

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

