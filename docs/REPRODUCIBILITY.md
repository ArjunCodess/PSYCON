# Current audio-first application

The active application uses only PostgreSQL. Install `requirements-instrument.txt`, configure the ignored `PSYCON_DATABASE_URL`, run `python run_psycon.py migrate`, then run `python run_psycon.py web` and `python run_psycon.py worker`. The local managed interpreter is `.runtime/venv/Scripts/python.exe`. No application/test SQLite fallback exists; `migrate-source` is the one-time read-only importer.

Run `python -m pytest tests/backend/test_instrument.py tests/backend/test_instrument_training.py tests/backend/test_instrument_workflow.py` against an available local PostgreSQL database. These fixtures create disposable `psycon_test_*` schemas, run real fitting with explicitly synthetic labels and remove their records. They exercise imports and revisions, source ancestry, mappings, frozen splits, roles, leases, retries, cancellation, generation attempts, portable models, deployment, withdrawal, exports and coordinated database/local-file restoration. Run `python -m pytest` for the broader compatibility suite. Optional external-service and licensed-data tests may skip; record those skips separately.

Check vanilla browser scripts with `node --check backend/static/instrument.js` and `node --check backend/static/instrument_workflow.js`. Inspect the current interface through the project-native browser on desktop and mobile; HTTP checks alone do not certify interaction. Use a separately labeled synthetic database for UI model demonstrations.

Freeze [dataset protocol](DATASET_PROTOCOL.md) and the exact model/snapshot versions before an evaluation. Model training and the matched A/B/C LLM experiment are separate analyses. Export and restore through the [operator runbook](POSTGRES_TRAINING_RUNBOOK.md); private exports contain human answers, source documents and metadata, so they are not public artifacts.

The matrix below describes historical hardware and compatibility checks. It does not reintroduce physiology or face dependencies into the active application.

# Reproducibility Matrix

This matrix defines the software checks required from a clean checkout. Hardware measurements are tracked separately in the seven-week plan.

The current direction and release limits are in [implementation status](IMPLEMENTATION_STATUS.md). Set `PSYCON_COMMUNICATION_TEST_DATABASE` to a local PostgreSQL URL for the real lifecycle test; otherwise it skips. Model-gated and licensed-dataset tests may also skip when their required inputs are unavailable.

| Surface | Command | Clean-checkout expectation |
| --- | --- | --- |
| Python | `python -m pip install -r requirements.txt` then `python -m pytest` | Repository tests pass; the three raw-WESAD integration tests skip when the licensed external dataset is absent |
| Protocol TypeScript | `npm --prefix protocol ci`, `npm --prefix protocol test`, `npm --prefix protocol run typecheck` | All tests and type-checking pass |
| Protocol security | `npm --prefix protocol audit` | Zero known dependency vulnerabilities |
| Protocol Python/C++ | Included in `python -m pytest tests/protocol` | Python and host C++ decode the same v2 fixtures; the corrupt fixture is rejected |
| Audio demo | `python -m demo.audio_demo` | Generated tone and speech-like cases are usable; silence, impulse, clipping, noise, missing input, and CRC corruption produce explicit abstention states; JSON is written under `results/demo/` |
| Real-audio upload page | `python -m demo.audio_web_app`, then open `http://127.0.0.1:5000` | The local page accepts consented WAV, MP3, and OGG uploads and reports quality, local transcription, speaker analysis, and language features; automated tests cover decoding, downmixing, resampling, quality gating, transcription states, speaker abstention, language abstention, successful analysis, and invalid-file errors |
| Audio firmware | `python -m platformio run --project-dir firmware/ear` | ESP32 firmware compiles |
| Communication software | `python -m pytest tests/backend/test_communication.py tests/backend/test_communication_postgres.py tests/validation/test_communication_semantics.py` | Private access, enrollment, deduplication, retention, future exclusion, snapshot lineage, baselines, roles, correction/deletion, and semantic gates pass. |
| Complete containers | `docker compose build api worker minio` | Web, GPU worker, and local object-store images build; human/physical gates remain separate. |
| Semantic validation | `python -m validation.communication_semantics reviewed.json validation.json` | Invalid references/duplicate exchanges are rejected; inadequate role coverage, precision, or review count leaves types unavailable. |
| Wrist firmware | `python -m platformio run --project-dir firmware/wrist` | ESP32 firmware compiles |
| Week 6 validation logic | `python -m pytest tests/validation` | Evidence-source rules, ordered integration gates, failure-scenario assessment, stress metrics, report generation, export verification, and risk mappings pass |
| Week 6 live API scenarios | Start Compose, then run `python -m validation.api_validation --url http://localhost:8000` | Nine simulated scenarios, processing, synchronization, features, inference, dashboard access, and export integrity pass; this cannot satisfy a physical gate |
| Week 6 simulated stress | Start Compose, then run `python -m validation.stress --url http://localhost:8000 --duration-seconds 3600` | The simulated transport path completes its requested duration without rejected packets; device memory, radio, temperature, battery, and physical loss remain unmeasured |
| Week 6 evidence report | `python -m validation.report --evidence <evidence.json> --output-dir validation-output/report` | JSON and Markdown reports are produced; exit code 2 is expected while required evidence or ordered stages remain open |
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

The repository contains no approved group-observation dataset and no binary Week 5 study result. `python -m pytest tests/research tests/backend/test_group_workflow.py` checks the dataset code, the binary comparison, and the group workflow with synthetic values only. Group collection uses consent version `group-consent-2.0` and marksheet version 4.0 (0–4 or N/O). The binary runner remains `python -m research.run_study` for the earlier device path.

Approved participant files belong in the encrypted study store rather than this repository; `data/studies/` and `results/studies/` are ignored as a second guard against accidental commits.

`docs/WEEK_5_IMPLEMENTATION.md` records the implemented behavior, file ownership, build-plan coverage, current test evidence, and open empirical gates.

## Week 6 physical evidence

`docs/validation/WEEK_6_RUNBOOK.md` defines the five ordered integration stages, calibration procedures, assembly checks, electrical measurements, one-hour stress test, six-hour battery test, safety rules, and evidence fields. The checked-in templates contain no measurements and do not establish a pass.

Keep raw photographs, serial captures, instrument exports, and runtime logs in the controlled project evidence store. Supply a JSON array of completed records to `validation.report`; a physical procedure passes only with `physical_measurement` evidence tied to a real hardware revision and artifacts.

## Protocol fixtures

Run `python protocol/tools/generate_fixtures.py` to regenerate the canonical binary fixtures. The generator is deterministic, and Python, TypeScript, and C++ tests consume the same files under `protocol/fixtures/`.
