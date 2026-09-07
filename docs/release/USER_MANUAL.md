# PSYCON user manual

This manual covers the current research prototype and its one-set group-discussion workflow. PSYCON does not diagnose stress or any mental-health condition. The Wrist Module measures only its wearer. The center Audio Module can separate conversation into recording-local speaker clusters, but overlapping or short speech may remain unknown, and the current application identifies at most one enrolled wearer.

## Before use

Do not put the system on a participant until the exact hardware revision has passed the Week 6 electrical, GSR, enclosure, calibration, one-hour, and six-hour checks. Use a protected undamaged LiPo cell, insulated terminals, battery restraint, and strain relief. Do not charge or connect wired external power while worn. Do not charge while GSR electrodes are attached.

For human research, confirm the approval ID, protocol version, parent or guardian consent where required, participant assent, separate audio and voice-profile choices, withdrawal status, retention period, and operator. Use anonymous participant and session codes. Stop if consent is absent or withdrawn.

## Software setup

Install Python dependencies and verify the repository:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-backend.txt
python -m pytest
npm --prefix protocol ci
npm --prefix protocol test
npm --prefix protocol run typecheck
```

Install Docker Desktop for the PostgreSQL and MinIO-backed server. Set non-default secrets before any deployment outside local development. Never commit `.env`, participant recordings, identity keys, tokens, or study data.

## Build and flash firmware

```powershell
python -m pip install platformio
python -m platformio run --project-dir firmware/wrist
python -m platformio run --project-dir firmware/ear
python -m platformio run --project-dir firmware/wrist --target upload
python -m platformio run --project-dir firmware/ear --target upload
```

Compilation does not prove sensor operation. The current Wrist firmware still publishes placeholder sensor values, so do not collect a research session until real MAX30102, ADS1115/GSR, MCP9808, and MPU6050 acquisition replaces them and passes the physical gates.

## Start the backend

```powershell
docker compose up --build -d
docker compose ps
```

Open `http://localhost:8000`. The readiness endpoint at `http://localhost:8000/api/v1/ready` must report ready before collection. Run the Week 6 simulated checks separately from participant data:

```powershell
python -m validation.api_validation --url http://localhost:8000
python -m validation.stress --url http://localhost:8000 --duration-seconds 3600
```

These checks do not pass physical hardware or battery requirements.

## One-set circle workflow

Use four to six fixed, numbered seats around the center Audio Module. Keep microphone distances similar, record the seating layout, and make a short sound check. Choose one focal participant for each session. Only that person wears the Wrist Module and, if separately consented, supplies exactly three clean 5 to 10 second enrollment clips.

Record a five-minute quiet baseline, then a 15 to 20 minute moderated discussion. Log the topic, room, noise, light, prompts, interruptions, overlap, late arrivals, and device events. The observer records evidence timestamps on the psychologist marksheet. Every participant supplies the approved momentary self-report before and immediately after the session if stress is an intended target. The behavioural marksheet is not stress ground truth.

Rotate the Wrist Module across later sessions so each participant becomes the focal wearer. Clean participant-contact surfaces using the material-approved method between wearers. Create a new anonymous session record for every run; never reuse IDs or relabel one participant's physiology as another participant's data.

## Audio analysis

For local file analysis, set `PSYCON_PROFILE_KEY` to a stable random secret of at least 32 characters. Set `HF_TOKEN` only after accepting the diarization model's terms, then run:

```powershell
python -m demo.audio_web_app
```

Open `http://127.0.0.1:5000`. Enroll only the focal wearer, upload the consented conversation, inspect quality and abstention reasons, and delete the encrypted profile when retention ends or the participant withdraws. Anonymous speaker numbers apply only inside that recording and must not be assumed to match seat numbers without manual verification.

## Dashboard, export, and backup

Use the session dashboard to check device status, sequence gaps, synchronization uncertainty, quality flags, jobs, features, inference, and errors. Do not hide missing data or override an abstention.

Create the session research export through the authenticated export endpoint or dashboard workflow. Verify its ZIP hash and manifest before copying it to the approved encrypted study store. The backend backup command and restore verification are documented in `docs/BACKEND.md`; test restoration before deleting any source copy.

## Replay and model evaluation

The deterministic replay path is:

```powershell
python -m backend.simulator --url http://localhost:8000 --scenario normal
```

Use `python -m research.run_study` only after marksheets, matching Wrist and Audio records, metadata, consent state, calibration references, and approval checks meet `docs/research/DATA_REQUIREMENTS.md`. Participant splits must remain fixed across physiology-only, speech-only, and combined comparisons.

## Safe shutdown

End acquisition first, wait for the device to report flushed buffers, close the backend session, and confirm later writes are rejected. Remove the wearable, disconnect GSR electrodes, and then switch off battery power. Charge only after the device is off and off-body. If shutdown, temperature, battery, GSR, or enclosure behavior differs from its accepted record, quarantine that build and open a corrective action.

Stop local services with:

```powershell
docker compose down
```

## Fault recovery

- If a sensor disappears, preserve the error log, isolate that sensor, and do not invent replacement values.
- If communication fails, remain within the measured queue limit, reconnect, and expose any sequence loss.
- If audio overlaps or diarization is uncertain, keep the speaker unknown and use manual timestamp review where consent permits.
- If the backend job fails, retain the immutable chunks and retry processing after correcting the service fault.
- If a participant withdraws, stop collection and follow the approved deletion and backup-removal procedure.
