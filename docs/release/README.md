# Week 7 release package

PSYCON `1.0.0-rc1` is a software and documentation release candidate. It is not a final hardware or research release because the blockers in `release_tools/versions.json` remain open.

## Package contents

- `USER_MANUAL.md` covers setup, firmware, backend operation, one-set circle collection, audio analysis, export, replay, backup, recovery, and shutdown.
- `ASSEMBLY_AND_MAINTENANCE.md` covers assembly order, inspections, maintenance, change control, storage, and transport.
- `COMPETITION_PACKAGE.md` contains the executive summary, design, AI method, current results, limitations, safety, ethics, budget status, timeline, and submission decision.
- `DEMONSTRATION_RUNBOOK.md` defines the physical sequence, software fallback, backup recording, and acceptance criteria.
- `AI_MODEL_CARD.md` and `DATASET_CARD.md` state exactly what the WESAD artifact supports and what the missing PSYCON dataset must contain.
- `EVIDENCE_MATRIX.md` maps SRS acceptance and final deliverables to evidence and open work.
- `RELEASE_CHECKLIST.md` controls final approval.
- `OFFICIAL_REFERENCES.md` links manufacturer, ethics, reporting, and WESAD sources.

Templates for the priced budget and demonstration record are under `release_tools/templates/`. Week 6 physical evidence templates remain under `validation/templates/`.

## Build the candidate

Run all verification commands in `docs/REPRODUCIBILITY.md`, then build and verify the archive:

```powershell
python -m release_tools.package --output-dir release-output
python -m release_tools.package --verify release-output/release-manifest.json
```

The archive contains only Git-tracked files. It excludes `audios/`, `.env`, study directories, and release output. The manifest records every included file's size and SHA-256 hash, the source commit, tracked-change state, version IDs, status, excluded tracked paths, and blockers.

Build only from a commit with `tracked_changes_present: false`. The user may have unrelated untracked files, so the release cleanliness check intentionally evaluates tracked changes. Review the excluded-path list before distribution.

## Promote to final

Close each blocker with accepted evidence, replace provisional version IDs, remove only the blockers that the evidence resolves, and change `release_status` to `final`. The packager rejects `final` while the blocker list is nonempty. Independently verify the archive, evidence report, live demonstration, backup recording, and rollback package before publishing.
