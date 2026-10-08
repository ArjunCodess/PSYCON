CREATE TABLE llm_generation_attempts (
 id UUID PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES llm_runs(id) ON DELETE CASCADE,
 attempt INTEGER NOT NULL CHECK(attempt>=0),
 status TEXT NOT NULL CHECK(status IN ('complete','failed')),
 output JSONB,
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(run_id,attempt)
);
CREATE TRIGGER immutable_generation_attempts BEFORE UPDATE ON llm_generation_attempts FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
-- Attempt zero records the retained pre-cutover outcome. Earlier retry history was
-- never recorded by that source, so it cannot be reconstructed or fabricated.
INSERT INTO llm_generation_attempts(id,run_id,attempt,status,output,error,created_at)
 SELECT gen_random_uuid(),id,0,CASE WHEN status='failed' THEN 'failed' ELSE 'complete' END,output,error,created_at
 FROM llm_runs WHERE status IN ('complete','stale','failed');
