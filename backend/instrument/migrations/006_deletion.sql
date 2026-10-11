ALTER TABLE training_runs ALTER COLUMN snapshot_id DROP NOT NULL;
ALTER TABLE training_examples ALTER COLUMN participant_id DROP NOT NULL;
ALTER TABLE training_examples ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE model_versions ADD COLUMN retirement_reason TEXT;
CREATE TABLE deletion_tombstones(id UUID PRIMARY KEY, deleted_at TIMESTAMPTZ NOT NULL DEFAULT now(), subject_hash TEXT NOT NULL, kind TEXT NOT NULL, backup_policy TEXT NOT NULL);
