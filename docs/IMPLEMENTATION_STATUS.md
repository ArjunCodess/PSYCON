# Implementation status

Historical workflow. This document records the earlier implementation and does not define the current behavioral instrument. Use [the current startup guide](START_HERE.md), [behavioral direction](PSYCON_VISION.md), [instrument architecture](INSTRUMENT_ARCHITECTURE.md), and [coverage record](INSTRUMENT_STATUS.md) for new work.

This is the detailed coverage record for the communication direction as of 6 October 2026. The short progress section belongs in [README](../README.md); current behavior is specified in [architecture](COMMUNICATION_ARCHITECTURE.md).

## What can be confirmed

The personal recordings software is implemented and has run through real local enrollment, transcription, speaker attribution, interpretation, and raw deletion on synthesized speech. Software tests exercise two independent profiles, repeated uploads, eligible baselines, recurring deviations, role reports, later comparisons, context access, correction, and deletion. Synthetic tests do not satisfy the two-person human pilot or establish identity accuracy.

The entire PSYCON vision is not complete. Physical continuous wearable capture, actual wrist sensing, semantic accuracy, longitudinal usefulness, role-specific opportunity validity, all-day power behavior, and hosted personal deployment remain open. Build success and accepted group profiles are not substitutes for those measurements.

Group spreadsheet uploads now retain the CSV and parsed ratings in PostgreSQL and continue to per-person feedback under shared discussion context. Local AI proposes practice exercises; human scores remain the source of the findings and training labels. A separate database training script saves PSYCON item classifiers and a reproducible manifest. Database lifecycle tests, artifact loading, leakage checks, and a real local Qwen inference passed. The full suite now reports 324 passed and two skipped. See [group feedback and training](GROUP_FEEDBACK_AND_TRAINING.md) for the commands and limits.

## Plan coverage

| Approved work | Implemented behavior | Remaining work or validation |
| --- | --- | --- |
| Persistent personal profiles | Private wearer tokens, roles, consent, encrypted embeddings, independent histories, revocable scoped grants. | Human enrollment isolation and withdrawal rehearsal; account recovery beyond the local token pilot. |
| Unified conversations | Upload, guarded group, and completed device adapters share records and preserve original timing. Exact upload hashes deduplicate retries. | Real identity-link review and physical device import; re-encoded duplicates require source review. |
| Contextual observations | Wearer quality, timing, vocabulary, pitch, level, overlap, jitter, context correction, and local event proposals, including reasoning/jargon/structure behavior definitions. | Semantic types stay disabled until exact-version reviewed evaluation passes; context windows limit interpretation. |
| Baselines and patterns | Comparable cohorts, session medians/MAD, source-addressed snapshots, 5/3/1800 eligibility, prior comparisons, three-later-session deviations. | Human longitudinal validity, drift studies, and stronger independent-session/opportunity modeling. |
| All role lenses and coaching | General, leadership, sales, teaching, law, debate, negotiation, medicine, student, and presentation rubrics; frozen goals; question/disagreement/criticism/objection/concern/confusion response opportunities. | Semantic accuracy and role usefulness still need human evaluation. Conservative adjacent-turn rules omit ambiguous opportunities. |
| Console and context | `/coach`, evidence, metrics, progress, corrections, goals, grants, context download, deletion, scoped versioned APIs. | Human usability pilot, external AI consumer integration, hosted operations. |
| Continuous transport | Ear DMA, bounded PCM queue, Wi-Fi v2 chunks, CRC, acknowledgements/retry, NVS sequences, clock/status, BLE provisioning/pause. | Physical continuity, radio recovery, clock, attribution, power, and safe worn-use evidence. |
| Optional wrist | Existing wrist feature/research code and compiling firmware scaffold. | Real sensor drivers; wrist firmware currently emits placeholders using its older starter packet. |
| Local interpreter | Qwen 3.5 4B, digest pinning, bounded structured output, local-only endpoints, no cloud fallback. | At least 50 reviewed exchanges spanning all roles, >=90% precision and adequate predictions per enabled type. |
| Data lifecycle | Encrypted temporary media, success cleanup, 24-hour failed/orphan expiry, revision checks, audit records, cleanup retries, invalidated references. | Operational backup exclusion and withdrawal rehearsal; downloaded external context cannot be recalled. |

## Verification evidence

The initial 3 October recordings implementation passed 275 Python tests with three optional checks skipped, 20 TypeScript protocol tests, TypeScript checking, and the ear firmware build. A real PostgreSQL test exercised two synthetic wearers and cleaned its own records. A live generated-speech run completed enrollment, Whisper, Community-1 attribution, Qwen interpretation, and deletion. It returned verified attribution, English transcription, measured speech, raw state `deleted`, and semantic state `awaiting_validation`. Browser inspection showed evidence and measurements without JavaScript errors.

The local LLM used the RTX 4060; the host speech environment used CPU PyTorch. The GPU container uses the existing CUDA 12.6 toolchain. The downloaded Qwen digest is stored in the ignored `.env`; installation location is an operator-specific runtime detail in [the runbook](COMMUNICATION_COACH.md).

The follow-up audit adds strict future-date exclusion, deterministic snapshot lineage, a pinned Community-1 revision for personal analysis, visible semantic-event evidence, original-timeline group import coverage, rejection of unknown device-clock uncertainty, and manual recovery after permanent firmware rejection.

