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

CREATE TABLE IF NOT EXISTS group_accounts (
    id UUID PRIMARY KEY,
    label TEXT NOT NULL,
    account_code TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('operator', 'psychologist', 'reviewer')),
    token_hash TEXT NOT NULL UNIQUE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_sessions (
    id UUID PRIMARY KEY,
    session_code TEXT NOT NULL UNIQUE,
    session_date DATE NOT NULL,
    class_name TEXT NOT NULL,
    section TEXT NOT NULL,
    topic TEXT NOT NULL,
    language TEXT NOT NULL,
    moderator_code TEXT NOT NULL,
    camera_position TEXT NOT NULL,
    camera_orientation TEXT NOT NULL,
    recording_start_time TIMESTAMPTZ NOT NULL,
    consent_status TEXT NOT NULL CHECK (consent_status IN ('pending', 'recorded', 'refused')),
    consent_version TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    participant_count INTEGER NOT NULL CHECK (participant_count BETWEEN 2 AND 10),
    state TEXT NOT NULL,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    marked_frame_object_key TEXT,
    recording_disposition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consent_records (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    form_line INTEGER NOT NULL,
    legal_name TEXT NOT NULL,
    signature_object_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS group_participants (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 10),
    anonymous_code TEXT NOT NULL,
    label TEXT NOT NULL,
    research_code TEXT,
    withdrawn_at TIMESTAMPTZ,
    UNIQUE (group_session_id, slot_number),
    UNIQUE (group_session_id, anonymous_code)
);

CREATE TABLE IF NOT EXISTS recordings (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL UNIQUE REFERENCES group_sessions(id) ON DELETE CASCADE,
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    video_codec TEXT NOT NULL,
    audio_codec TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    timestamps_readable BOOLEAN NOT NULL,
    processing_state TEXT NOT NULL,
    failure_reason TEXT,
    quality_state TEXT NOT NULL,
    processing JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_version TEXT
);

CREATE TABLE IF NOT EXISTS seat_assignments (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL,
    label TEXT NOT NULL,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    width DOUBLE PRECISION NOT NULL,
    height DOUBLE PRECISION NOT NULL,
    center_x DOUBLE PRECISION NOT NULL,
    valid_from_s DOUBLE PRECISION NOT NULL,
    valid_to_s DOUBLE PRECISION NOT NULL,
    camera_orientation TEXT NOT NULL,
    marked_frame_object_key TEXT NOT NULL,
    frame_time_s DOUBLE PRECISION NOT NULL,
    confirmed_by UUID,
    confirmed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS speaker_turns (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    recording_id UUID NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    cluster_label TEXT NOT NULL,
    start_s DOUBLE PRECISION NOT NULL,
    end_s DOUBLE PRECISION NOT NULL,
    overlap BOOLEAN NOT NULL,
    engine TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    proposed_participant_id UUID
);

CREATE TABLE IF NOT EXISTS speaker_mappings (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    cluster_label TEXT NOT NULL,
    participant_id UUID REFERENCES group_participants(id),
    status TEXT NOT NULL CHECK (status IN ('confirmed', 'uncertain', 'unknown')),
    note TEXT NOT NULL DEFAULT '',
    mapped_by UUID,
    mapped_at TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS marksheets (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    rater_id UUID NOT NULL REFERENCES group_accounts(id),
    rating_role TEXT NOT NULL CHECK (rating_role IN ('primary', 'independent', 'adjudicated')),
    revision INTEGER NOT NULL,
    marksheet_version TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('draft', 'submitted')),
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,
    supersedes_id UUID,
    corrected_by UUID,
    correction_reason TEXT,
    UNIQUE (participant_id, rater_id, rating_role, revision)
);

CREATE TABLE IF NOT EXISTS item_ratings (
    id UUID PRIMARY KEY,
    marksheet_id UUID NOT NULL REFERENCES marksheets(id) ON DELETE CASCADE,
    item_letter TEXT NOT NULL,
    score TEXT,
    preceding_event TEXT NOT NULL DEFAULT '',
    observed_response TEXT NOT NULL DEFAULT '',
    fair_opportunity BOOLEAN,
    no_score_reason TEXT,
    UNIQUE (marksheet_id, item_letter)
);

CREATE TABLE IF NOT EXISTS evidence_intervals (
    id UUID PRIMARY KEY,
    item_rating_id UUID NOT NULL REFERENCES item_ratings(id) ON DELETE CASCADE,
    interval_kind TEXT NOT NULL CHECK (interval_kind IN ('evidence', 'baseline', 'trigger')),
    start_s DOUBLE PRECISION NOT NULL,
    end_s DOUBLE PRECISION NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    primary_marksheet_id UUID NOT NULL REFERENCES marksheets(id),
    independent_marksheet_id UUID NOT NULL REFERENCES marksheets(id),
    adjudicated_marksheet_id UUID NOT NULL REFERENCES marksheets(id),
    reviewer_id UUID NOT NULL,
    reason TEXT NOT NULL,
    changes JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    rater_id UUID,
    item_letter TEXT NOT NULL,
    predicted_label TEXT NOT NULL,
    abstained BOOLEAN NOT NULL,
    confidence DOUBLE PRECISION,
    account TEXT NOT NULL,
    evidence_start_s DOUBLE PRECISION,
    evidence_end_s DOUBLE PRECISION,
    evidence_source TEXT,
    model_version TEXT NOT NULL,
    model_family TEXT,
    reason TEXT,
    source_recording_sha256 TEXT NOT NULL,
    psychologist_score TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marksheet_attachments (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    filename TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    uploaded_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pdf_text_used_as_labels BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS group_jobs (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'complete', 'failed')),
    locked_by TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS playback_grants (
    token_hash TEXT PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    account_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    object_key TEXT NOT NULL
);

INSERT INTO schema_version(version) VALUES (1), (2), (3), (4), (5) ON CONFLICT DO NOTHING;

ALTER TABLE recordings ADD COLUMN IF NOT EXISTS audio_object_key TEXT;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS thumbnail_object_key TEXT;

CREATE TABLE IF NOT EXISTS face_samples (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 10),
    x REAL NOT NULL,
    y REAL NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    feature JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (group_session_id, slot_number)
);

CREATE TABLE IF NOT EXISTS training_labels (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    participant_id UUID NOT NULL REFERENCES group_participants(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 10),
    item_letter TEXT NOT NULL,
    score TEXT NOT NULL,
    class_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (group_session_id, participant_id, item_letter)
);

ALTER TABLE training_labels ADD COLUMN IF NOT EXISTS class_name TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS voice_segments (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    start_s DOUBLE PRECISION NOT NULL,
    end_s DOUBLE PRECISION NOT NULL,
    cluster_label TEXT,
    overlap_refused_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    slot_number INTEGER CHECK (slot_number BETWEEN 1 AND 10),
    confidence DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('assigned', 'unknown')),
    CHECK (end_s > start_s)
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id UUID PRIMARY KEY,
    group_session_id UUID NOT NULL REFERENCES group_sessions(id) ON DELETE CASCADE,
    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 10),
    engine TEXT,
    usable_seconds DOUBLE PRECISION NOT NULL,
    vector JSONB,
    embedding_engine TEXT,
    embedding JSONB,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('ready', 'insufficient_speech')),
    UNIQUE (group_session_id, slot_number)
);

ALTER TABLE voice_segments ADD COLUMN IF NOT EXISTS cluster_label TEXT;
ALTER TABLE voice_segments ADD COLUMN IF NOT EXISTS overlap_refused_s DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS embedding_engine TEXT;
ALTER TABLE voice_profiles ADD COLUMN IF NOT EXISTS embedding JSONB;
