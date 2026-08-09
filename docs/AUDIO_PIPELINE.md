# Audio Feature and Quality Contract

Week 3 freezes a deterministic software contract for mono signed PCM16 audio, local transcription, and transparent English language features. It does not identify a speaker, infer a diagnosis, or prove that the physical microphone is correctly configured.

The Engineering PRD specifies language features and conversation analysis. The implemented consent-aware stage provides timestamped text, confidence/failure states, vocabulary and sentence statistics, sentiment, emotion-related word counts, topic transitions, and basic speech/pause summaries. The acoustic quality decision runs first so unusable audio does not silently enter transcription or multimodal inference.

## Input and provenance

`analyze_audio_packet` accepts one CRC-checked Protocol v2 `audio_pcm` packet. Every accepted feature window retains the session ID, device ID, sequence, device timestamp, first sample index, sample count, nominal sample rate, SHA-256 digest of the complete source packet, and extractor version. A caller may supply the nominal 16 kHz rate because the current integer-microsecond protocol period represents it as 62 microseconds; a disagreement greater than one microsecond is rejected.

The extractor version is `psycon_audio_v2`. Its ordered feature vector is:

1. duration in seconds;
2. RMS and peak level in dBFS;
3. clipped-sample fraction and normalized DC offset;
4. zero-crossing rate;
5. spectral centroid, 85% rolloff, and flatness;
6. mean, standard deviation, minimum, and maximum autocorrelation pitch from 70 to 400 Hz;
7. relative pitch jitter and a bounded voice-stability score;
8. energy-active frame fraction, pause count, and total pause duration from 25 ms frames with a 10 ms hop.

This vector uses NumPy only, so it has no model download or feature-extractor licensing dependency. It should remain unchanged under the v1 name; incompatible changes require a new version and equivalence tests.

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
python -m demo.audio_week3_demo
```

It wraps each fixture in a Protocol v2 packet, runs decoding, provenance, feature extraction, and abstention, then writes `results/demo/audio_week3_demo.json`. The demo also injects a missing packet and a CRC-corrupted packet. It uses generated signals only, so no microphone, personal recording, or consented dataset is required.

The physical Week 3 gate remains separate: Saksham must verify I2S channel/sign/shift/sample rate, establish placement-specific noise and clipping limits, prove continuous DMA and overrun accounting, align TEMT6000 readings to the audio clock, and save the one-hour capture evidence.

## Transcription and language decisions

`psycon_transcription_v1` uses `faster-whisper` with a locally cached model. The development profile defaults to the multilingual `small` model on CPU with int8 computation. The approved production profile is `large-v3-turbo` on a CUDA GPU with float16 computation; it runs inside the PSYCON backend rather than a third-party transcription API. Configure these profiles with `PSYCON_WHISPER_MODEL`, `PSYCON_WHISPER_DEVICE`, and `PSYCON_WHISPER_COMPUTE_TYPE`. Raw recordings still require encrypted transport, restricted access, consent, and an explicit retention policy when the backend performs transcription.

Use the production profile with:

```powershell
$env:PSYCON_WHISPER_MODEL = "large-v3-turbo"
$env:PSYCON_WHISPER_DEVICE = "cuda"
$env:PSYCON_WHISPER_COMPUTE_TYPE = "float16"
python demo/audio_web_app.py
```

Model selection remains an empirical research decision. Before freezing a release, compare `small`, `medium`, `large-v3-turbo`, and `large-v3` on representative consented multilingual recordings using word error rate, language-detection accuracy, latency, peak memory, and downstream language-feature stability. Transcription is multilingual, but `psycon_language_v1` still abstains from sentiment, emotion-word, vocabulary, and topic-transition analysis outside English until validated language-specific feature extractors exist.

Only contiguous windows marked `usable` by `psycon_audio_v2` are transcribed. The result is one of `complete`, `no_speech`, `skipped_quality`, `not_requested`, `transcription_unavailable`, or `failed_transcription`. Completed segments retain start/end time, approximate confidence, and source-sample boundaries.

`psycon_language_v1` supports English transcripts. It reports word and unique-word counts, vocabulary diversity, sentence count and mean length, a small lexicon-based sentiment baseline, emotion-related word counts, topic-transition distance, speech-segment count, speaking duration, pauses, and words per minute. Non-English transcripts return `unsupported_language`, short transcripts return `insufficient_text`, and missing transcription returns `transcription_unavailable`.

The lexicons are deliberately small and inspectable. Their values are research features for ablation testing, not validated emotion recognition. Transcript segments are not speaker turns, and speaker diarization is explicitly unavailable.

## Local real-recording webpage

Install the declared Python dependencies and start the local server from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m demo.audio_web_app
```

Open `http://127.0.0.1:5000` and upload a PCM or floating-point WAV file. The page accepts at most 12 MB and five minutes, holds the recording in process memory rather than writing it to disk, and provides an in-browser playback control. It downmixes as many as eight channels, resamples supported rates to 16 kHz, converts samples to PCM16 without loudness normalization, and divides the recording into balanced sequential windows of at most two seconds so a short final remainder is not judged alone. Each window then travels through the same Protocol v2 decoder, provenance, feature, and quality-decision path used by the synthetic demo.

The summary is `usable` only when every window passes, `partially_usable` when at least one window passes, and `no_usable_audio` when none pass. The per-window table remains authoritative because a usable section must not hide clipping, noise, silence, or an insufficient final window elsewhere in the recording.

The page requires the operator to confirm permission from recorded speakers before processing and can disable transcription for an acoustic-only check. This checkbox is an engineering safeguard, not a complete participant-consent system. The Flask development server binds to localhost by default and has no authentication, encryption, durable storage, participant management, or production deployment configuration. Do not expose it to a network or use it to collect research participants' recordings.
