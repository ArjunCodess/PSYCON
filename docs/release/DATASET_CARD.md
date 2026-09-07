# PSYCON dataset card

## Current datasets

The repository contains one processed public-development table, `data/processed/wesad_features.csv`. It does not contain raw WESAD files, completed psychologist marksheets in the analytical schema, matching PSYCON Wrist and Audio sessions, or an external-validation dataset.

The processed WESAD table has 13,698 overlapping 10-second windows from 15 subjects. There are 8,760 calm and 4,938 high-stress windows. The source protocol contains chest and Wrist physiological signals plus self-reports under baseline, stress, and amusement conditions. PSYCON's current pipeline uses the documented subset and mapping in `ml/src/wesad.py` and `main.py`.

## Allowed use

Use the table to reproduce development experiments and test software. Follow the WESAD authors' licensing and citation terms. Do not treat its windows as independent people, infer student-discussion performance, or use the checked-in artifact for clinical or disciplinary decisions.

## Reproducibility limit

Raw WESAD subject pickles are licensed external files and are not committed. A clean checkout can test deterministic preprocessing units, but it cannot recreate `wesad_features.csv` from source until the researcher obtains WESAD and places its subject files under `data/raw/wesad/`.

## Intended PSYCON dataset

Each study row needs an anonymous participant ID, session ID, rater record, 20 behavioural domain values with `N/O` preserved as missing, evidence timestamps, discussion context, approved momentary stress label when stress is the research target, and matching synchronized device data. Wrist records need PPG/BVP, EDA/GSR, temperature, motion, timestamps, sequence, units, quality, calibration, battery, and errors. Audio records or approved features need timestamps, quality, consent state, and verified speaker attribution. Center-audio clusters alone do not identify participants or provide physiological stress.

## One-set collection design

One focal participant wears the Wrist Module in each circle session. The Audio Module remains near the center at recorded distances from fixed numbered seats. Later sessions rotate the Wrist Module so every participant becomes the focal wearer. Every record keeps the focal participant, seating map, topic, speaking opportunity, noise, light, prompts, overlap, device versions, and synchronization uncertainty.

## Privacy and exclusions

Keep names, contact details, birth dates, signatures, identity keys, unrestricted notes, raw consent forms, and unapproved voices out of the analytical package. Store approved participant data in the encrypted study store, not Git. Withdrawal, missing consent, invalid approval, identity leakage, absent calibration, irrecoverable corruption, or an exclusion frozen in the protocol makes a session ineligible.

## Split and release rules

Split by participant, never by window. Hold out complete participants and preferably a separate school or site for final testing. Freeze the split and primary metric before test evaluation. A dataset release needs source hashes, inclusion decisions, consent and withdrawal state, label policy, schema and feature versions, participant and session counts, missingness, rater reliability, subgroup coverage, known bias, access policy, retention, and deletion verification.

## Current status

`wesad-processed-development` is frozen as a development input in `release_tools/versions.json`. The PSYCON dataset version is not assigned because no eligible study package exists. No Week 5 or Week 7 empirical PSYCON result may be generated until the handoff in `docs/research/DATA_REQUIREMENTS.md` passes validation.
