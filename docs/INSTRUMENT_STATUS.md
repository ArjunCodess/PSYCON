# Current specification coverage

This records implementation scope, not scientific success. The user's audio-first specification supersedes the previous wearable/coaching product direction.

| Area | Implemented behavior | Remaining validation or limitation |
| --- | --- | --- |
| Audio ingestion | Multiple uploads, immutable originals, hashes, dates/context/conditions/participants/splits/consent | Near-duplicate excerpts need dataset-level provenance review; hashes detect exact duplicates only |
| Preprocessing | Audio extraction, mono 16 kHz, duration/channels/rate, clipping/silence diagnostics, explicit corruption/silence/length gates | Energy contrast is an SNR proxy; no aggressive denoising |
| Speaker processing | Community-1 regular overlap turns, large-v3 timestamped transcript, replaceable adapters | Diarization and ASR accuracy need independent labels |
| Speaker attribution | Conservative word alignment, ambiguous/unattributed speech, editable names/person mapping | No automatic identity across recordings; manual mapping must be reviewed |
| Segmentation | Turns, sentences, gaps, adjacent exchanges, contextual neighbors | Topic boundaries and conversational phases require manual annotation |
| Observable features | Speaking quantity, timing, overlap entries, questioning and linguistic-marker rules | Semantic indicators are exploratory; interruption intent is not automatically established |
| Rich behavior layer | Manual topic, argumentation, interaction, question-type, interruption, turn-taking annotations | Partial annotation coverage is visible; not an independently validated automatic semantic classifier |
| Evidence graph | Session/speaker/utterance/time/context/event/trait lineage; clickable playback and examples | Source IDs alone do not validate interpretation |
| Personal baseline | Strictly earlier eligible sessions, per-recording statistics, global/context baseline, uncertainty, deviation flags | Five prior comparable recordings are a prototype minimum, not proof of stable personality |
| Archetypes | Four exploratory frameworks; empirical group-derived behavioral lenses; custom corpus references; documented distance | Occupational role ground truth is absent; framework selection and normalization need external justification |
| LLM reasoning | Local digest-pinned calls, matched A/B/C inputs, constrained citations, observation/inference separation, raw audit | Independent reviewers must evaluate support, diagnostic overclaiming, and usefulness |
| Reports and coaching | Trait evidence, dimensions, baseline changes, selected target, cautious evidence-based adjustments | Coaching usefulness and outcomes are not validated |
| Longitudinal view | Chronological feature charts/tables, recurring indicators, session comparison | Current imported reference recordings are not a verified personal longitudinal cohort |
| Group dynamics | Directed response/acknowledgement/disagreement estimates, overlap candidates, reviewed event directions | Adjacency is not always a true directed response |
| Research area | Five experiment definitions, real A/B/C run queue, feature reference annotations, blinded ratings, kappa, exports | No independent benchmark results yet; empirical improvement remains unproven |
| Storage and failure handling | Relational SQLite, inspectable stages, exclusive worker lock, leases/checkpoints, retry/deletion/stale invalidation | Public hosted multi-user deployment is outside this local prototype |
| Reproducibility | JSON/CSV/RTTM/transcript/ZIP/research manifest, model versions and revisions, LLM digest/prompt/config | Reference/framework versions must be frozen before final evaluation |
| Hardware and physiology | Excluded from the active instrument | Legacy files are retained for historical compatibility only |

Six saved group recordings with embedded recording times were imported locally as exploratory reference data. Their guarded intervals and partial transcripts preserve original Whisper-small provenance, missing word confidence, and undocumented consent status. Five other saved recordings lack embedded times and are skipped. This is not a new participant recruitment count or a validated evaluation dataset.

Technical smoke runs use actual recorded audio, Community-1, large-v3, and local Ollama. They establish that components can run together, not that downstream claims are accurate or that C outperforms A/B. Synthetic test fixtures never populate the application or its research charts.

Local verification on October 7, 2026: the complete automated suite passed 344 tests, with five optional integration tests skipped because their external services or fixtures were unavailable. Both browser scripts passed JavaScript syntax checks. An isolated real-audio CUDA run completed all eight pipeline stages, and a matched local A/B/C batch completed with exact stored prompts, model digest, and decoding settings. Earlier failed and superseded runs remain visible in the audit history. No human evaluation scores were supplied by these technical checks.

The full requested scientific project cannot be declared validated until the independent dataset, repeat-person mappings, reference definitions, reviewer annotations, and predeclared experimental analysis are available. Missing results remain `Not evaluated yet`.
