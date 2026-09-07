# Week 7 release test report

**Status on 8 September 2026: software and documentation candidate passed; final release blocked.** The checks below establish source, packaging, and software behavior only. They do not close physical, study, or demonstration gates.

| Check | Observed result | Limit |
| --- | --- | --- |
| Full Python suite | 150 passed, 5 skipped in 16.31 seconds | Skips cover optional external data or services |
| Protocol tests | 20 passed | Does not test a physical radio |
| TypeScript type-check | Passed | Static contract check only |
| Audio firmware build | Passed; 35,948 bytes RAM and 615,785 bytes flash reported | Not flashed or physically tested |
| Wrist firmware build | Passed; 36,260 bytes RAM and 615,929 bytes flash reported | Still publishes placeholder sensor values |
| Deterministic audio demo | Passed expected usable and abstention cases | Uses generated audio fixtures |
| Engineering PRD | 40 pages; build passed with bibliography and no errors, undefined references, or overfull boxes | Documentation is not physical evidence |
| Release-tool tests | 5 passed | Covers version rules, exclusions, hashes, verification, and deterministic ZIP writing |
| Candidate archive | Generated with `tracked_changes_present: false`; manifest verification passed | Status remains candidate with six blockers |
| Week 6 live API scenarios | Blocked | Docker Desktop's Linux engine was unavailable on this workstation |

## Privacy review

The candidate archive is built from Git-tracked files, then applies explicit exclusions. The observed manifest excluded all five tracked files under `audios/`. It also excludes `.env`, `data/studies/`, `results/studies/`, and `release-output/` when present. Untracked psychologist marksheet working files were not added to Git and were not included in the archive.

The operator must still inspect the manifest and archive before distribution. A tracked file outside the configured private prefixes is included by design.

## Open final gates

The final hardware and PCB revisions, real Wrist firmware, calibration, electrical and GSR safety, one-hour and six-hour tests, five physical integration stages, priced BOM, approved marksheets and synchronized sessions, PSYCON model results, external validation, third-person reproduction, backup hardware decision, and live and recorded demonstrations remain open.

Run `python -m release_tools.package --output-dir release-output` after every accepted change. Preserve the generated manifest with its matching ZIP; verifying a different checkout does not establish the contents of the distributed archive.
