#!/bin/sh
set -eu

# Hosted web instances use a separate GPU worker by default.
if [ "${PSYCON_RUN_WORKER:-false}" = "true" ]; then
  python -m backend.worker &
fi
exec gunicorn \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  run_backend:app
