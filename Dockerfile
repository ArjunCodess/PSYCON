FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements-backend.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements-backend.txt

FROM dependencies AS nvidia-deps
RUN pip install --no-cache-dir 'torch==2.9.1+cu126' --index-url https://download.pytorch.org/whl/cu126 \
    && pip install --no-cache-dir 'transformers @ https://github.com/huggingface/transformers/archive/6da3313a6f89fb3fe0d51c02fe06e3664cd436b0.tar.gz'
RUN pip install --no-cache-dir 'librosa==0.11.0'

FROM dependencies AS base
COPY backend backend
ENV PSYCON_DIARIZATION_MODELS=/opt/psycon/diarization
RUN python -m backend.group.install_voice_models
COPY protocol protocol
COPY research research
COPY ml/src ml/src
COPY results/app_model.json results/app_model.json
COPY run_backend.py .

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "run_backend:app"]

FROM nvidia-deps AS nvidia
COPY --from=base /app /app
COPY --from=base /opt/psycon/diarization /opt/psycon/diarization
ENV PSYCON_DIARIZATION_MODELS=/opt/psycon/diarization
ENV HF_HOME=/opt/psycon/hf-cache
