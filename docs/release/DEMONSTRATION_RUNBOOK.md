# Demonstration and backup recording runbook

Run the physical demonstration only after the exact hardware revision passes all Week 6 gates. Until then, use the deterministic software demonstration and say that it uses generated packets.

## People and equipment

Assign one presenter, one operator, one safety observer, and one consent/data observer. Prepare the approved Wrist and Audio builds, charged protected cells, test records, offline laptop, local server, known-good cables for off-body programming only, cleaning materials, printed consent status, anonymous session code, and a second copy of the release archive. Backup hardware is optional only when its absence is declared.

## Preflight

1. Verify the release manifest, tracked source revision, hardware label, firmware versions, calibration IDs, runtime record, and open-risk report.
2. Inspect the cell, enclosure, strap, insulation, sensors, electrodes, microphone port, and connectors. Keep the charger disconnected.
3. Start the backend and confirm health, readiness, database, object storage, worker, dashboard, disk capacity, and local network.
4. Confirm consent for physiology, audio, transcription, and the optional voice profile. Confirm the deletion and withdrawal route.
5. Create a new anonymous session. Record the room, numbered seats, focal wearer, topic, and clock-check event.

Any failed item stops the physical demonstration.

## Live sequence

| Time | Action | Evidence shown |
| --- | --- | --- |
| 0:00 | State the research-only purpose and one-wearer limitation | Audience sees the non-diagnostic claim |
| 0:30 | Power each battery module independently | No wired power; boot and versions appear |
| 1:00 | Show Wrist initialization and I2C addresses | `0x57`, `0x68`, `0x18`, `0x48`; errors remain visible |
| 1:30 | Show Audio initialization | I2S capture, light input, quality, and buffer status |
| 2:00 | Record quiet baseline | Timestamped focal-wearer physiology and room context |
| 3:00 | Run a short consented two-speaker exchange | Audio, Wrist, light, motion, clock, and sequence state |
| 5:00 | Introduce one planned short communication interruption | Queue behavior, visible gap if capacity is exceeded, and recovery |
| 6:00 | Process the session | Feature provenance, quality, uncertainty, confidence, or abstention |
| 7:00 | Open the dashboard | Session, devices, streams, status, jobs, features, and errors |
| 8:00 | Create and verify the research export | ZIP hash, manifest, file sizes, and hashes |
| 9:00 | Delete the optional wearer profile | Encrypted profile lifecycle and confirmation |
| 9:30 | Shut down | Buffers flush, session closes, later writes fail, power turns off |

Never unplug a worn device to simulate failure. Use the tested wireless interruption method. Do not provoke a battery brownout, short, GSR fault, or thermal event during a participant demonstration.

## Software-only fallback

```powershell
docker compose up --build -d
python -m backend.simulator --url http://localhost:8000 --scenario normal
python -m validation.api_validation --url http://localhost:8000
python -m demo.audio_demo
python -m release_tools.package --output-dir release-output
```

Label every screen and spoken result as simulated or generated. The WESAD model is a public-dataset development baseline, not a result from the displayed hardware or discussion participants.

## Backup recording

Record the complete live sequence in one continuous take where practical. Frame the hardware label, off-body charger state, boot output, sensor status, dashboard URL, anonymous session ID, quality and uncertainty, export hash, profile deletion, and shutdown. Do not show names, tokens, `.env`, participant codes linked to identities, raw consent forms, or private recordings.

Create a recording record containing date, operator, participants' media consent, hardware and firmware revisions, release commit, session ID, duration, file hash, storage location, redactions, result, faults, and corrective actions. Review the recording without network access before copying it to the approved presentation store.

## Acceptance

The live and recorded demonstrations pass only when every planned step is visible, outputs retain their quality and non-diagnostic labels, the export verifies, shutdown completes, and no safety or privacy rule is violated. A software-only recording is useful fallback evidence but cannot pass the physical demonstration gate.
