# Week 4 backend and local demo

The Week 4 software is a cloud-ready local stack. Hardware sends authenticated Protocol v2 packets to a stateless HTTP service; PostgreSQL holds transactional metadata and processing state; S3-compatible object storage holds immutable raw packets and exports. The local demo uses MinIO, while a later deployment can use Cloudflare R2, Amazon S3, DigitalOcean Spaces, or another S3-compatible provider without changing object keys or repository records.

The hardware is not required to exercise this contract. `backend.simulator` creates a session, provisions simulated Wrist and Audio credentials, performs clock exchanges, posts status, uploads real Protocol v2 bytes, and queues processing through the same endpoints intended for the ESP32 modules.

## Start the local stack

Docker Desktop must be running with at least several gigabytes of free disk space.

```powershell
docker compose up --build -d
docker compose ps
python -m backend.simulator --scenario normal
```

Open `http://localhost:8000`. The local operator token is `psycon-local-operator`. This value is intentionally limited to the development Compose file and must never be reused in a deployment.

MinIO's local administration console is available at `http://localhost:9001`. PostgreSQL is exposed on port `5432` for local inspection. Stop the stack without deleting its named volumes using `docker compose down`; deleting the volumes destroys local research data and is not part of the normal workflow.

The simulator supports `normal`, `duplicate`, `corrupt`, `missing-audio`, and `overrun` scenarios. A corrupt packet is expected to receive `invalid_crc` and remain absent from storage; duplicates must return `already_present` without adding a metadata row.

## HTTP contract

All protected requests use `Authorization: Bearer <token>`. Operator credentials create sessions and devices, inspect data, trigger processing, and export results. Device credentials are scoped to one unsigned 32-bit device ID and cannot upload another device's packets or status.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/health` | Process liveness without dependency checks |
| `GET /api/v1/ready` | PostgreSQL and object-storage readiness |
| `GET /api/v1/time` | Backend UTC epoch time in microseconds |
| `GET /api/v1/system` | Processing-worker heartbeat and health state |
| `POST /api/v1/sessions` | Create a pseudonymous, version-complete session |
| `POST /api/v1/devices` | Issue a device token for one session, returned once |
| `POST /api/v1/sessions/{id}/chunks` | Ingest one `application/vnd.psycon.chunk-v2` packet |
| `POST /api/v1/sessions/{id}/clock-sync` | Record a four-timestamp clock exchange |
| `POST /api/v1/sessions/{id}/status` | Record health, battery, light, reset, reconnect, or overrun state |
| `GET /api/v1/sessions/{id}` | Return the dashboard snapshot |
| `POST /api/v1/sessions/{id}/process` | Queue idempotent feature processing |
| `POST /api/v1/sessions/{id}/exports` | Build an immutable ZIP research export |
| `POST /api/v1/sessions/{id}/close` | Close ingestion for the session |
| `DELETE /api/v1/sessions/{id}` | Remove session objects and then cascade its database records |

Clock exchanges use `t0_backend_us`, `t1_device_us`, `t2_device_us`, and `t3_backend_us`. The service estimates backend-epoch-minus-device offset and bounded drift from the lowest-delay observations. Original device timestamps are always preserved; synchronized timestamps remain absent when fewer than two observations exist or uncertainty exceeds the configured limit.

Status requests accept these event types: `startup`, `heartbeat`, `sensor_error`, `battery_warning`, `reconnect`, `overrun`, `watchdog_reset`, `shutdown`, and `light`. Operational metadata remains outside the frozen binary chunk so existing Python, TypeScript, and C++ Protocol v2 decoders stay compatible.

## Storage, processing, and recovery

Raw bytes use immutable keys under `sessions/{session}/raw/{device}/{stream}/`. Metadata commits only after the object upload succeeds; failed session validation removes the uncommitted object. The immutable protocol key remains `(device_id, stream_type, sequence)`, so identical retries return success and changed bytes return `sequence_conflict`.

The worker claims queued work using PostgreSQL `FOR UPDATE SKIP LOCKED`. Feature rows have source-and-extractor uniqueness constraints, so a retried job updates the same derived record. Audio uses the existing quality-gated `psycon_audio` extractor. The inference engine validates and scores a complete finite vector using the checked-in logistic model artifact; live audio or raw wrist summaries explicitly abstain because they do not yet contain that calibrated feature contract.

Exports include session metadata, clock observations, status and error events, feature decisions, inference rows, job history, and raw packet bytes. `manifest.json` records every included file's SHA-256 digest and byte length.

Create and verify PostgreSQL backups with:

```powershell
python -m backend.backup create backups
python -m backend.backup verify backups\psycon-<timestamp>.json
```

`pg_dump` must be installed and on `PATH`. The backup command downloads every object and hashes it alongside the database dump, so the destination must have enough space for the complete research store. Production backups should be copied to a second private storage location.

## Deployment boundary

The application image is stateless and configured entirely through `PSYCON_*` environment variables. A permanent hardware receiver needs paid always-on compute, managed PostgreSQL backups, private S3-compatible storage, TLS, monitoring, and secret rotation. Free services that sleep or pause are useful for staging but do not satisfy continuous ingestion.

The Week 4 server software milestone is complete: the Compose integration test verifies authenticated dual-device simulation, idempotent packet storage, synchronized metadata, worker processing, explicit inference abstention, and hashed export retrieval. Deployment and firmware integration remain separate physical gates. When the modules are available, run them simultaneously, measure synchronization uncertainty, interrupt connectivity within queue capacity, fail one module and one sensor at a time, verify continuous acquisition by the survivor, and inspect a complete exported real session before claiming hardware validation.
