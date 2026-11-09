-- App-owned immutable demand snapshots and exact private NCP bytes.
CREATE TABLE demands (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    intent_id TEXT NOT NULL UNIQUE,
    sender_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','withdrawn')),
    current_version_id TEXT,
    confirmed_version_id TEXT,
    ncp_revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE demand_versions (
    id TEXT PRIMARY KEY,
    demand_id TEXT NOT NULL REFERENCES demands(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    parent_version_id TEXT,
    source_message_id TEXT NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
    original_text TEXT NOT NULL,
    data_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','confirmed')),
    model TEXT,
    provider TEXT,
    prompt_version TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(demand_id, number)
);
CREATE TABLE demand_packets (
    id TEXT PRIMARY KEY,
    demand_id TEXT NOT NULL REFERENCES demands(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES demand_versions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    packet_bytes BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(demand_id, sequence)
);
CREATE TABLE demand_requests (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    operation TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','failed','completed')),
    claim_token TEXT NOT NULL,
    lease_until REAL NOT NULL,
    version_id TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX demand_requests_conversation ON demand_requests(conversation_id);
INSERT OR IGNORE INTO schema_migrations(version) VALUES (4);
