UPDATE training_tasks SET definition=definition || '{"feature_version":"conversation-2","context_policy":"Fixed meeting/group discussion/interview/presentation/other categories; no names, classes, reviewer identity, or free-text topic as predictors"}'::jsonb;
UPDATE model_versions SET status='needs_retraining' WHERE feature_schema->>'version'!='conversation-2' AND status!='retired';
