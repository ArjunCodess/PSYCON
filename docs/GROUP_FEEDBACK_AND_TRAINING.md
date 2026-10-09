# Group feedback and PSYCON training

Historical workflow. This document records the earlier implementation and does not define the current behavioral instrument. Use [the current startup guide](START_HERE.md), [behavioral direction](PSYCON_VISION.md), [instrument architecture](INSTRUMENT_ARCHITECTURE.md), and [coverage record](INSTRUMENT_STATUS.md) for new work.

Upload a discussion video, review its speaker assignments, and submit its spreadsheet. PSYCON saves the data, then prepares feedback for each participant. Training runs separately, when you choose to run it.

## Use the group page

Start the website, Ollama, and one worker using the [startup instructions](../README.md#open-the-web-app). Open [Group research](http://127.0.0.1:8000/group).

1. Upload the video and check the numbered faces. Review uncertain speech in the original recording before assigning it. Run the PSYCON analysis when you need its confirmed speech intervals and training features.
2. Upload a UTF-8 CSV under 2 MB. Participant numbers must match the marked frame. Use `participant,class,A` through `T`, with scores from `0` to `4` or `N/O`. The [spreadsheet guide](GROUP_SESSION_CSV.md) explains the rubric.
3. Enter the topic, setting, and discussion goal. Everyone receives feedback under this same context. The class column stays a spreadsheet label, so PSYCON does not treat it as a profession or a personality type.
4. Submit the spreadsheet and stay on the feedback page while the worker runs. Each person gets reviewer-supported strengths, areas to improve, and practical exercises. The page states whether the local AI or rubric rules supplied the exercises.
5. Select **Review recording and context** to change the context, then **Save context and update feedback**. Upload a corrected spreadsheet to replace the current labels. Use **Generate feedback again** to retry interrupted processing.

The session URL restores saved feedback when reopened. **Upload another recording** starts the next session when you're ready.

A score of `0` means the reviewer did not observe that rubric behavior despite an opportunity. Higher scores describe its occurrence or effect. `N/O` supports no conclusion. PSYCON does not turn the marksheet into an overall grade or a diagnosis.

The CSV has no event timestamps. Feedback cites rating rows; confirmed speech excerpts keep original video times. These excerpts help review the conversation, but do not prove each rating. The LLM suggests exercises from human ratings. It does not add observed events or rewrite scores. Review its suggestions before use.

## What the database stores

PostgreSQL already stores sessions, participant slots, face features, voice profiles, speaker intervals, transcription results, and research marksheets. This extension adds two tables.

| Table | Stored data |
| --- | --- |
| `training_labels` | Current participant, class, item, and human score for each uploaded rating. |
| `group_label_imports` | Original CSV text, parsed rows, file name, hash, uploader, date, and rubric version for each import. |
| `group_feedback` | Shared context, processing state, input hash, participant feedback, source references, and model digest or fallback reason. |

Replacing labels and recording the import happen in one transaction. Invalid uploads leave previous labels intact. Feedback uses the existing group job queue, so the upload request does not wait for the LLM. Earlier CSV imports follow the existing research retention policy.

Changed ratings, context, speaker evidence, or participant availability make feedback stale and hide its claims. Worker writes check the request revision, so an old job cannot replace newer context. Session deletion removes imports and feedback through database cascades. Withdrawal excludes that person from new reports and training snapshots.

Media files keep the existing object-storage policy. Their references and analysis results live in PostgreSQL; the database does not contain copies of the video or audio files.

## Train from saved data

From PowerShell in the project folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 train-group
```

The launcher supplies local database settings. The separate script, `backend/group/train.py`, reads a consistent PostgreSQL snapshot and trains the existing PSYCON face-and-voice classifiers for the A through T ratings. This command does not train Qwen.

Training uses human spreadsheet scores, completed recordings, active participants, recorded session consent, and current PSYCON voice profiles with at least three usable seconds. Profiles must pass the existing identity, quality, and feature-version checks. Predictions and AI feedback never supply labels. `N/O` is excluded from fitting.

Each item needs five independent recording groups and five nonzero scores. Its training split also needs two score values. Explicit research-person links and identical source hashes connect recordings into one split, so they cannot appear on both sides of evaluation. Anonymous slot numbers stay local to each recording. Unlinked repeat participants can still affect independence, so confirm person links before treating evaluation as participant-independent.

Each run creates a folder under `.runtime/models/psycon-group/`, saves an `item-A.joblib` style file for each fitted item, and writes `manifest.json` last. The manifest records the dataset hash, label references, source hashes, split assignments, seed, artifact hashes, model version, and held-out metrics. A folder without its manifest is incomplete.

Sparse items stay unavailable with a reason. If no item can fit, the script exits with code `2`; a run with examples still writes its manifest so you can see what is missing. Training saves research artifacts and does not replace the application's active model. Retrain after data removal and retire old artifacts under the research retention policy.

To use another directory or seed, set your database environment first and run:

```powershell
.runtime\venv\Scripts\python.exe -m backend.group.train --output-root .runtime/models/psycon-group --seed 42
```

## API and inference

| Route | Action |
| --- | --- |
| `POST /api/v1/group-sessions/{id}/labels` | Save CSV ratings and queue feedback. Multipart `topic`, `setting`, and `objective` fields set shared context. |
| `GET /api/v1/group-sessions/{id}/feedback` | Read feedback or processing state. Stale reports return no participant claims. |
| `POST /api/v1/group-sessions/{id}/feedback` | Generate using a `context` object. Set `retry` to `true` to replace an interrupted request. |

Operators and psychologists can upload and regenerate. Reviewers can read. Existing group authentication and local development behavior still apply.

The interpreter uses the personal coach's private Ollama endpoint and pinned digest. It processes bounded rating windows with an 8K context limit. Structured output must cite supplied rating IDs. Context text is untrusted input. Invalid references, a changed digest, truncated output, or an unavailable server fall back to rubric exercises. There is no cloud fallback. AI exercises are proposals for review, not validated semantic event detections.

Tests cover persistence, stale output, revision conflicts, withdrawal, deletion, reviewer access, unsupported LLM references, artifact loading, and split leakage. The database test uses `PSYCON_COMMUNICATION_TEST_DATABASE`, creates synthetic sessions, and removes them afterward.
