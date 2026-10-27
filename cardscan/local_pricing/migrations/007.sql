CREATE TABLE IF NOT EXISTS marketplace_publications(
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  listing_id TEXT NOT NULL REFERENCES inventory_listings(id),
  listing_revision INTEGER NOT NULL,
  provider TEXT NOT NULL,
  external_listing_id TEXT,
  status TEXT NOT NULL CHECK(status IN ('sending','published','failed')),
  request_fingerprint TEXT,
  response_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS marketplace_publication_latest ON marketplace_publications(owner_id,listing_id,created_at DESC);
PRAGMA user_version=7;
