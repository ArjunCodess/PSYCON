# Implementation status

This is the detailed coverage record for the communication direction as of 3 October 2026. The short progress section belongs in [README](../README.md); current behavior is specified in [architecture](COMMUNICATION_ARCHITECTURE.md).

## What can be confirmed

The personal recordings software is implemented and has run through real local enrollment, transcription, speaker attribution, interpretation, and raw deletion on synthesized speech. Software tests exercise two independent profiles, repeated uploads, eligible baselines, recurring deviations, role reports, later comparisons, context access, correction, and deletion. Synthetic tests do not satisfy the two-person human pilot or establish identity accuracy.

The entire PSYCON vision is not complete. Physical continuous wearable capture, actual wrist sensing, semantic accuracy, longitudinal usefulness, role-specific opportunity validity, all-day power behavior, and hosted personal deployment remain open. Build success and accepted group profiles are not substitutes for those measurements.

## Plan coverage

| Approved work | Implemented behavior | Remaining work or validation |
| --- | --- | --- |
| Persistent personal profiles | Private wearer tokens, roles, consent, encrypted embeddings, independent histories, revocable scoped grants. | Human enrollment isolation and withdrawal rehearsal; account recovery beyond the local token pilot. |
| Unified conversations | Upload, guarded group, and completed device adapters share records and preserve original timing. Exact upload hashes deduplicate retries. | Real identity-link review and physical device import; re-encoded duplicates require source review. |
| Contextual observations | Wearer quality, timing, vocabulary, pitch, level, overlap, jitter, context correction, and local event proposals. | Semantic types stay disabled until reviewed evaluation passes; advanced reasoning/jargon/structure detectors are not implemented. |
| Baselines and patterns | Comparable cohorts, session medians/MAD, source-addressed snapshots, 5/3/1800 eligibility, prior comparisons, three-later-session deviations. | Human longitudinal validity, drift studies, and stronger independent-session/opportunity modeling. |
| All role lenses and coaching | General, leadership, sales, teaching, law, debate, negotiation, medicine, student, and presentation focus/adjustments; frozen goals. | Rule-based lenses are not validated complete semantic rubrics. Objection/concern/confusion opportunity counts need further implementation. |
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

## Release gates

1. **Recordings pilot.** Two consented human users must independently enroll, upload repeated conversations, form eligible baselines, review a supported recurring observation and adjustment, compare later sessions, export context, and delete history.
2. **Semantic claims.** Independently annotate at least 50 exchanges covering every role, disagreement, supportive overlap, criticism, and objections. Evaluate the exact model digest; only types passing the precision and prediction-count gate appear automatically.
3. **Physical wearable input.** A real microphone/ESP32 must produce the same records with measured continuity, packet loss, reconnects, reboot boundaries, clock quality, power, and wearer attribution.
4. **Optional wrist/all-day use.** Complete sensor drivers/calibration, electrical review, enclosure, bystander controls, continuous runtime evidence, and storage/recovery before broader claims.
5. **Hosted personal deployment.** Separately authorize infrastructure/worker access, define encryption/backup/retention operations, and verify external consumer boundaries. Existing hosted group research is not the personal pilot.

## Existing research evidence

The 1 October benchmark records 57 accepted guarded PSYCON profiles across 85 marked slots from 11 recordings. It describes assignment coverage rather than identity accuracy or longitudinal coaching validity. A–T human ratings remain independent of automated coaching. WESAD results concern the existing development dataset and do not validate communication interpretations or the physical wrist module.

See [the historical overview](RESEARCH_LEGACY.md), [group final report](group_discussions_final_report.md), [research data requirements](research/DATA_REQUIREMENTS.md), and [physical runbook](validation/WEEK_6_RUNBOOK.md). Historical completion percentages retain their original scope and are not current product estimates.
