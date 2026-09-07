# Reproducibility Matrix

This matrix defines the software checks required from a clean checkout. Hardware measurements are tracked separately in the seven-week plan.

| Surface | Command | Clean-checkout expectation |
| --- | --- | --- |
| Python | `python -m pip install -r requirements.txt` then `python -m pytest` | Repository tests pass; the three raw-WESAD integration tests skip when the licensed external dataset is absent |
| Protocol TypeScript | `npm --prefix protocol ci`, `npm --prefix protocol test`, `npm --prefix protocol run typecheck` | All tests and type-checking pass |
| Protocol security | `npm --prefix protocol audit` | Zero known dependency vulnerabilities |
| Protocol Python/C++ | Included in `python -m pytest tests/protocol` | Python and host C++ decode the same v2 fixtures; the corrupt fixture is rejected |
| Audio demo | `python -m demo.audio_demo` | Generated tone and speech-like cases are usable; silence, impulse, clipping, noise, missing input, and CRC corruption produce explicit abstention states; JSON is written under `results/demo/` |
| Real-audio upload page | `python -m demo.audio_web_app`, then open `http://127.0.0.1:5000` | The local page accepts consented WAV, MP3, and OGG uploads and reports quality, local transcription, speaker analysis, and language features; automated tests cover decoding, downmixing, resampling, quality gating, transcription states, speaker abstention, language abstention, successful analysis, and invalid-file errors |
| Audio firmware | `python -m platformio run --project-dir firmware/ear` | ESP32 firmware compiles |
| Wrist firmware | `python -m platformio run --project-dir firmware/wrist` | ESP32 firmware compiles |
| Week 6 validation logic | `python -m pytest tests/validation` | Evidence-source rules, ordered integration gates, failure-scenario assessment, stress metrics, report generation, export verification, and risk mappings pass |
| Week 6 live API scenarios | Start Compose, then run `python -m validation.api_validation --url http://localhost:8000` | Nine simulated scenarios, processing, synchronization, features, inference, dashboard access, and export integrity pass; this cannot satisfy a physical gate |
| Week 6 simulated stress | Start Compose, then run `python -m validation.stress --url http://localhost:8000 --duration-seconds 3600` | The simulated transport path completes its requested duration without rejected packets; device memory, radio, temperature, battery, and physical loss remain unmeasured |
| Week 6 evidence report | `python -m validation.report --evidence <evidence.json> --output-dir validation-output/report` | JSON and Markdown reports are produced; exit code 2 is expected while required evidence or ordered stages remain open |
| Week 7 release tooling | `python -m pytest tests/release_tools` | Version rules, privacy exclusions, hashes, manifest verification, and deterministic ZIP output pass |
| Week 7 candidate | `python -m release_tools.package --output-dir release-output`, then `python -m release_tools.package --verify release-output/release-manifest.json` | A candidate archive and manifest are created from tracked files; the verification reports no missing, changed, or hash-mismatched included file |
| Engineering PRD | Compile `docs/engineering_prd/main.tex` using the commands in its README | PDF rebuild succeeds; placeholder bibliography items remain a release blocker |

## External WESAD data

Raw WESAD subject files are not committed. Place legitimately obtained files at:

```text
data/raw/wesad/S2/S2.pkl
data/raw/wesad/S3/S3.pkl
...
```

With raw data present, `python main.py --limit-subjects 1` exercises loading, preprocessing, feature extraction, and model training. Without it, deterministic synthetic tests still verify label mapping, windowing, features, personalization, model export, and rule-baseline behavior.

## Week 5 study data

The repository contains no Week 5 study dataset or generated metric. `python -m pytest tests/research` verifies the dataset, metadata, splitting, evaluation, and reporting code with unit-test values only. Run approved marksheets and matching PSYCON sessions with `python -m research.run_study` after completing the checks in `docs/research/DATA_REQUIREMENTS.md`.

Approved participant files belong in the encrypted study store rather than this repository; `data/studies/` and `results/studies/` are ignored as a second guard against accidental commits.

`docs/WEEK_5_IMPLEMENTATION.md` records the implemented behavior, file ownership, build-plan coverage, current test evidence, and open empirical gates.

## Week 7 release

`release_tools/versions.json` is the candidate version freeze and blocker list. The packager excludes checked-in audio files, `.env`, study directories, and its own output from distribution. It evaluates tracked cleanliness because unrelated untracked local files are outside the candidate archive.

The output is reproducible for a fixed manifest because ZIP entry order, timestamps, permissions, and compression settings are fixed. The generated manifest timestamp changes between separate builds, so archive hashes from builds at different times are not expected to match. Preserve and distribute the manifest created with the approved archive.

## Week 6 physical evidence

`docs/validation/WEEK_6_RUNBOOK.md` defines the five ordered integration stages, calibration procedures, assembly checks, electrical measurements, one-hour stress test, six-hour battery test, safety rules, and evidence fields. The checked-in templates contain no measurements and do not establish a pass.

Keep raw photographs, serial captures, instrument exports, and runtime logs in the controlled project evidence store. Supply a JSON array of completed records to `validation.report`; a physical procedure passes only with `physical_measurement` evidence tied to a real hardware revision and artifacts.

## Protocol fixtures

Run `python protocol/tools/generate_fixtures.py` to regenerate the canonical binary fixtures. The generator is deterministic, and Python, TypeScript, and C++ tests consume the same files under `protocol/fixtures/`.
