# Build verification, 13 October 2026

The paper builder completed with a fifteen-page paper and exactly two-page synopsis. All rebuilt paper/figure PDFs were compared page by page with committed copies and rendered identically; timestamp-only changes were discarded.

The existing MiKTeX toolchain compiled the forty-page engineering document, three-page group-discussion report, five-page observation marksheet, two-page interpretation guide and one-page blank group-session consent template. Build outputs remain under `.runtime/full-build-2026-10-13/`; completed signed consent forms and source-rating scans remain private. Historical engineering claims are not certified by compilation.

Both PlatformIO ESP32 targets compiled successfully. Ear-module firmware used 17.0% RAM and 82.6% flash; wrist-module firmware used 11.1% RAM and 47.0% flash. This is compilation evidence, not a physical-device test.

Protocol TypeScript typechecking and all twenty Vitest tests passed. Both frontend behavior scripts passed. Python bytecode compilation succeeded for `backend`, `research`, `ml` and `run_psycon.py`.

The local pytest run passed 381 tests with five optional checks skipped, out of 386 collected. The three PostgreSQL-dependent instrument suites were excluded: `test_instrument.py`, `test_instrument_training.py` and `test_instrument_workflow.py`. An initial run omitted the wrong third filename and encountered a missing-database fixture error; it was stopped and the corrected local suite completed. No application failure is attributed to that missing test database, and this does not claim a complete integration rerun.

Reproduce the local suite with:

```powershell
.runtime/venv/Scripts/python.exe -m pytest tests --ignore=tests/backend/test_instrument.py --ignore=tests/backend/test_instrument_training.py --ignore=tests/backend/test_instrument_workflow.py -q --maxfail=1
```

The Docker daemon probe did not respond and was stopped. An initial direct Compose invocation lacked the path-mapping environment variable; a retry loaded the project environment and supplied that mapping, but remained unresponsive and was stopped. No container rebuild is claimed. The local failure record is retained in `.runtime/full-build-2026-10-13/docker-build.log`.

Presentation numbering was checked to contain exactly sections 1 through 25. The latest instruction supersedes the earlier request to leave slides uncommitted. The versioned emergency-audit reports contain aggregate results and anonymized examples; private weights, source manifests, original recordings, signed forms and identifiable rating scans are excluded.
