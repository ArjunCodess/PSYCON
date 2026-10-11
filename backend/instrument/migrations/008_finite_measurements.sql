ALTER TABLE features ADD CONSTRAINT feature_finite CHECK(value IS NULL OR (value>'-Infinity'::float8 AND value<'Infinity'::float8));
ALTER TABLE turns ADD CONSTRAINT turn_finite CHECK(start_s>=0 AND end_s<'Infinity'::float8);
ALTER TABLE utterances ADD CONSTRAINT utterance_finite CHECK(start_s>=0 AND end_s>=start_s AND end_s<'Infinity'::float8);
ALTER TABLE words ADD CONSTRAINT word_finite CHECK(start_s>=0 AND end_s>=start_s AND end_s<'Infinity'::float8);
ALTER TABLE evidence ADD CONSTRAINT evidence_finite CHECK(start_s>=0 AND end_s>=start_s AND end_s<'Infinity'::float8);
ALTER TABLE training_example_features ADD CONSTRAINT training_feature_finite CHECK(value IS NULL OR (value>'-Infinity'::float8 AND value<'Infinity'::float8));
