# Running and using PSYCON

Start the local services, keep one worker running, and open the personal coach. That is the normal setup. This guide covers the software installed in this PSYCON folder.

The pilot accepts English recordings. The speech models and local AI run on this computer. Human testing still needs to confirm how accurate and useful the coaching is.

## Pick the right page

| What you want to do | Where to go | What you need |
| --- | --- | --- |
| Enroll, upload conversations, and review your history | [Personal coach](http://127.0.0.1:8000/coach) | Your wearer token |
| Review someone's history with permission | The same personal coach | Their reviewer grant token |
| Work with group recordings and marksheets | [Group research console](http://127.0.0.1:8000/group) | Research access under the existing group workflow |
| Inspect device sessions, worker status, and exports | [Device dashboard](http://127.0.0.1:8000/) | The operator credential |
| Inspect research objects and storage | [MinIO console](http://127.0.0.1:9001) | The local storage administrator login |
| Check the database and object store connection | [Readiness check](http://127.0.0.1:8000/api/v1/ready) | Open it in the browser |

Wearer tokens, operator credentials, and sharing tokens have different jobs. Use a wearer token for your own coach. A context-only token belongs in an AI application's API request, so it cannot open the coach.

## Start the software

Open Docker Desktop and wait for its engine to start. Then open PowerShell in the project folder:

```powershell
cd C:\Users\USER\Desktop\code\PSYCON
```

In that terminal, run these commands in order:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 services
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 ollama
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 web
```

The first command starts PostgreSQL and MinIO. They store records and research files. The second starts Ollama in the background. The third starts the website and keeps the terminal occupied. Leave it open.

Open a second PowerShell terminal in the same folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 worker
```

Leave this terminal open too. The website accepts uploads, but the worker processes enrollment and recordings. A file can stay queued if the worker is stopped. Run one inference worker on this GPU.

Now open [the coach](http://127.0.0.1:8000/coach). If the website is already running and the readiness check says `ready`, use that server. Starting another server on port 8000 will fail.

The installed model is already pinned. Run the following only after changing or reinstalling the local model:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 configure
```

Restart the web server and worker after configuration changes. This command preserves the existing profile encryption key.

## Create an account once

The current pilot uses access tokens. An operator creates the account, and the wearer uses the returned token to sign in. There is no public signup or password recovery screen yet.

In another PowerShell terminal in the project folder, run:

```powershell
$env:PSYCON_DATABASE_URL = 'postgresql://psycon:psycon@127.0.0.1:5432/psycon'
$env:PSYCON_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:PSYCON_S3_SECRET_KEY = 'psycon-local-object-secret'
.runtime\venv\Scripts\python.exe -m backend.communication.runtime create-wearer --label 'My pilot account' --role general
```

Those connection values belong to this local development setup. The command prints the account ID and token. Save the token in a password manager, then enter it in **Wearer access token** on the coach page.

Create a separate account for each person. Reuse your account for later recordings so your history stays together. A new account starts a new history. If you lose the token, contact the operator; the current pilot cannot recover it through the browser.

## Follow the personal coaching flow

1. **Set your role and consent.** Choose your role under Profile and consent, confirm permission to process the conversations, and save. General coaching works for everyone. Other roles adjust the focus and practice advice.

2. **Enroll your voice.** Select three clear recordings of your voice, each 5 to 10 seconds long. Confirm enrollment consent and choose Enroll my voice. The worker processes them. Use Refresh history until the account says Voice enrolled.

3. **Add a real conversation.** Choose a WAV, MP3, or OGG file under 32 MB. Enter its actual date and time, conversation type, setting, and microphone. Add a topic, relationship, and objective if they help explain the exchange. Then choose Analyze conversation.

4. **Check the result.** Refresh history while the job moves from queued to processing to complete. Read the measured observations and evidence. An uncertain voice match stays outside your personal baseline. If the context is wrong, use Correct context.

5. **Build your baseline.** Upload more comparable conversations. Keep the same names for the same setting and microphone. The starting rule is five eligible conversations across at least three UTC dates, with 30 minutes of usable speech from you. Total recording time is different from usable wearer speech.

6. **Look for repeated changes.** After the baseline is ready, later recordings can be compared with it. A recurring pattern needs support from at least three later independent conversations. Eight conversations can be a useful starting target, but reaching eight alone does not guarantee a pattern.

7. **Practice one adjustment.** Review the supporting examples before acting on advice. Choose one available measurement under Practice goals. PSYCON saves the earlier reference and waits for at least three comparable conversations that happened after goal creation before reporting a later comparison.

8. **Review the change.** Check the measurement, examples, and context together. A change in pace or speaking share does not prove that listeners understood more, or that coaching caused the change. Decide whether the adjustment actually helped the conversation you were trying to have.

Use different real conversations. Repeated copies of the same file are deduplicated. Re-exporting that recording still does not make it a new conversation.

### What the labels mean

| Label | What to do |
| --- | --- |
| Queued | Keep the worker running and refresh later. |
| Processing | Wait for local analysis to finish. |
| Complete | Review the measurements, identity result, and evidence. |
| Failed | Read the error. Retry while the original upload still exists, or upload a new recording. |
| Baseline building | Keep collecting eligible recordings in the same context. |
| Unavailable role observation | Use the available measurements. The required evidence or validated detector is missing. |
| Awaiting validation | Local AI ran, but its semantic claims still need independent evaluation. |
| Reference invalidated | A correction or deletion changed the goal's earlier evidence. Create a new goal when a suitable baseline is ready. |

Overlap means two people spoke at once. Calling it an interruption needs more evidence. Role interpretations also need a reviewed model evaluation before they appear automatically.

## Correct, share, and delete

Current correction buttons open a JSON text box. Context correction edits the recorded setting and other fields. Event correction labels a retained example, such as acknowledgement. Use the evidence ID shown beside the excerpt. The [role guide](COMMUNICATION_ROLE_RUBRICS.md) explains paired events and their two references.

Corrections rebuild the affected reports and invalidate earlier goal references. A few corrected excerpts cannot describe every event in a deleted transcript, so PSYCON removes that conversation's automatic semantic rates. Its acoustic measurements remain.

Choose Download my AI context to save a small JSON file for another application. It contains supported patterns, goals, dates, counts, uncertainty, and limited session context. It excludes audio, voice embeddings, and evidence text.

Under sharing, create a reviewer grant for a person who should read your history. Create a context grant for an AI application that should read only the context API. Both expire after seven days, and you can revoke them sooner. Share a grant token through your chosen private channel, never your wearer token.

For an authorized context request, use `GET /api/v1/communication/context` with `Authorization: Bearer <context-grant-token>`. The [API reference](COMMUNICATION_ARCHITECTURE.md#http-interface) covers the other routes.

Delete conversation removes one personal record and updates its dependent reports. Delete my profile and history revokes account access and removes the personal history and enrollment. Keep the worker running so failed cleanup can retry. Revocation stops future access; a context file someone already downloaded cannot be recalled.

Successful personal processing deletes the uploaded media and full transcript. Retained evidence appears as text with original timing. Failed raw uploads expire after 24 hours through worker cleanup. Shared research recordings follow their existing policy.

## Use the research and device paths

The same web server and worker support the existing research tools. In the [group console](http://127.0.0.1:8000/group), submit the recording and review the numbered faces. Confirm the required consent and assignments, run the selected analysis, then review uncertain voice intervals. Submit the marksheet CSV for that same recording when its human ratings are ready. The [spreadsheet guide](GROUP_SESSION_CSV.md) explains the file, and the [group runtime notes](psycon_group_runtime.md) explain attribution. Human ratings remain separate from automated coaching.

For guarded group voice analysis, use the built GPU container worker. It includes the face models and TalkNet weights. Stop the host worker with Ctrl+C first, keep the host website running, then run this in the project folder:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local.yml run --rm --no-deps -e PSYCON_OLLAMA_URL=http://host.docker.internal:11434 worker
```

This worker uses the same local database and personal upload folder. It reaches the host Ollama service through the supplied address. The command starts one worker without starting a second website. Return to the normal host worker after stopping it if you prefer that setup for personal uploads.

A group participant enters a personal history only after an operator confirms who they are and creates a source link. Participant 1 in two videos is not an identity match. Completed device sessions also need an explicit profile link and acceptable timing before import. The [source-link instructions](COMMUNICATION_COACH.md#api-and-existing-sources) explain those operator steps.

Use the [device dashboard](http://127.0.0.1:8000/) to inspect ingestion, session status, worker status, and exports. Physical wearable capture remains a separate validation stage. Start with uploaded recordings for the personal pilot.

For a software-only device demo, keep the web server and worker running, then run:

```powershell
.runtime\venv\Scripts\python.exe -m backend.simulator --url http://127.0.0.1:8000 --scenario normal
```

This creates simulated device credentials and a session, sends test packets, and queues processing. Inspect the result in the device dashboard. Its default operator credential is the local development value `psycon-local-operator`. A custom operator setup needs `--operator-token` with its own credential. See [the backend guide](BACKEND.md) for failure scenarios and exports.

The MinIO console uses `psycon` and `psycon-local-object-secret` in this local development setup. PostgreSQL is at `127.0.0.1:5432`, with database, user, and password `psycon`. These administrator values are for this machine's development services. Wearers use their private tokens instead.

For the existing WESAD experiments, place the permitted dataset in the paths listed in [reproducibility](REPRODUCIBILITY.md#external-wesad-data), then run `.runtime\venv\Scripts\python.exe main.py --limit-subjects 1`. That runs the stress research pipeline. Its predictions do not determine personal communication interpretations. The same document lists the study runners, evaluation tools, and report commands.

## Find files and check problems

| Location | What it holds |
| --- | --- |
| `.runtime/python` and `.runtime/venv` | The working Python interpreter and installed packages |
| `.runtime/ollama`, `.runtime/node`, and `.runtime/bin` | Ollama, Node/npm, and media tools |
| `.runtime/models` | Local AI and speech model caches |
| `.runtime/services` | PostgreSQL and MinIO data |
| `.runtime/logs` and `.runtime/tmp` | Saved runtime logs and temporary files |
| `.psycon-private-spool` | Encrypted personal uploads waiting for processing or cleanup |
| `.env` | Local settings and the profile encryption key |

Keep `.env` private and preserve its encryption key. Replacing the key makes existing encrypted enrollment and pending uploads unreadable. Keep temporary personal media out of backups.

If the page will not open, check the web terminal. If readiness is unavailable, start Docker Desktop and rerun the services command. If enrollment or uploads stay queued, check the worker terminal. If Ollama reports a port conflict, another runtime is already using port 11434. Use the project-local runtime rather than starting a second copy.

For a software check, run:

```powershell
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 test
powershell -ExecutionPolicy Bypass -File release_tools/local-runtime.ps1 protocol-test
```

The [technical runbook](COMMUNICATION_COACH.md) covers database integration tests and deeper checks. Passing tests confirms software behavior. The human pilot and semantic accuracy review are separate work.

To stop a web server or worker you started in a terminal, press Ctrl+C there. The background Ollama process and Docker services continue running. To stop the local database and object store without deleting their data, use:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local.yml stop postgres minio
```

Keep both Compose files in that command. The local override points at the data inside this project.

## The simpler user system

The current coach puts its forms on one page. The proposed design gives users a clearer path through setup, conversations, and practice. Read [the user-system design](USER_SYSTEM.md) for the screens, behavior, and changes still needed.
