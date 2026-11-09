"""Private local conversation persistence independent of model availability."""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .config import Settings
from .errors import AppError
from .storage import LOCAL_OWNER, connect

MAX_CONTENT = 8000
MAX_MESSAGES = 500
MAX_CONVERSATIONS = 200


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def checked_text(value, *, label="content", limit=MAX_CONTENT):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise AppError("INVALID_INPUT", f"{label} must contain 1 to {limit} characters", 422)
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise AppError("INVALID_INPUT", "Text must contain valid Unicode", 422) from None
    return value


def checked_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError):
        raise AppError("INVALID_INPUT", "A valid UUID is required", 422) from None


def message_view(row):
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "sequence": row["sequence"],
        "created_at": row["created_at"],
        "client_message_id": row["client_message_id"],
        "parent_message_id": row["parent_message_id"],
        "metadata": json.loads(row["metadata_json"]),
    }


class HistoryService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _conversation(self, db, conversation_id):
        identity = checked_id(conversation_id)
        row = db.execute(
            "SELECT id,title,created_at,updated_at FROM conversations WHERE id=? AND owner_id=?",
            (identity, LOCAL_OWNER),
        ).fetchone()
        if row is None:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation does not exist", 404)
        return row

    def _detail(self, db, conversation_id):
        row = self._conversation(db, conversation_id)
        messages = db.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id=? AND owner_id=? "
            "ORDER BY sequence",
            (row["id"], LOCAL_OWNER),
        ).fetchall()
        return {**dict(row), "messages": [message_view(message) for message in messages]}

    def create(self, title=None):
        title = "新对话" if title is None else checked_text(title, label="title", limit=120).strip()
        identity, timestamp = str(uuid4()), now()
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM conversations WHERE owner_id=?", (LOCAL_OWNER,)
            ).fetchone()[0]
            if count >= MAX_CONVERSATIONS:
                raise AppError(
                    "HISTORY_LIMIT_REACHED", "Export or delete older conversations first", 409
                )
            db.execute(
                "INSERT INTO conversations(id,owner_id,title,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (identity, LOCAL_OWNER, title, timestamp, timestamp),
            )
            return self._detail(db, identity)

    def list(self, query="", limit=50, offset=0):
        if not isinstance(query, str) or len(query) > 200 or "\x00" in query:
            raise AppError("INVALID_INPUT", "Search text is too long or invalid", 422)
        if not isinstance(limit, int) or not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise AppError("INVALID_INPUT", "Invalid pagination", 422)
        try:
            query.encode("utf-8")
        except UnicodeError:
            raise AppError("INVALID_INPUT", "Search text must contain valid Unicode", 422) from None
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        condition = (
            "c.owner_id=? AND (c.title LIKE ? ESCAPE '\\' OR EXISTS ("
            "SELECT 1 FROM conversation_messages m WHERE m.conversation_id=c.id "
            "AND m.owner_id=c.owner_id AND m.content LIKE ? ESCAPE '\\'))"
        )
        with connect(self.settings) as db:
            total = db.execute(
                "SELECT count(*) FROM conversations c WHERE " + condition,
                (LOCAL_OWNER, pattern, pattern),
            ).fetchone()[0]
            rows = db.execute(
                "SELECT c.id,c.title,c.created_at,c.updated_at,"
                "(SELECT count(*) FROM conversation_messages m "
                "WHERE m.conversation_id=c.id AND m.owner_id=c.owner_id) AS message_count "
                "FROM conversations c WHERE "
                + condition
                + " ORDER BY c.updated_at DESC,c.id LIMIT ? OFFSET ?",
                (LOCAL_OWNER, pattern, pattern, limit, offset),
            ).fetchall()
            return {"conversations": [dict(row) for row in rows], "total": total}

    def get(self, conversation_id):
        with connect(self.settings) as db:
            return self._detail(db, conversation_id)

    def rename(self, conversation_id, title):
        title = checked_text(title, label="title", limit=120).strip()
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._conversation(db, conversation_id)
            db.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=? AND owner_id=?",
                (title, now(), row["id"], LOCAL_OWNER),
            )
            return self._detail(db, row["id"])

    def delete(self, conversation_id):
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._conversation(db, conversation_id)
            db.execute(
                "DELETE FROM conversations WHERE id=? AND owner_id=?", (row["id"], LOCAL_OWNER)
            )
        return {"deleted": True}

    def _referenced_version(self, db, conversation_id, version_id):
        """Resolve a version only inside this local owner's conversation."""
        version_id = checked_id(version_id)
        record = db.execute(
            "SELECT v.id,v.number,v.status,v.data_json FROM demand_versions v "
            "JOIN demands d ON d.id=v.demand_id "
            "WHERE v.id=? AND d.conversation_id=? AND d.owner_id=?",
            (version_id, conversation_id, LOCAL_OWNER),
        ).fetchone()
        if record is None:
            raise AppError(
                "REFERENCE_VERSION_NOT_FOUND",
                "本会话中不存在所引用的方案版本，请重新选择。",
                404,
            )
        return record

    def add_message(
        self, conversation_id, content, client_message_id, *, reference_version_id=None
    ):
        content = checked_text(content)
        client_id = checked_id(client_message_id)
        reference_id = (
            checked_id(reference_version_id) if reference_version_id is not None else None
        )
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._conversation(db, conversation_id)
            old = db.execute(
                "SELECT * FROM conversation_messages WHERE owner_id=? AND client_message_id=?",
                (LOCAL_OWNER, client_id),
            ).fetchone()
            if old:
                old_reference = json.loads(old["metadata_json"]).get("reference_version")
                old_reference_id = old_reference["id"] if old_reference else None
                if (
                    old["conversation_id"] == row["id"]
                    and old["content"] == content
                    and old_reference_id == reference_id
                ):
                    return {"message": message_view(old), "duplicate": True}
                raise AppError(
                    "MESSAGE_ID_CONFLICT", "This message ID has different content or context", 409
                )
            metadata = {}
            if reference_id is not None:
                version = self._referenced_version(db, row["id"], reference_id)
                metadata["reference_version"] = {
                    key: version[key] for key in ("id", "number", "status")
                }
            result = self._insert_message(
                db, row["id"], "user", content, client_id, metadata=metadata
            )
            return {"message": result, "duplicate": False}

    def _insert_message(
        self, db, conversation_id, role, content, client_id=None, parent=None, metadata=None
    ):
        sequence = db.execute(
            "SELECT coalesce(max(sequence),0)+1 FROM conversation_messages "
            "WHERE conversation_id=? AND owner_id=?",
            (conversation_id, LOCAL_OWNER),
        ).fetchone()[0]
        if sequence > MAX_MESSAGES:
            raise AppError(
                "HISTORY_LIMIT_REACHED", "Start a new conversation after exporting this one", 409
            )
        identity, timestamp = str(uuid4()), now()
        db.execute(
            "INSERT INTO conversation_messages(id,owner_id,conversation_id,role,content,sequence,"
            "client_message_id,parent_message_id,metadata_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                identity,
                LOCAL_OWNER,
                conversation_id,
                role,
                content,
                sequence,
                client_id,
                parent,
                json.dumps(metadata or {}, ensure_ascii=False),
                timestamp,
            ),
        )
        db.execute(
            "UPDATE conversations SET updated_at=? WHERE id=? AND owner_id=?",
            (timestamp, conversation_id, LOCAL_OWNER),
        )
        result = db.execute(
            "SELECT * FROM conversation_messages WHERE id=?", (identity,)
        ).fetchone()
        return message_view(result)

    def record_assistant(self, conversation_id, content, metadata=None, *, parent_message_id=None):
        """Internal method only; clients cannot forge assistant messages through a public route."""
        content = checked_text(content)
        metadata = dict(metadata or {})
        if set(metadata) - {"model", "configuration_id", "source"}:
            raise AppError("INVALID_METADATA", "Only safe response attribution is allowed", 422)
        if any(not isinstance(value, str) or len(value) > 200 for value in metadata.values()):
            raise AppError("INVALID_METADATA", "Invalid response attribution", 422)
        if "configuration_id" in metadata:
            metadata["configuration_id"] = checked_id(metadata["configuration_id"])
        if "source" in metadata and metadata["source"] not in ("ai", "local-status"):
            raise AppError("INVALID_METADATA", "Invalid response source", 422)
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._conversation(db, conversation_id)
            if parent_message_id is not None:
                parent_message_id = checked_id(parent_message_id)
                parent = db.execute(
                    "SELECT id FROM conversation_messages WHERE id=? AND conversation_id=? "
                    "AND owner_id=? AND role='user'",
                    (parent_message_id, row["id"], LOCAL_OWNER),
                ).fetchone()
                if parent is None:
                    raise AppError("MESSAGE_NOT_FOUND", "Original user message does not exist", 404)
            return self._insert_message(
                db, row["id"], "assistant", content, parent=parent_message_id, metadata=metadata
            )

    def get_context(self, conversation_id, max_messages=6, max_chars=6000):
        """Only this conversation; bounds count message content Unicode characters."""
        if not 1 <= max_messages <= 20 or not 1 <= max_chars <= 12000:
            raise AppError("INVALID_INPUT", "Invalid context limit", 422)
        with connect(self.settings) as db:
            row = self._conversation(db, conversation_id)
            messages = db.execute(
                "SELECT role,content,sequence FROM conversation_messages "
                "WHERE conversation_id=? AND owner_id=? ORDER BY sequence DESC LIMIT ?",
                (row["id"], LOCAL_OWNER, max_messages),
            ).fetchall()
        selected, remaining = [], max_chars
        for message in messages:
            if not remaining:
                break
            value = dict(message)
            if len(value["content"]) > remaining:
                value["content"] = value["content"][:remaining]
                value["truncated"] = True
            selected.append(value)
            remaining -= len(value["content"])
        return list(reversed(selected))

    def export(self, conversation_id=None):
        with connect(self.settings) as db:
            if conversation_id is not None:
                conversations = [self._detail(db, conversation_id)]
            else:
                ids = db.execute(
                    "SELECT id FROM conversations WHERE owner_id=? ORDER BY created_at,id",
                    (LOCAL_OWNER,),
                ).fetchall()
                conversations = [self._detail(db, row["id"]) for row in ids]
            for conversation in conversations:
                demand = db.execute(
                    "SELECT * FROM demands WHERE conversation_id=? AND owner_id=?",
                    (conversation["id"], LOCAL_OWNER),
                ).fetchone()
                conversation["demands"] = []
                if demand:
                    versions = []
                    for row in db.execute(
                        "SELECT * FROM demand_versions WHERE demand_id=? ORDER BY number",
                        (demand["id"],),
                    ):
                        value = dict(row)
                        value["data"] = json.loads(value.pop("data_json"))
                        value["user_confirmed"] = value["status"] == "confirmed"
                        versions.append(value)
                    packets = [
                        bytes(row["packet_bytes"]).decode("utf-8")
                        for row in db.execute(
                            "SELECT packet_bytes FROM demand_packets "
                            "WHERE demand_id=? ORDER BY sequence",
                            (demand["id"],),
                        )
                    ]
                    conversation["demands"].append(
                        {
                            **dict(demand),
                            "versions": versions,
                            "packet_utf8": packets,
                            "network_transmitted": False,
                        }
                    )
        return {
            "schema": "demand-search.conversations.export/2",
            "exported_at": now(),
            "scope": "conversation" if conversation_id else "all_conversations",
            "includes_model_configuration": False,
            "conversations": conversations,
        }

    def delete_all(self):
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM conversations WHERE owner_id=?", (LOCAL_OWNER,)
            ).fetchone()[0]
            db.execute("DELETE FROM conversations WHERE owner_id=?", (LOCAL_OWNER,))
        return {
            "deleted": True,
            "deleted_conversations": count,
            "model_configurations_preserved": True,
        }
