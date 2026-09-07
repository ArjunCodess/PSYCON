# PSYCON study protocol

**Status:** protocol prepared; participant recruitment and collection are blocked until the applicable ethics or school review approves this protocol and its consent materials.

PSYCON studies whether synchronized wrist physiology and speech-derived features improve a non-clinical experimental classification task. The study does not diagnose, screen for, or recommend treatment for any medical or psychological condition.

## Frozen research questions

1. Does the combined model improve participant-separated performance over physiology-only and speech-only models?
2. How do recorded environment categories and ambient-light levels affect performance and data quality?
3. How do motion level and wrist signal quality affect performance and abstention?
4. What is the shortest recording duration at which the selected features and model output remain stable under the preregistered tolerance?

The protocol must define the target label, sample-size rationale, primary metric, stability tolerance, environment categories, motion categories, and external dataset before recruitment begins. Changes after collection starts require a dated amendment and a new protocol version.

## Approval gate and eligibility

The study operator records the approval identifier and approved protocol version in every session manifest. If either field is absent, the ingestion validator rejects the session for research use.

Participants must meet the approved age criteria, be able to consent or have approved guardian permission, and be able to wear the device comfortably. Exclude a participant if the approved protocol requires exclusion for damaged skin at an electrode site, an implanted medical device, inability to wear the device safely, or refusal of either physiological or audio consent. Audio is optional unless the approved study design explicitly requires it; refusal must never be overridden.

Use a random participant ID such as `P-7F3A91`. Keep the identity-to-ID key outside this repository and outside the research dataset. Do not put names, email addresses, phone numbers, dates of birth, or free-text identifying notes in metadata.

## Session workflow

1. **Confirm authority.** Verify the approval identifier, protocol version, current consent, optional audio consent, optional voice-profile consent, and withdrawal status.
2. **Check the hardware.** Record hardware and firmware versions, battery state, sensor status, calibration record IDs, physical condition, and the safety checklist result. Do not proceed with worn collection if conductors are exposed, a battery is damaged or hot, GSR excitation is unverified, or external power is connected.
3. **Prepare the participant.** Inspect the approved contact area, attach the wrist module, position the audio module, explain how to stop, and confirm comfort. Never charge either module while it is worn or while GSR electrodes are attached.
4. **Start together.** Create one session ID, start the wrist and audio modules against the same backend epoch, and record synchronization uncertainty. Mark absent modalities explicitly.
5. **Monitor without coercion.** Record device status, errors, battery, signal quality, environment, and motion. Stop on withdrawal, discomfort, unsafe hardware, loss of required consent, or a protocol-defined failure.
6. **Close and preserve.** Stop both modules, record duration and stop reason, hash raw objects, create an immutable manifest, back up encrypted data, and run the quality review before feature extraction.
7. **Review eligibility.** Apply the frozen inclusion, exclusion, and quality rules. Record every exclusion with a controlled reason code. Never delete an inconvenient result or silently repair corrupted data.

## Recorded variables

Session metadata contains the anonymous participant ID, approved age group, optional biological sex only when approved and volunteered, UTC start time, duration, environment category, motion condition, hardware and firmware versions, battery status, sensor status, error codes, calibration record IDs, consent versions, synchronization quality, and withdrawal state.

Raw records contain physiology, motion, ambient light, consented speech, device timestamps, sequence numbers, checksums, status, and quality fields. Derived records contain synchronized physiological features, acoustic features, transcript and language features, context features, labels, missingness indicators, provenance, and extraction versions. Free-text operator notes must not contain identifying information.

## Quality and exclusion rules

The analysis pipeline preserves missing, corrupt, late, clipped, low-contact, saturated, untranscribable, and unsynchronized states. It may impute training features within a participant-safe pipeline, but it must retain missingness indicators and report the affected counts. It excludes a window only under a rule frozen before the test set is opened.

Exclude an entire session when consent is invalid or withdrawn, the participant is ineligible, raw provenance cannot be verified, synchronization exceeds the approved bound, or the protocol's required modality is absent. A modality-specific failure may remain in the dataset for missing-signal evaluation if consent and provenance are valid.

## Analysis plan

Create one participant-level train, validation, and test assignment and reuse it for physiology-only, speech-only, and combined datasets. Fit preprocessing only on training participants. Select models and thresholds with the validation participants, then evaluate once on the held-out test participants. Report accuracy, precision, recall, F1, ROC-AUC when both classes exist, confusion matrices, false-positive and false-negative counts, bootstrap confidence intervals, data-quality coverage, and abstentions.

Run group cross-validation on the development participants, modality ablations, environment and motion slices, and duration-stability analysis. External validation requires a separate named dataset with compatible labels and features; fixture data and an internal holdout do not count as external validation.

## Reporting rules

Reports identify the dataset, protocol, feature, split, model, firmware, hardware, and code versions. They distinguish fixture, public, pilot, and approved participant data. Every report includes limitations and states that outputs are research indicators, not clinical diagnoses. Negative and inconclusive results remain in the report.

