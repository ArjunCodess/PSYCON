CREATE TABLE session_assets(session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE, asset_id UUID REFERENCES assets(id), purpose TEXT NOT NULL, PRIMARY KEY(session_id,asset_id));
CREATE TABLE legacy_records(source TEXT NOT NULL, table_name TEXT NOT NULL, legacy_id TEXT NOT NULL, data JSONB NOT NULL, sha256 TEXT NOT NULL, imported_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(source,table_name,legacy_id));
CREATE TRIGGER immutable_legacy_records BEFORE UPDATE ON legacy_records FOR EACH ROW EXECUTE FUNCTION immutable_annotation();
