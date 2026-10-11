
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, label TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workspace_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO workspace_settings VALUES ('target_archetype','Executive') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), label TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, target_archetype TEXT NOT NULL DEFAULT 'Executive');
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, original_path TEXT NOT NULL,
 recorded_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL, context TEXT NOT NULL, topic TEXT NOT NULL,
 dataset TEXT NOT NULL, split TEXT NOT NULL CHECK(split IN ('development','validation','evaluation','reference')),
 consent TEXT NOT NULL, conditions TEXT NOT NULL, participant_ids JSONB NOT NULL,
 status TEXT NOT NULL, error TEXT, duration DOUBLE PRECISION, sample_rate INTEGER, channels INTEGER,
 config JSONB NOT NULL, versions JSONB NOT NULL, lease_until DOUBLE PRECISION, worker_id TEXT
);
CREATE TABLE IF NOT EXISTS stages (
 session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, name TEXT NOT NULL, status TEXT NOT NULL,
 started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, output JSONB, error TEXT, PRIMARY KEY(session_id,name)
);
CREATE TABLE IF NOT EXISTS speakers (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 label TEXT NOT NULL, display_name TEXT NOT NULL, profile_id TEXT REFERENCES profiles(id),
 UNIQUE(session_id,label), UNIQUE(session_id,profile_id)
);
CREATE TABLE IF NOT EXISTS turns (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
 start_s DOUBLE PRECISION NOT NULL, end_s DOUBLE PRECISION NOT NULL, confidence DOUBLE PRECISION, CHECK(end_s > start_s)
);
CREATE TABLE IF NOT EXISTS utterances (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE, turn_id TEXT REFERENCES turns(id) ON DELETE CASCADE,
 start_s DOUBLE PRECISION NOT NULL, end_s DOUBLE PRECISION NOT NULL, text TEXT NOT NULL, confidence DOUBLE PRECISION,
 attribution TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS words (
 id TEXT PRIMARY KEY, utterance_id TEXT REFERENCES utterances(id) ON DELETE CASCADE,
 start_s DOUBLE PRECISION NOT NULL, end_s DOUBLE PRECISION NOT NULL, text TEXT NOT NULL, confidence DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS evidence (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
 utterance_id TEXT REFERENCES utterances(id) ON DELETE CASCADE,
 feature TEXT NOT NULL, start_s DOUBLE PRECISION NOT NULL, end_s DOUBLE PRECISION NOT NULL, text TEXT NOT NULL,
 context JSONB NOT NULL, level TEXT NOT NULL, confidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interactions (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 source TEXT REFERENCES speakers(id) ON DELETE CASCADE, target TEXT REFERENCES speakers(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, start_s DOUBLE PRECISION NOT NULL, evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE,
 status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS features (
 session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE,
 name TEXT NOT NULL, value DOUBLE PRECISION, unit TEXT NOT NULL, source TEXT NOT NULL,
 confidence TEXT NOT NULL, status TEXT NOT NULL, denominator DOUBLE PRECISION, PRIMARY KEY(speaker_id,name)
);
CREATE TABLE IF NOT EXISTS baseline_profiles (
 id TEXT PRIMARY KEY, profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
 session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, context TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL, source_sessions JSONB NOT NULL, statistics JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS baseline_features (
 baseline_id TEXT REFERENCES baseline_profiles(id) ON DELETE CASCADE, name TEXT NOT NULL,
 mean DOUBLE PRECISION, median DOUBLE PRECISION, variance DOUBLE PRECISION, standard_deviation DOUBLE PRECISION, p10 DOUBLE PRECISION, p90 DOUBLE PRECISION,
 sample_count INTEGER NOT NULL, empirical_percentile DOUBLE PRECISION, confidence TEXT NOT NULL,
 PRIMARY KEY(baseline_id,name)
);
CREATE TABLE IF NOT EXISTS baseline_sessions (
 baseline_id TEXT REFERENCES baseline_profiles(id) ON DELETE CASCADE,
 source_session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, PRIMARY KEY(baseline_id,source_session_id)
);
CREATE TABLE IF NOT EXISTS archetypes (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, source TEXT NOT NULL,
 dataset TEXT, sample_count INTEGER NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL, limitations TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archetype_features (
 archetype_id TEXT REFERENCES archetypes(id) ON DELETE CASCADE, name TEXT NOT NULL,
 center DOUBLE PRECISION NOT NULL, weight DOUBLE PRECISION NOT NULL, distribution JSONB, PRIMARY KEY(archetype_id,name)
);
CREATE TABLE IF NOT EXISTS traits (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, feature TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_traits (
 id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE, trait_id TEXT REFERENCES traits(id),
 observation TEXT NOT NULL, inference TEXT NOT NULL, confidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trait_evidence (
 session_trait_id TEXT REFERENCES session_traits(id) ON DELETE CASCADE,
 evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE, PRIMARY KEY(session_trait_id,evidence_id)
);
CREATE TABLE IF NOT EXISTS comparisons (
 id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE, archetype_id TEXT REFERENCES archetypes(id),
 similarity DOUBLE PRECISION, method TEXT NOT NULL, dimensions JSONB NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_runs (
 id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE, condition TEXT NOT NULL,
 model TEXT NOT NULL, digest TEXT, created_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL,
 input JSONB NOT NULL, output JSONB, error TEXT, prompt_version TEXT NOT NULL, blind_id TEXT UNIQUE NOT NULL,
 system_prompt TEXT, configuration JSONB
);
CREATE TABLE IF NOT EXISTS evaluations (
 id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
 speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE, feature TEXT NOT NULL,
 reviewer_id TEXT NOT NULL, expected DOUBLE PRECISION NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS reviewer_annotations (
 id TEXT PRIMARY KEY, run_id TEXT REFERENCES llm_runs(id) ON DELETE CASCADE, reviewer_id TEXT NOT NULL,
 claim_index INTEGER NOT NULL, grounding INTEGER NOT NULL, attribution INTEGER NOT NULL,
 contextual_appropriateness INTEGER NOT NULL, archetype_agreement INTEGER NOT NULL,
 usefulness INTEGER NOT NULL, overclaiming INTEGER NOT NULL, trait_validity INTEGER NOT NULL,
 notes TEXT NOT NULL, UNIQUE(run_id,reviewer_id,claim_index)
);
CREATE INDEX IF NOT EXISTS session_history ON sessions(recorded_at,status);
CREATE INDEX IF NOT EXISTS speaker_history ON speakers(profile_id,session_id);
CREATE INDEX IF NOT EXISTS evidence_lookup ON evidence(speaker_id,feature,start_s);
CREATE TABLE IF NOT EXISTS behavior_annotations (
 id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, reviewer_id TEXT NOT NULL, target_speaker_id TEXT REFERENCES speakers(id) ON DELETE CASCADE,
 topic TEXT NOT NULL, phase TEXT NOT NULL, notes TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 UNIQUE(evidence_id,kind,reviewer_id)
);

INSERT INTO users VALUES ('local','Local researcher') ON CONFLICT DO NOTHING;
