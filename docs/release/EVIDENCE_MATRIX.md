# Final evidence matrix

Status values mean `verified`, `partial`, or `open`. Documentation proves only the stated design or procedure. Physical completion needs a measurement record from the exact hardware revision.

## SRS acceptance criteria

| Acceptance item | Status | Current evidence | Required closure |
| --- | --- | --- | --- |
| All sensors initialize | Open | Firmware scaffolds and static build tests | Physical Stage 1 records for every sensor and real Wrist drivers |
| No I2C address conflicts | Open | Address map and scanner code | Repeated `0x57`, `0x68`, `0x18`, `0x48` scans plus one-hour stability record |
| Audio records correctly | Partial | I2S code, generated audio tests, local analysis demo | Intended INMP441 recording, continuous-buffer, placement, and quality evidence |
| Physiology streams continuously | Open | Protocol and backend accept Wrist batches | Real PPG, GSR, temperature, and motion acquisition plus continuity record |
| Modules operate independently | Partial | Separate firmware projects and simulated failure handling | Physical module-independence record |
| Battery operation is stable | Open | Power design and runtime template | Electrical, charge, temperature, brownout, one-hour, and six-hour records |
| Timestamps remain synchronized | Partial | Backend offset and uncertainty logic with tests | Measured shared-event result from both physical modules |
| Documentation is complete | Partial | PRD, runbooks, model and dataset cards, competition package | Exact purchased-part records, hardware drawings, evidence, priced budget, and verified bibliography |
| Safety procedures are documented | Verified | Week 6 runbook, user manual, assembly guide | Procedure is documented; physical safety acceptance remains separate and open |
| Hardware passes integration | Open | Ordered gate evaluator | Passed physical Stages 1 through 5 |

## Final deliverables

| Deliverable | Status | Evidence or gap |
| --- | --- | --- |
| Hardware prototype | Open | No frozen revision, photographs, inspection, or integration record supplied |
| Firmware | Partial | Both targets compile; Wrist values remain placeholders and physical recovery is untested |
| Protocol and backend | Partial | Contract, service, tests, dashboard, export, backup, simulation, and failure tools exist; physical transport and current live rerun are open |
| AI package | Partial | WESAD model, features, audio path, evaluation code, model card, and dataset card exist; no PSYCON training or external validation |
| Testing and validation | Partial | Unit tests, evidence schema, stage gates, test procedures, and report generator exist; physical records are missing |
| Safety and ethics | Partial | Rules, consent draft, data management, and study protocol exist; ethics approval and physical acceptance are missing |
| User, assembly, maintenance, and troubleshooting guides | Verified | `docs/release/USER_MANUAL.md`, `docs/release/ASSEMBLY_AND_MAINTENANCE.md`, and PRD Chapter 30 |
| Competition document | Partial | Written package exists; priced budget, final empirical results, and presentation artifact remain open |
| Release archive and manifest | Verified as candidate tooling | Deterministic packager hashes tracked files and excludes audio/private paths; final status is blocked |
| Live demonstration | Open | No verified physical demonstration record supplied |
| Backup recording | Open | Recording procedure exists; no consented recording and hash supplied |

## Chapter 33 summary

Hardware assembly, calibration, electrical safety, runtime, firmware completion, physical end-to-end testing, dataset collection, psychologist target approval, PSYCON model training, ablation, useful-duration result, external validation, and demonstrations remain open. Software architecture, protocol, research controls, evidence controls, release tooling, and the written operating package are present.

## Release decision

The repository can produce `psycon-1.0.0-rc1`, a software and documentation release candidate. It cannot produce a final competition release while any blocker in `release_tools/versions.json` remains. Changing the release status to `final` with an open blocker causes the release tool to fail.
