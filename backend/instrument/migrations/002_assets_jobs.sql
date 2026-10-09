CREATE TABLE storage_roots(id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL CHECK(kind IN ('media','models')));
CREATE TABLE assets (
 id UUID PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
 root_id TEXT NOT NULL REFERENCES storage_roots(id), relative_path TEXT NOT NULL,
 original_filename TEXT NOT NULL, media_type TEXT NOT NULL, byte_size BIGINT NOT NULL CHECK(byte_size>=0),
 sha256 TEXT NOT NULL CHECK(length(sha256)=64), state TEXT NOT NULL DEFAULT 'available',
 retention TEXT NOT NULL DEFAULT 'until withdrawal', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(root_id,relative_path), CHECK(relative_path NOT LIKE '../%')
);
ALTER TABLE sessions ADD COLUMN asset_id UUID REFERENCES assets(id);
ALTER TABLE sessions ADD COLUMN input_revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE sessions ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local' REFERENCES users(id);
ALTER TABLE sessions DROP CONSTRAINT sessions_sha256_key;
CREATE TABLE jobs (
 id UUID PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('speech','interpretation','import','training')),
 subject_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL DEFAULT 'queued',
 input_revision INTEGER NOT NULL, owner TEXT, attempt INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3, lease_until TIMESTAMPTZ, heartbeat_at TIMESTAMPTZ,
 available_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ, error TEXT, payload JSONB NOT NULL DEFAULT '{}', result JSONB,
 UNIQUE(kind,subject_id,input_revision)
);
CREATE INDEX jobs_claim ON jobs(status,available_at,created_at);
CREATE TABLE worker_heartbeats(owner TEXT PRIMARY KEY, seen_at TIMESTAMPTZ NOT NULL);
CREATE TABLE resource_leases(name TEXT PRIMARY KEY, owner TEXT NOT NULL, lease_until TIMESTAMPTZ NOT NULL);
CREATE TABLE audit_events(id UUID PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL, subject_id TEXT, details JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE migration_runs(id UUID PRIMARY KEY, source_hash TEXT NOT NULL, counts JSONB NOT NULL, verification JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE legacy_id_aliases(source TEXT NOT NULL, table_name TEXT NOT NULL, legacy_id TEXT NOT NULL, canonical_id TEXT NOT NULL, PRIMARY KEY(source,table_name,legacy_id));
CREATE TABLE llm_claims(id UUID PRIMARY KEY, run_id TEXT NOT NULL REFERENCES llm_runs(id) ON DELETE CASCADE, claim_index INTEGER NOT NULL, speaker_id TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE, observation TEXT NOT NULL, inference TEXT NOT NULL, confidence TEXT NOT NULL, limitation TEXT NOT NULL, suggestion TEXT NOT NULL, UNIQUE(run_id,claim_index));
CREATE TABLE llm_claim_evidence(claim_id UUID REFERENCES llm_claims(id) ON DELETE CASCADE, evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE, utterance_id TEXT REFERENCES utterances(id) ON DELETE CASCADE, CHECK((evidence_id IS NULL) <> (utterance_id IS NULL)));
ALTER TABLE speakers ADD CONSTRAINT speakers_id_session UNIQUE(id,session_id);
ALTER TABLE turns ADD CONSTRAINT turn_speaker_session FOREIGN KEY(speaker_id,session_id) REFERENCES speakers(id,session_id) ON DELETE CASCADE;
ALTER TABLE evidence ADD CONSTRAINT evidence_speaker_session FOREIGN KEY(speaker_id,session_id) REFERENCES speakers(id,session_id) ON DELETE CASCADE;
ALTER TABLE utterances ADD CONSTRAINT utterance_speaker_session FOREIGN KEY(speaker_id,session_id) REFERENCES speakers(id,session_id) ON DELETE CASCADE;
ALTER TABLE features ADD CONSTRAINT feature_speaker_session FOREIGN KEY(speaker_id,session_id) REFERENCES speakers(id,session_id) ON DELETE CASCADE;
