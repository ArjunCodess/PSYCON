# Audio-only PSYCON architecture and research protocol

PSYCON is a behavioral observation and communication research instrument. It connects a person's speaker-specific talking patterns and discussion context with psychologist-reviewed observations from the A-T marksheet. It preserves timestamped evidence and personal history, and trains supervised models to predict eligible contextual ratings from conversational data.

Participant evidence and reviewed marksheet observations define the behavioral focus. Existing archetype controls now appear as optional exploratory disclosures. Speaker reports additionally read current human observations through the latest confirmed participant mapping, excluding withdrawn people and participants. Those report-only annotation records do not change the controlled A/B/C packets. See [the staged behavioral direction](PSYCON_VISION.md).

## Runtime and persistence

`run_psycon.py web` serves the canonical local application on 127.0.0.1:8001. `run_psycon.py worker` processes durable speech, interpretation, import, and training queues. The legacy default entry point opens this same application. PostgreSQL is mandatory; startup never creates a SQLite database or silently falls back to one. Migration is an explicit operator command.

The `psycon` PostgreSQL schema holds all application records, immutable human annotation revisions, frozen training datasets, evaluations, and provenance. Native psycopg pools use short transactions, connection timeouts, and a 30-second statement timeout. Original media and model artifacts remain in registered local roots with exact filenames, paths, sizes, and SHA-256 hashes. Normalized playback files are disposable. Annotation spreadsheets and bounded scanned sources are retained in PostgreSQL. Failed ingestion removes only the newly created upload directory.

Users, profiles, sessions, speakers, turns, utterances, words, features, evidence, directed interactions, traits, trait-evidence edges, baseline snapshots, baseline feature statistics, baseline-source edges, archetypes, archetype dimensions, comparisons, LLM runs, feature evaluations, behavioral annotations, and reviewer ratings are separately queryable. JSON additionally stores raw stage outputs, input representations, configurations, and statistical snapshots.

The local instrument assumes a trusted single-user machine. Same-origin mutation checks and an explicit request header block cross-origin browser writes. This is not a public-hosted authentication system; do not bind the standalone service to a public interface without adding deployment access controls. Media are retained locally until explicit deletion, as requested. Legacy encrypted-spool retention does not apply to this workspace.

## Pipeline and inspectable intermediate outputs

1. **Ingestion.** MP3, WAV, M4A, MP4, MOV, and OGG are accepted. Each file stores original filename, SHA-256, recording time in UTC, processing configuration, model provenance, context, participant IDs, recording conditions, consent status, dataset, and split. Maximums are 8 GiB, four hours, eight input channels, and 12 diarized speakers.
2. **Preprocessing.** PyAV extracts audio, downmixes to mono, and resamples to 16 kHz PCM16. Source time is preserved; silence is never removed or concatenated. Diagnostics record original channels/rate, duration, clipping fraction after downmix, 20 ms frame silence below -50 dBFS, and an energy-quantile contrast proxy. The proxy is not a calibrated SNR. Denoising is disabled. Silence, invalid samples, corruption, absent audio, and recordings below one second fail explicitly.
3. **Diarization.** A lazy Community-1 adapter accepts normalized in-memory waveforms and preserves regular overlapping speaker intervals. Diarization confidence remains null when the model does not supply it. The default revision is pinned, and an adapter interface permits replacement without changing storage or feature calculations.
4. **Transcription.** The large-v3 adapter uses beam size 5, English, VAD, word timestamps, and no conditioning on previous text. Its default model revision is pinned. Model confidence is an estimate, not calibrated accuracy. Raw segment outputs remain in the stage record.
5. **Attribution.** Words need at least 80% coverage by one speaker and below 10% coverage by another speaker. Ambiguous words remain unattributed, including overlapping words. Segment-only fallback uses the same conservative rule. Word timestamps remain queryable and raw transcript remains accessible.
6. **Segmentation and features.** Same-speaker diarized intervals within 0.3 seconds are merged into turns. Speaker changes, sentence endings, and word gaps above one second delimit utterances. Adjacent exchanges preserve speaker, preceding utterance, following response, overlap, session context, and supplied topic. Automatically inferred topic boundaries and phases are unavailable; reviewed annotations can add them.
7. **Evidence.** Each marker event points to a session, speaker, utterance, timestamp, excerpt, context, confidence, and measurement level. Directed responses are adjacent-turn estimates. Overlap entries are interruption candidates only; their intent is unknown. Traits have explicit evidence edges.
8. **Profiles, comparisons, and reasoning.** Historical statistics and mathematical reference similarities are calculated without an LLM. The LLM receives bounded structured evidence and generates separately labeled observations, inferences, limitations, and possible adjustments. Its input, exact system prompt, decoding parameters, model digest, raw output, validation outcome, and version are retained.

