# Audio Feature and Quality Contract

This document defines the software contract for mono signed PCM16 audio, local transcription, transparent English language features, consented wearer verification, conversation timing, and voice jitter. It does not infer a diagnosis or prove that the physical microphone is correctly configured.

The Engineering PRD specifies language features and conversation analysis. The implemented consent-aware stage provides timestamped text, confidence/failure states, vocabulary and sentence statistics, sentiment, emotion-related word counts, topic transitions, and basic speech/pause summaries. The acoustic quality decision runs first so unusable audio does not silently enter transcription or multimodal inference.

## Input and provenance

`analyze_audio_packet` accepts one CRC-checked Protocol v2 `audio_pcm` packet. Every accepted feature window retains the session ID, device ID, sequence, device timestamp, first sample index, sample count, nominal sample rate, SHA-256 digest of the complete source packet, and extractor identity. A caller may supply the nominal 16 kHz rate because the current integer-microsecond protocol period represents it as 62 microseconds; a disagreement greater than one microsecond is rejected.

The extractor is `psycon_audio`. Its ordered feature vector is:

1. duration in seconds;
2. RMS and peak level in dBFS;
3. clipped-sample fraction and normalized DC offset;
4. zero-crossing rate;
5. spectral centroid, 85% rolloff, and flatness;
6. mean, standard deviation, minimum, and maximum autocorrelation pitch from 70 to 400 Hz;
7. relative pitch jitter and a bounded voice-stability score;
8. energy-active frame fraction, pause count, and total pause duration from 25 ms frames with a 10 ms hop.

This vector uses NumPy only, so it has no model download or feature-extractor licensing dependency. Changes must update the contract and equivalence tests together.

## Quality decisions

The analysis returns exactly one state before any downstream inference:

| State | Current deterministic rule | Consequence |
| --- | --- | --- |
| `usable` | At least one second, adequate energy, no excessive clipping, and spectral flatness at or below 0.5 | Features may enter a research model. |
| `insufficient_audio` | Duration below one second, RMS below -45 dBFS, or fewer than 10% active frames | Abstain because there is too little signal. |
| `clipped` | More than 1% of samples are at PCM16 full scale | Abstain because amplitude and spectrum are distorted. |
| `too_noisy` | Spectral flatness exceeds 0.5 after the energy check | Abstain because broadband noise dominates this baseline check. |
| `corrupt` | Protocol/CRC/type failure or invalid PCM shape/rate | Reject the window and record the reason. |
| `missing_audio` | No packet was supplied | Preserve missingness; never replace it with zeros. |

These thresholds are frozen for deterministic testing, not claimed as final field calibration. Replace them only with versioned evidence from the final INMP441 placement, measured noise floor, clipping behavior, and approved study data.

## Deterministic fixtures and demo

`ml/src/audio_fixtures.py` generates silence, impulse, 220 Hz tone, clipped tone, amplitude-modulated speech-like signal, and seeded white noise. “Speech-like” describes a synthetic prosody fixture and must not be presented as human speech data.

Run the small local demo from the repository root:

```powershell
python -m demo.audio_demo
```

It wraps each fixture in a Protocol v2 packet, runs decoding, provenance, feature extraction, and abstention, then writes `results/demo/audio_demo.json`. The demo also injects a missing packet and a CRC-corrupted packet. It uses generated signals only, so no microphone, personal recording, or consented dataset is required.

The physical Week 3 gate remains separate: Saksham must verify I2S channel/sign/shift/sample rate, establish placement-specific noise and clipping limits, prove continuous DMA and overrun accounting, align TEMT6000 readings to the audio clock, and save the one-hour capture evidence.

## Transcription and language decisions

`psycon_transcription` uses `faster-whisper` with a locally cached model. The development profile defaults to the multilingual `small` model on CPU with int8 computation. The approved production profile is `turbo` on a CUDA GPU with float16 computation; it runs inside the PSYCON backend rather than a third-party transcription API. Configure these profiles with `PSYCON_WHISPER_MODEL`, `PSYCON_WHISPER_DEVICE`, and `PSYCON_WHISPER_COMPUTE_TYPE`. Raw recordings still require encrypted transport, restricted access, consent, and an explicit retention policy when the backend performs transcription.

Use the production profile with:

```powershell
$env:PSYCON_WHISPER_MODEL = "turbo"
$env:PSYCON_WHISPER_DEVICE = "cuda"
$env:PSYCON_WHISPER_COMPUTE_TYPE = "float16"
python demo/audio_web_app.py
```

