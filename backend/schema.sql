CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS participants (
    id UUID PRIMARY KEY,
    anonymous_code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    participant_id UUID NOT NULL REFERENCES participants(id),
    state TEXT NOT NULL CHECK (state IN ('open', 'processing', 'complete', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    versions JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS credentials (
    id UUID PRIMARY KEY,
    label TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('operator', 'device')),
    device_id BIGINT,
    token_hash TEXT NOT NULL UNIQUE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session_devices (
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    credential_id UUID NOT NULL REFERENCES credentials(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(session_id, credential_id),
    UNIQUE(session_id, device_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL,
    stream_type TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    device_timestamp_us NUMERIC(20,0) NOT NULL,
    synchronized_timestamp_us NUMERIC(20,0),
    sync_uncertainty_us BIGINT,
    sample_count INTEGER NOT NULL,
    sample_period_us INTEGER NOT NULL,
    payload_length INTEGER NOT NULL,
    crc32 BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (device_id, stream_type, sequence)
);

CREATE TABLE IF NOT EXISTS clock_observations (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL,
    t0_backend_us NUMERIC(20,0) NOT NULL,
    t1_device_us NUMERIC(20,0) NOT NULL,
    t2_device_us NUMERIC(20,0) NOT NULL,
    t3_backend_us NUMERIC(20,0) NOT NULL,
    delay_us BIGINT NOT NULL,
    offset_us BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS clock_observations_device_idx
    ON clock_observations(session_id, device_id, created_at DESC);

CREATE TABLE IF NOT EXISTS status_events (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    device_timestamp_us NUMERIC(20,0),
    synchronized_timestamp_us NUMERIC(20,0),
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'complete', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(session_id, job_type)
);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_job_id UUID
);

CREATE TABLE IF NOT EXISTS feature_windows (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    source_chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    modality TEXT NOT NULL,
    window_start_us NUMERIC(20,0),
    window_end_us NUMERIC(20,0),
    quality_state TEXT NOT NULL,
    extractor TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    features JSONB NOT NULL,
    provenance JSONB NOT NULL,
    UNIQUE(source_chunk_id, extractor, extractor_version)
);

CREATE TABLE IF NOT EXISTS inference_results (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    feature_window_id UUID REFERENCES feature_windows(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    score DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(feature_window_id, model_name, model_version)
);

CREATE TABLE IF NOT EXISTS exports (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_version(version) VALUES (1), (2), (3) ON CONFLICT DO NOTHING;