Mean transcript confidence below 0.55, attributed word coverage below 0.60, or clipping above 5% withholds communication profiles. Available transcripts and preceding stage outputs remain inspectable. Missing transcription or failed diarization cannot produce features or a confident profile. These are prototype quality gates, not independently calibrated operating thresholds.

PostgreSQL owns job claims, renewable leases, worker heartbeats, attempt budgets, cancellation, and the shared GPU lease. Expired jobs recover only after their worker heartbeat expires. Completion transactions check the owner, attempt, lease, and input revision. Transient connectivity/timeouts have bounded exponential retry delays; invalid inputs fail explicitly. Cached speech retries retain transcript/evidence identities and refuse changed evidence rather than deleting cited records. Mapping, annotation, consent, and context changes invalidate dependent snapshots, models, predictions, and interpretations.

See [the PostgreSQL and training runbook](POSTGRES_TRAINING_RUNBOOK.md) for migration, role configuration, imports, supervised training, activation, deletion, backups, and verified restoration.

## Formal feature dictionary

The dictionary is served at `/api/instrument/dictionary`, exported in every ZIP, and defined in `backend/instrument/features.py`. Each feature specifies description, unit, calculation, source, valid range, confidence, and schema version.

Speaking share is a speaker's exclusive duration divided by all exclusive speech duration. Speaking time includes the union of that speaker's intervals, including overlap. Words/minute uses attributed lexical words divided by that speaker's diarized time. Question/proposal/disagreement rates use the original session duration, so exposure denominators remain transparent. Interruption-candidate rate is candidate overlap entries per ten minutes of session exposure, not confirmed interruption frequency.

Question punctuation, WH-initial questions, hedging, assertion, acknowledgement, proposal, reasoning, experimentation, concession, and disagreement use explicit rules. They are unvalidated linguistic indicators. A word or marker never proves a psychological trait. Undetectable or unvalidated dimensions remain null, never zero. Manual annotations can record topic events, argumentation, question types, directed interruptions, acknowledgement, and other behaviors; their derived rates explicitly describe partial annotated events rather than exhaustive truth.

## Personal baseline and longitudinal inference

Profiles require explicit speaker mapping; anonymous cluster labels do not imply cross-session identity. One person maps to at most one cluster per session. Baselines query strictly earlier complete sessions only. Equal recording times are not treated as prior history. Reference sessions are excluded from personal history. Development baselines cannot see validation/evaluation data, and validation cannot see final evaluation; evaluation may use eligible prior history under the documented within-person temporal protocol.

Context-specific baselines use exact session-context matches. The global baseline is stored separately. Each comparable recording contributes one value per feature; speech duration does not weight a long conversation as many independent samples. Statistics include mean, median, sample variance/SD, empirical 10th/90th percentiles, sample count, current-session empirical percentile, and an explicitly descriptive current/median ratio when the median is nonzero.

Five previous comparable sessions are required to flag deviations. A value over two sample SD from the earlier mean is a descriptive flag, not a statistical-significance claim. A zero-SD baseline flags a changed value without inventing a z-score or infinite ratio. Confidence remains low below ten samples and moderate afterward; sample count alone does not establish validity. Recurring indicators require evidence in at least three independent recordings and do not establish a fixed personality.

## Optional exploratory reference comparisons

Reference dimensions are normalized into [0,1]. Ratio features use their original [0,1] range. Proposal generation uses `clip(proposals/minute / 2, 0, 1)`, an explicit prototype scale rather than a population percentile. Missing dimensions are omitted. At least three common dimensions are required.

The similarity calculation is `100 * (1 - sqrt(sum(w * (person - reference)^2) / sum(w)))`. Each dimension, weight, normalized value, reference center, difference, source, sample count, and limitation is available. Scores are comparable only across an equivalent selected feature space; dimensional coverage is shown. No number means percentage occupational identity.

Project-defined Executive, Builder, Salesperson, and Negotiator frameworks are marked exploratory and not expert-validated. Group-derived lenses select one speaker per reference recording with the smallest mean squared distance to each documented framework on available shared dimensions, then calculate centers across recording-level observations. Thus the observed values come from the corpus, but the role selection criteria remain a project assumption. This does not validate occupational archetypes or remove selection bias. The raw A–T marksheet scores are never converted into role labels.

