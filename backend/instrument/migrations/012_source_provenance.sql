CREATE TABLE source_reviews (
 id UUID PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('independent','excerpt','derived','uncertain')),
 source_session_id TEXT,
 source_hash TEXT NOT NULL CHECK(length(source_hash)=64),
 reviewer_id TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(session_id,revision),
 CHECK((kind IN ('excerpt','derived'))=(source_session_id IS NOT NULL))
);
CREATE TRIGGER immutable_source_reviews BEFORE UPDATE ON source_reviews FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
INSERT INTO snapshot_invalidations(id,snapshot_id,reason)
 SELECT gen_random_uuid(),id,'Recording source provenance must be reviewed under source-review-1' FROM training_snapshots;
UPDATE model_versions SET status='needs_retraining' WHERE status!='retired';
