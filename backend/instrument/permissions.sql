-- Apply as the migration operator after creating role-specific login credentials externally.
-- This file deliberately contains no passwords and is never run by web request handling.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='psycon_web') THEN CREATE ROLE psycon_web NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='psycon_worker') THEN CREATE ROLE psycon_worker NOLOGIN; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='psycon_trainer') THEN CREATE ROLE psycon_trainer NOLOGIN; END IF;
END $$;
-- The default local/Neon deployment uses one operator login with SET ROLE.
GRANT psycon_web,psycon_worker,psycon_trainer TO CURRENT_USER;
GRANT USAGE ON SCHEMA psycon TO psycon_web,psycon_worker,psycon_trainer;
GRANT SELECT ON ALL TABLES IN SCHEMA psycon TO psycon_web,psycon_worker,psycon_trainer;
GRANT INSERT,UPDATE,DELETE ON psycon.jobs,psycon.worker_heartbeats,psycon.resource_leases TO psycon_web,psycon_worker,psycon_trainer;
GRANT INSERT,DELETE ON psycon.baseline_profiles,psycon.baseline_features,psycon.baseline_sessions,psycon.comparisons TO psycon_web,psycon_worker;
GRANT INSERT,UPDATE,DELETE ON psycon.sessions,psycon.stages,psycon.speakers,psycon.turns,psycon.utterances,psycon.words,psycon.features,psycon.evidence,psycon.interactions,psycon.session_traits,psycon.trait_evidence,psycon.traits,psycon.model_predictions,psycon.prediction_evidence TO psycon_worker;
GRANT INSERT,UPDATE,DELETE ON psycon.people,psycon.session_participants,psycon.consent_records,psycon.speaker_mappings,psycon.annotation_imports,psycon.annotation_import_rows,psycon.annotation_submissions,psycon.annotation_answers,psycon.annotation_context_flags,psycon.annotation_validity_checks,psycon.annotation_pattern_summaries,psycon.annotation_evidence,psycon.annotation_reviews,psycon.annotation_adjudications,psycon.annotation_attachments,psycon.snapshot_invalidations TO psycon_web;
GRANT INSERT ON psycon.annotation_submissions,psycon.annotation_answers,psycon.annotation_context_flags,psycon.annotation_validity_checks,psycon.annotation_pattern_summaries,psycon.annotation_evidence,psycon.annotation_import_rows,psycon.snapshot_invalidations TO psycon_worker;
GRANT UPDATE ON psycon.annotation_imports TO psycon_worker;
-- SELECT FOR UPDATE requires an UPDATE grant; workers lock participants but never change their identities.
GRANT UPDATE(id) ON psycon.session_participants TO psycon_worker;
GRANT INSERT,UPDATE ON psycon.sessions,psycon.stages,psycon.profiles,psycon.workspace_settings,psycon.llm_runs,psycon.llm_claims,psycon.llm_claim_evidence,psycon.assets,psycon.storage_roots,psycon.session_assets TO psycon_web;
GRANT INSERT,UPDATE,DELETE ON psycon.llm_runs,psycon.llm_claims,psycon.llm_claim_evidence TO psycon_worker;
GRANT INSERT ON psycon.training_snapshots,psycon.training_examples,psycon.training_example_features,psycon.training_example_labels,psycon.split_assignments,psycon.training_runs,psycon.model_deployments,psycon.audit_events,psycon.evaluations,psycon.reviewer_annotations,psycon.behavior_annotations TO psycon_web;
GRANT INSERT,UPDATE ON psycon.training_runs,psycon.training_run_events,psycon.model_versions,psycon.model_artifacts,psycon.model_evaluations,psycon.assets,psycon.storage_roots TO psycon_trainer;
GRANT UPDATE ON psycon.model_versions,psycon.training_runs TO psycon_web,psycon_worker;
GRANT INSERT,UPDATE,DELETE ON psycon.speakers,psycon.model_predictions,psycon.prediction_evidence TO psycon_web;
GRANT DELETE ON psycon.sessions,psycon.training_snapshots,psycon.archetypes TO psycon_web;
GRANT INSERT,UPDATE,DELETE ON psycon.archetype_features,psycon.archetypes,psycon.traits TO psycon_web;
GRANT INSERT,UPDATE,DELETE ON psycon.evaluations,psycon.reviewer_annotations,psycon.behavior_annotations,psycon.deletion_tombstones TO psycon_web;
GRANT INSERT,UPDATE ON psycon.training_runs,psycon.training_run_events TO psycon_web;
GRANT INSERT ON psycon.model_predictions,psycon.prediction_evidence TO psycon_trainer;

GRANT INSERT,DELETE ON psycon.source_reviews TO psycon_web;

GRANT INSERT ON psycon.llm_generation_attempts TO psycon_worker;

GRANT INSERT ON psycon.report_review_revisions,psycon.behavior_review_revisions TO psycon_web;

-- Human review updates derived conversational indicators without editing transcripts.
GRANT INSERT,DELETE ON psycon.features,psycon.interactions,psycon.session_traits,psycon.trait_evidence TO psycon_web;
GRANT UPDATE(context) ON psycon.evidence TO psycon_web;
GRANT DELETE ON psycon.llm_runs TO psycon_web;

GRANT INSERT ON psycon.reanalysis_requests TO psycon_web;

GRANT INSERT ON psycon.assets,psycon.storage_roots,psycon.session_assets TO psycon_worker;