Model selection remains an empirical research decision. Before freezing a release, compare `small`, `medium`, and `turbo` on representative consented multilingual recordings using word error rate, language-detection accuracy, latency, peak memory, and downstream language-feature stability. Transcription is multilingual, but `psycon_language` still abstains from sentiment, emotion-word, vocabulary, and topic-transition analysis outside English until validated language-specific feature extractors exist.

Only contiguous windows marked `usable` by `psycon_audio` are transcribed. The result is one of `complete`, `no_speech`, `skipped_quality`, `not_requested`, `transcription_unavailable`, or `failed_transcription`. Completed segments retain start/end time, approximate confidence, source-sample boundaries, and word timestamps used for speaker attribution.

`psycon_language` supports English transcripts. It reports word and unique-word counts, vocabulary diversity, sentence count and mean length, a small lexicon-based sentiment baseline, emotion-related word counts, topic-transition distance, speech-segment count, speaking duration, pauses, and words per minute. Non-English transcripts return `unsupported_language`, short transcripts return `insufficient_text`, and missing transcription returns `transcription_unavailable`.

The lexicons are deliberately small and inspectable. Their values are research features for ablation testing, not validated emotion recognition. Filler-word classification is not implemented.

## Speaker, timing, and jitter analysis

`psycon_speaker_analysis` runs `pyannote/speaker-diarization-community-1` on the project-controlled server. `HF_TOKEN` grants the gated model access, while `PSYCON_DIARIZATION_DEVICE` selects CPU or CUDA. Regular diarization measures overlap; exclusive diarization assigns word timestamps to speakers. Words with less than 50% overlap with any turn remain `unknown`.

One wearer is enrolled from exactly three clean 5–10 second WAV or MP3 recordings. SpeechBrain ECAPA-TDNN creates normalized embeddings, which are averaged and encrypted using `PSYCON_PROFILE_KEY`. The recordings are held in memory and discarded, and neither raw embeddings nor enrollment audio enter results or logs. The page supports profile deletion and replacement.

Each diarized speaker needs at least three seconds of clean non-overlapping speech before comparison. A cluster becomes `participant` only when it exceeds `PSYCON_SPEAKER_THRESHOLD` and beats the runner-up by `PSYCON_SPEAKER_MARGIN`; otherwise the analysis reports an explicit abstention. All other clusters are anonymous within the current recording.

The analyzer reports speaking duration/share, turn statistics, articulation and session speaking rates, within-speaker pauses, response gaps, signed transition latencies, overlap, and interruptions. A pause is at least 200 ms before the same speaker continues. An interruption starts at least 200 ms before the active turn ends and lasts at least 500 ms.

Praat through Parselmouth calculates local absolute jitter, local relative jitter, RAP, PPQ5, and DDP on separate continuous regions of at least one second. Overlapped, clipped, low-energy, short, and pitch-insufficient regions abstain. Aggregates are weighted by valid voiced duration and include coverage; these microphone-sensitive measurements are research features, not diagnostic evidence.

## Local real-recording webpage

Install the declared Python dependencies and start the local server from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m demo.audio_web_app
```

Set `PSYCON_PROFILE_KEY` to a random secret of at least 32 characters and supply `HF_TOKEN` for the gated local diarization model. Select CUDA with `PSYCON_DIARIZATION_DEVICE` and `PSYCON_SPEAKER_DEVICE` on the intended server.

Open `http://127.0.0.1:5000`, enroll the wearer, and upload a WAV or MP3 conversation recording. WAV follows the deterministic SciPy decoder, while MP3 is decoded in memory through PyAV. The page accepts at most 12 MB and five minutes, holds conversation and enrollment recordings in process memory rather than writing them to disk, and provides playback. It downmixes as many as eight channels, resamples supported rates to 16 kHz, converts samples to PCM16 without loudness normalization, and divides the recording into balanced sequential windows of at most two seconds. Independent failure states keep acoustic analysis and transcription usable when model access or enrollment is missing.

The summary is `usable` only when every window passes, `partially_usable` when at least one window passes, and `no_usable_audio` when none pass. The per-window table remains authoritative because a usable section must not hide clipping, noise, silence, or an insufficient final window elsewhere in the recording.

The page requires recording permission and separate biometric-processing consent. These checkboxes are engineering safeguards, not a complete participant-consent system. The Flask development server binds to localhost and has no authentication, encrypted transport, audit log, or production deployment configuration. Do not expose it to a network or use it to collect research participants' recordings.
