ALTER TABLE sync_state ADD COLUMN export_marker TEXT;
CREATE TABLE quality_issues(id INTEGER PRIMARY KEY, provider TEXT NOT NULL, source_set_id TEXT NOT NULL, document_id INTEGER REFERENCES documents(id), reason TEXT NOT NULL, identifiers_json TEXT NOT NULL, UNIQUE(provider,source_set_id,document_id,reason));
PRAGMA user_version=2;
