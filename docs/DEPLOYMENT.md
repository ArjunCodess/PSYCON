# Deployment

## Current hosting

Checked on 1 October 2026 using the open Render and Cloudflare dashboards.
The existing site is https://psycon.onrender.com. It runs `main` on a free
CPU instance in Singapore. Its dashboard reached Ready after a cold start.
The Cloudflare R2 bucket `psycon-research` is private. Keep it private.

This branch has not been deployed. The free web instance cannot run the CUDA
analysis worker. Large recordings also need more memory: the current upload
path reads the whole video into memory and permits files up to 2 GB. Choose a
web instance with enough memory for the largest recording and concurrent
uploads before enabling group uploads in production. A ready health endpoint
does not prove that analysis jobs can finish.

During the release smoke check, the local Docker runtime stopped all its
containers while video inference and API checks were running together.
The extra app-triggered PSYCON run was interrupted; it is not another
completed benchmark. The saved 66 benchmark runs remain the comparison evidence.

## Web server

Render's existing settings can use the root Dockerfile and
`sh backend/start_render.sh`, with `/api/v1/ready` as the health check. The final
Docker stage is now `web`, so a normal build excludes CUDA dependencies.
Keep `PSYCON_RUN_WORKER` unset or `false` on the web server.

Set `PSYCON_ENV=production`. Supply unique `PSYCON_SECRET_KEY` and
`PSYCON_BOOTSTRAP_OPERATOR_TOKEN`, the PostgreSQL connection in
`PSYCON_DATABASE_URL`, and these private R2 settings:

- `PSYCON_S3_ENDPOINT_URL` and `PSYCON_S3_PUBLIC_ENDPOINT_URL`: the same R2 S3 endpoint, not a public bucket URL. Downloads use signed URLs.
- `PSYCON_S3_BUCKET`, `PSYCON_S3_REGION`, `PSYCON_S3_ACCESS_KEY`, and `PSYCON_S3_SECRET_KEY`.

The existing service already has these key names configured. Their values
were kept masked. Provision named group accounts through
`POST /api/v1/group-accounts` using the bootstrap operator bearer token.
Use the issued named token in Account access on `/group`. The browser keeps
a signed, HttpOnly, Secure, SameSite=Strict session in production. Every group
request checks the account's current role and revocation state. Anonymous
production requests cannot use the local operator fallback.

## Analysis worker

Run the worker on an NVIDIA GPU host with Docker GPU support. It must use
the same PostgreSQL database and private R2 bucket as the web server, not the
localhost database from the development Compose file. Keep its environment
file outside Git. Include `HF_TOKEN` with accepted Community-1 model access,
the production settings above, and these model device settings:

```text
PSYCON_DIARIZATION_DEVICE=cuda
PSYCON_SPEAKER_DEVICE=cuda
PSYCON_WHISPER_DEVICE=cuda
PSYCON_COMMUNITY1_REVISION=3533c8cf8e369892e6b79ff1bf80f7b0286a54ee
```

Build and start it from the same code revision as the web server:

```sh
docker build --target nvidia -t psycon-worker .
docker run -d --restart unless-stopped --gpus all \
  --env-file /secure/psycon-worker.env \
  -v psycon-models:/opt/psycon/hf-cache \
  psycon-worker python -m backend.worker
```

Start one worker first and check its database heartbeat and a completed
group job. Confirm that assigned playback loads, unknown intervals stay
unknown, and a missing model or token produces an explicit failure. PSYCON
training eligibility must never be supplied by another method.

For concurrent wearable traffic, run a separate CPU worker using the web
image and `python -m backend.worker --device-only`, with the same database
and storage settings. It never claims group jobs, so a long video run cannot
hold up the wearable queue on that worker.

If a runtime stops during voice inference, first verify the worker owning
the job has stopped. Then recover that exact job using its ID and `locked_by`
worker ID from `group_jobs`:

```sh
python -m backend.group.recover_voice_job --job-id JOB_UUID \
  --worker-id STOPPED_WORKER_ID --worker-stopped --reason runtime_interrupted
```

This marks only that voice method failed and clears its profiles in one
transaction. The Faces tab can then retry it. It preserves the other methods.
Never use this command against a live worker; it does not cancel inference.

## Local verification

`docker compose up --build -d` starts the local API, GPU worker, PostgreSQL,
and object storage. Published ports bind to `127.0.0.1`.
The previously pinned MinIO container stopped being publicly pullable, so
`deploy/minio` builds a local image from the official release binary and
checks its SHA-256 before installing it. This older storage build is for local
development; use private R2 for hosted storage.

No cloud settings, credentials, bucket visibility, or deployed branch were
changed during the release check. Merge and deploy the reviewed PR only after
the web memory allocation and GPU worker host have been selected.
