# Reproducibility Matrix

This matrix defines the software checks required from a clean checkout. Hardware measurements are tracked separately in the seven-week plan.

| Surface | Command | Clean-checkout expectation |
| --- | --- | --- |
| Python | `python -m pip install -r requirements.txt` then `python -m pytest` | Repository tests pass; the three raw-WESAD integration tests skip when the licensed external dataset is absent |
| Protocol TypeScript | `npm --prefix protocol ci`, `npm --prefix protocol test`, `npm --prefix protocol run typecheck` | All tests and type-checking pass |
| Protocol security | `npm --prefix protocol audit` | Zero known dependency vulnerabilities |
| Protocol Python/C++ | Included in `python -m pytest tests/protocol` | Python and host C++ decode the same v2 fixtures; the corrupt fixture is rejected |
| Week 3 audio demo | `python -m demo.audio_week3_demo` | Generated tone and speech-like cases are usable; silence, impulse, clipping, noise, missing input, and CRC corruption produce explicit abstention states; JSON is written under `results/demo/` |
| Real-WAV upload page | `python -m demo.audio_web_app`, then open `http://127.0.0.1:5000` | The local page accepts consented WAV uploads and reports quality, local transcription, and language features; automated tests cover decoding, downmixing, resampling, quality gating, transcription states, language abstention, successful analysis, and invalid-file errors |
| Audio firmware | `python -m platformio run --project-dir firmware/ear` | ESP32 firmware compiles |
| Wrist firmware | `python -m platformio run --project-dir firmware/wrist` | ESP32 firmware compiles |
| Engineering PRD | Compile `docs/engineering_prd/main.tex` using the commands in its README | PDF rebuild succeeds; placeholder bibliography items remain a release blocker |

## External WESAD data

Raw WESAD subject files are not committed. Place legitimately obtained files at:

```text
data/raw/wesad/S2/S2.pkl
data/raw/wesad/S3/S3.pkl
...
```

With raw data present, `python main.py --limit-subjects 1` exercises loading, preprocessing, feature extraction, and model training. Without it, deterministic synthetic tests still verify label mapping, windowing, features, personalization, model export, and rule-baseline behavior.

## Protocol fixtures

Run `python protocol/tools/generate_fixtures.py` to regenerate the canonical binary fixtures. The generator is deterministic, and Python, TypeScript, and C++ tests consume the same files under `protocol/fixtures/`.