Custom references can use explicit reviewer-selected speakers from at least three reference recordings. Recordings are averaged first, so larger groups do not inflate independent N. Source session, source speaker, source participant IDs where known, distributions, and version remain available. Comparisons exclude their own source session, known source person, or overlapping participant IDs. Unknown cross-recording identity remains an explicit unresolved limitation; anonymous slots cannot prove participant disjointness.

## Matched research experiment

Conditions share the same target speaker, first 40 utterances around their first contribution, selected target, model digest, exact prompt, seed 42, temperature 0, context limit 16,384, and output budget 2,200 tokens.

- A receives the speaker-attributed transcript window and selected archetypes only.
- B additionally receives session features and exchange context, without historical baseline.
- C additionally receives strictly previous personal baseline, documented reference dimensions and comparisons, normalization, and retrieved contextual evidence.

Evidence retrieval covers indicator types rather than using only one repeated marker. At most 24 records are selected, with up to three per kind. Representations over 48,000 characters fail explicitly rather than silently dropping history or evidence. Interpretations must qualify their limited transcript coverage. Session-level features still describe the full successfully processed recording.

All three conditions share the same evidence-integrity guardrails, so the experiment tests input representation rather than relaxing A's safety constraints. Generation constrains target speaker IDs and allowed citation IDs. Postvalidation rejects invented references or unsupported speaker ownership, and every claim requires observation, inference, confidence, limitation, and suggestion. These checks establish ID integrity only. Independent evaluation must determine whether cited evidence supports the claim and whether its interpretation overclaims.

Review pages conceal condition, model, run ID, feature packet, and baseline. Wording can still reveal a condition; report that blinding limitation. Reviewers rate grounding, attribution, contextual appropriateness, archetype agreement, usefulness, overclaiming, and trait validity on a 0–4 ordinal scale. Unsupported proportion uses claims whose mean grounding rating is zero. Quadratic weighted Cohen's kappa uses common paired reviewer items; insufficient or invariant paired ratings remain unavailable. Feature reliability reports MAE against supplied independent numeric annotations, with independent recording count. No significance test or confidence interval is fabricated.

The five planned experiments are feature reliability, A vs B context representation, B vs C personalization, A vs C archetype comparison, and repeated-session consistency/deviations. Implemented run and annotation machinery does not mean the experiments have established improvement. Final evaluation requires a documented fixed dataset, known participant splits, consent/ethics status, sufficient repeated recordings, independent annotations, and frozen reference/framework versions. Reserve final evaluation before adjusting prompts or thresholds.

## Exports

Session exports support JSON, feature CSV, RTTM, transcript text, and a ZIP containing the full report, all intermediate rows, feature dictionary, LLM provenance, and evaluation summary. Research JSON includes annotations and the dataset manifest. The audio endpoint serves normalized playback and a separate retained-original download. JSON exports contain actual failure states, never invented successful stages.

## Model API sources

The adapter follows [Community-1's official model interface](https://huggingface.co/pyannote/speaker-diarization-community-1) and [faster-whisper's official transcription interface](https://github.com/SYSTRAN/faster-whisper). Model availability, local inference checks, or existing group coverage are not evidence of longitudinal communication validity.

## Behavioral targets, annotations, and training storage

Ordered migrations in `backend/instrument/migrations` create a separate `psycon` schema under a migration ledger and advisory lock. Runtime requests never execute migrations. Native JSONB, timezone-aware timestamps, finite measurements, and explicit start_s/end_s columns retain the external transcript timing contract. PostgreSQL leases own speech, interpretation, import, and training jobs; completion checks owner, attempt, lease, and input revision. A shared GPU lease excludes concurrent speech/LLM use. Frozen datasets use a serializable transaction to detect concurrent revisions.

People, session participants, and speaker clusters remain distinct. Reviewed mappings and consent precede feature joins. Human observer answers, self-report, independent review, adjudication, supervised predictions, and LLM claims retain separate storage and provenance. Corrections and withdrawals invalidate dependent snapshots and flag model weights for retraining; deletion additionally removes affected weights and frozen private copies. Original media keep exact local filenames, and small bounded annotation sources remain database bytes. See the storage/training runbook for the implemented contract and remaining validation gates.

B and C receive the same frozen supervised-model predictions and feature version, so the personalization comparison isolates history/reference/evidence representation. Supervised prediction evaluation is reported separately. Uncalibrated logistic probabilities are explicitly identified; no model is active automatically.
