-- Preserve every component of annotation history; deletion remains an explicit retention operation.
CREATE TRIGGER immutable_context BEFORE UPDATE ON annotation_context_flags FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_validity BEFORE UPDATE ON annotation_validity_checks FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_patterns BEFORE UPDATE ON annotation_pattern_summaries FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_annotation_evidence BEFORE UPDATE ON annotation_evidence FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_adjudications BEFORE UPDATE ON annotation_adjudications FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
CREATE TRIGGER immutable_attachments BEFORE UPDATE ON annotation_attachments FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
UPDATE form_items SET requirements=jsonb_set(requirements,'{event}','true'::jsonb) WHERE form_id='at-4.0' AND key='K';
UPDATE form_definitions SET definition=definition || '{"eligibility_policy_version":"audio-context-2"}'::jsonb WHERE id='at-4.0';