| Final check on 3 October 2026 | Result |
| --- | --- |
| `python -m pytest tests` with local PostgreSQL lifecycle enabled | 278 passed, 3 optional checks skipped. |
| Protocol Vitest and TypeScript | 20 passed; type checking passed. |
| Coach JavaScript syntax | Passed. |
| Ear firmware | Compiled; 17.0% static RAM, 82.6% flash. |
| Wrist firmware | Compiled; 11.1% static RAM, 47.0% flash; readings remain placeholders. |
| `docker compose build api worker minio` | All three final images built. |
| Built API smoke | `/coach` 200, unauthenticated personal API 401, readiness 200. |
| Built GPU worker smoke | PyTorch 2.9.1+cu126 saw the RTX 4060; Whisper, Community-1 and SpeechBrain imports passed. |
| Local Markdown links | New product documents and updated core references resolve. |

An intermediate Docker daemon stop interrupted one rebuild and the PostgreSQL check; restarting Docker and restoring the services allowed both to pass. A flaky short-substring encryption assertion was replaced with verification of the encrypted round trip. The speech libraries warn about optional file-decoding backends; the successful live path decodes media first and supplies waveforms in memory. These software results leave all human and physical gates below open.

## Software verification on 6 October 2026

The follow-up implements semantic version 2 with evidence-linked role behavior definitions, explicit opportunity/response pairs, original-word concision checks, context-aware interpretation, boundary-window overlap, and observed/unavailable rubric coverage. Complete-pass counts precede excerpt retention limits. Disabled types, missing opportunities, incomplete output windows, and partial human corrections cannot produce whole-session semantic zeros. Evaluation binds the prompt contract as well as the model digest. See [role rubrics](COMMUNICATION_ROLE_RUBRICS.md).

The full Python suite passed 311 tests with three optional checks skipped, including the live PostgreSQL two-wearer lifecycle. Protocol tests passed all 20 cases and TypeScript checking passed. Coach JavaScript syntax passed. API, GPU worker, and MinIO images rebuilt successfully. The API returned coach 200, private unauthenticated access 401, and readiness 200; the worker saw the RTX 4060 and imported the speech models through the existing compatibility adapter.

The local portable Ollama runtime could not complete its smoke test because `G:` became unavailable after startup; the tags endpoint returned a missing model-directory error. Restore that drive or reconfigure the local runtime before using interpretation on this machine. The measured-only fallback and container builds remain usable. This is an operator runtime issue, and no cloud fallback was used. Human accuracy and pilot usefulness remain unverified.

### Project-local installation follow-up

The unavailable-drive issue is resolved: Ollama 0.35.0 and Qwen, CPython 3.12, an isolated dependency environment, CUDA PyTorch 2.9.1, Node/npm, FFmpeg/ffprobe, model caches, temporary paths, logs, PostgreSQL data, and MinIO data now live inside `.runtime` in this repository. Original named service volumes and a database migration dump were preserved. Docker Desktop and the NVIDIA driver remain existing system prerequisites. An unused, incomplete Python 3.14 `.venv` remains because automatic approval review blocked its deletion; `.runtime/venv` is the working environment.

The newly downloaded Qwen tag is pinned to digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`. Existing semantic evaluations for another digest cannot enable it. Structured generation now constrains paired evidence to other-speaker and wearer references in that order, while application validation still checks original timing. The real local call returned `awaiting_validation` with complete windows. SpeechBrain produced a 192-element embedding on CUDA; Community-1 and Whisper loaded on the GPU from the project-local environment. The final launcher suite passed 312 tests with two optional skips after FFmpeg installation, protocol passed 20 tests and type checking, all 138 installed Python packages passed dependency checking, and API smoke returned 200/401/200. All three images rebuilt successfully. Optional file-decoder warnings remain; the application supplies decoded waveforms in memory.

Use [the local launcher](../release_tools/local-runtime.ps1) and [runbook](COMMUNICATION_COACH.md). Runtime artifacts, personal data, caches, and secrets remain excluded from Git. The prior `G:` configuration is no longer used.

## Release gates

1. **Recordings pilot.** Two consented human users must independently enroll, upload repeated conversations, form eligible baselines, review a supported recurring observation and adjustment, compare later sessions, export context, and delete history.
2. **Semantic claims.** Independently annotate at least 50 exchanges covering every role, disagreement, supportive overlap, criticism, and objections. Evaluate the exact model digest; only types passing the precision and prediction-count gate appear automatically.
3. **Physical wearable input.** A real microphone/ESP32 must produce the same records with measured continuity, packet loss, reconnects, reboot boundaries, clock quality, power, and wearer attribution.
4. **Optional wrist/all-day use.** Complete sensor drivers/calibration, electrical review, enclosure, bystander controls, continuous runtime evidence, and storage/recovery before broader claims.
5. **Hosted personal deployment.** Separately authorize infrastructure/worker access, define encryption/backup/retention operations, and verify external consumer boundaries. Existing hosted group research is not the personal pilot.

## Existing research evidence

The 1 October benchmark records 57 accepted guarded PSYCON profiles across 85 marked slots from 11 recordings. It describes assignment coverage rather than identity accuracy or longitudinal coaching validity. A–T human ratings remain independent of automated coaching. WESAD results concern the existing development dataset and do not validate communication interpretations or the physical wrist module.

See [the historical overview](RESEARCH_LEGACY.md), [group final report](group_discussions_final_report.md), [research data requirements](research/DATA_REQUIREMENTS.md), and [physical runbook](validation/WEEK_6_RUNBOOK.md). Historical completion percentages retain their original scope and are not current product estimates.
