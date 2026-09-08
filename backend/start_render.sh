#!/bin/sh
set -eu

python -m backend.worker &
exec gunicorn \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  run_backend:app
