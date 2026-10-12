# Build verification, 13 October 2026

## Latest maximum-defensible documentation build

`python paper/build.py` rebuilt a sixteen-page paper and exactly two-page synopsis with resolved citations/references and no overflowing boxes. Abstracts contain 234 and 260 whitespace-separated words. All paper pages were rendered into a contact sheet; the new audit table/figure pages and both synopsis pages were inspected at reading size. The source presentation retains exactly 25 numbered content slides. The new figure reads only the committed aggregate audit and checks the 402-rating denominator.

The LaTeX plugin compiler used the existing MiKTeX/latexmk toolchain to rebuild the engineering document at 41 pages. An initial long aggregate-file path overflowed a column; using a breakable path fixed it, and the final log has no overfull or unresolved-reference warnings. The changed audit page was rendered and inspected. The rebuilt PDF is versioned with its source.

An initial paper-build attempt with the ML virtual environment failed because that environment lacks PyMuPDF. The system Python has the document libraries and completed the build; documentation therefore uses `python paper/build.py`, while model reproduction retains the ML virtual environment. Earlier unchanged figure PDFs rendered identically to their committed versions, so timestamp-only changes were discarded.

The aggregate release was checked against the private saved comparison: all 29 procedure records retain both cohort counts, exact-match numerators, MAE and class support. Private individual IDs, raw notes and prediction rows are excluded. The earlier audit research suite passed 82 tests with one ffmpeg-dependent skip; this documentation build does not claim a new model, hardware, Docker, PostgreSQL or human-study run. The source-score output remains retrospective development with no independent final test. No existing reference result was overwritten.

## Earlier full build

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
