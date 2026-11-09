-- S1 private local conversations; no provider secrets or shared NCP storage.
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_owner_updated
    ON conversations(owner_id, updated_at DESC, id);
CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    client_message_id TEXT,
    parent_message_id TEXT REFERENCES conversation_messages(id) ON DELETE CASCADE,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(conversation_id, sequence),
    UNIQUE(owner_id, client_message_id)
);
CREATE INDEX IF NOT EXISTS messages_conversation_sequence
    ON conversation_messages(conversation_id, sequence);
INSERT OR IGNORE INTO schema_migrations(version) VALUES (3);
