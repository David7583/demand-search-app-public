CREATE TABLE IF NOT EXISTS model_configs (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
 provider TEXT NOT NULL, base_url TEXT NOT NULL, api_mode TEXT NOT NULL,
 model TEXT NOT NULL, encrypted_secret BLOB NOT NULL, secret_context TEXT NOT NULL,
 verified_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_model_per_owner ON model_configs(owner_id) WHERE is_active=1;
CREATE TABLE IF NOT EXISTS model_validation_tickets (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
 provider TEXT NOT NULL, base_url TEXT NOT NULL, api_mode TEXT NOT NULL, model TEXT NOT NULL,
 encrypted_secret BLOB NOT NULL, secret_context TEXT NOT NULL, verified_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, existing_id TEXT, expected_revision INTEGER
);
INSERT OR IGNORE INTO schema_migrations(version) VALUES (2);
