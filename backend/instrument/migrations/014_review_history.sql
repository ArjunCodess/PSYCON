CREATE TABLE report_review_revisions (
 id UUID PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES llm_runs(id) ON DELETE CASCADE,
 previous_id TEXT NOT NULL UNIQUE,
 previous_annotation JSONB NOT NULL,
 archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE behavior_review_revisions (
 id UUID PRIMARY KEY,
 evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
 previous_id TEXT NOT NULL UNIQUE,
 previous_annotation JSONB NOT NULL,
 archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER immutable_report_review_history BEFORE UPDATE ON report_review_revisions FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_behavior_review_history BEFORE UPDATE ON behavior_review_revisions FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
