CREATE TABLE reanalysis_requests (
 id UUID PRIMARY KEY,
 parent_session_id TEXT NOT NULL,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 request_hash TEXT NOT NULL,
 reviewer_id TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(parent_session_id,request_hash)
);
CREATE TRIGGER immutable_reanalysis_requests BEFORE UPDATE ON reanalysis_requests FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_speaker_mappings BEFORE UPDATE ON speaker_mappings FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_consent_history BEFORE UPDATE ON consent_records FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
