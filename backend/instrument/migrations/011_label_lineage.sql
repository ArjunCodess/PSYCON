ALTER TABLE training_example_labels ADD COLUMN label_revision INTEGER CHECK(label_revision>0);
ALTER TABLE training_example_labels ADD COLUMN form_id TEXT REFERENCES form_definitions(id);
ALTER TABLE training_example_labels ADD COLUMN form_hash TEXT;
ALTER TABLE training_example_labels ADD COLUMN import_id UUID REFERENCES annotation_imports(id);
ALTER TABLE training_example_labels ADD COLUMN annotation_source_hash TEXT;
ALTER TABLE training_example_labels ADD COLUMN reviewer_id TEXT;
ALTER TABLE training_example_labels ADD COLUMN source_type TEXT;
ALTER TABLE training_example_labels ADD COLUMN observer_confidence INTEGER CHECK(observer_confidence BETWEEN 1 AND 3);
ALTER TABLE training_example_labels ADD COLUMN fair_opportunity BOOLEAN;
ALTER TABLE training_example_labels ADD COLUMN mapping_revision INTEGER CHECK(mapping_revision>0);
ALTER TABLE training_example_labels ADD COLUMN consent_id UUID REFERENCES consent_records(id);
ALTER TABLE training_example_labels ADD COLUMN review_id UUID REFERENCES annotation_reviews(id);
-- Older immutable snapshots are not rewritten. Unrecorded provenance stays absent.
