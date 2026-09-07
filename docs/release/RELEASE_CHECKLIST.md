# Week 7 release checklist

## Source and versions

- [x] Candidate release ID and version map are stored in `release_tools/versions.json`.
- [x] The packager records the source commit, tracked-change state, file sizes, and SHA-256 hashes.
- [x] The archive uses tracked files only and excludes checked-in `audios/`, study directories, `.env`, and release output.
- [ ] Freeze the final hardware, PCB, firmware, calibration, dataset, model, configuration, and documentation IDs after their gates pass.
- [ ] Create the final release from a tracked-clean commit and independently verify its manifest.

## Hardware and safety

- [ ] Supply the exact hardware and PCB revision records, drawings or photographs, purchased-part identifiers, and enclosure files.
- [ ] Pass all five physical integration stages.
- [ ] Supply assembly, calibration, electrical, GSR, charging, temperature, brownout, one-hour, and six-hour records.
- [ ] Close the nine Week 6 risks with accepted evidence.
- [ ] Prepare identified backup firmware and practical backup hardware, or record why backup hardware is unavailable.

## Firmware and backend

- [x] Both firmware projects compile.
- [x] Protocol v2 fixtures agree across Python, TypeScript, and C++.
- [x] The backend has authenticated ingestion, synchronization, jobs, dashboard, export, backup, simulation, and failure-scenario tools.
- [ ] Replace Wrist placeholder values with real continuous drivers, quality, buffering, power, watchdog, and recovery behavior.
- [ ] Run the current live-stack scenarios and physical end-to-end session.

## Research and AI

- [x] Research questions, consent draft, data rules, model lifecycle, dataset join, grouped evaluation, reports, model card, and dataset card exist.
- [x] WESAD development artifacts and limitations are recorded.
- [ ] Obtain approval and a psychologist-approved stress or behavioural target.
- [ ] Supply reliable marksheets and matching synchronized PSYCON sessions.
- [ ] Freeze the PSYCON dataset, participant split, primary metric, and analysis plan.
- [ ] Generate physiology-only, speech-only, combined, ablation, error, duration, subgroup, calibration, and external-validation results.

## Documentation and demonstration

- [x] User, assembly, maintenance, recovery, competition, reference, evidence, and demonstration documents exist.
- [x] The Engineering PRD builds from source.
- [ ] Replace approximate BOM entries with exact purchased parts and dated prices.
- [ ] Replace bibliography placeholders with reviewed citations where the final submission requires them.
- [ ] Rehearse and pass the physical live demonstration.
- [ ] Record, review, hash, and store the consented backup demonstration.
- [ ] Have a third person reproduce setup, operation, export verification, shutdown, maintenance, and replay from the package.

## Final approval

The release owner changes `release_status` from `candidate` to `final` only after removing every supported blocker and attaching its evidence. The tool rejects a final configuration that still lists blockers. Record approver, date, release commit, archive hash, evidence-report hash, and rollback release before distribution.
