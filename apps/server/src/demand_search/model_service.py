"""Encrypted, explicitly verified configuration lifecycle; failures never replace a profile."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .errors import AppError
from .market_context import build_market_context
from .providers import PROVIDERS, ProviderClient, normalize_base
from .storage import LOCAL_OWNER, connect


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelService:
    def __init__(self, settings, vault, client=None):
        self.settings = settings
        self.vault = vault
        self.client = client or ProviderClient()

    def catalog(self):
        return {"providers": PROVIDERS, "secret_storage": "windows_dpapi_current_user"}

    @staticmethod
    def safe(row):
        return {
            **{
                key: row[key]
                for key in (
                    "id",
                    "name",
                    "provider",
                    "base_url",
                    "api_mode",
                    "model",
                    "verified_at",
                )
            },
            "key_mask": "已安全保存",
            "is_active": bool(row["is_active"]),
        }

    def _find(self, identifier):
        with connect(self.settings) as db:
            row = db.execute(
                "SELECT * FROM model_configs WHERE id=? AND owner_id=?", (identifier, LOCAL_OWNER)
            ).fetchone()
        if row is None:
            raise AppError("MODEL_CONFIG_NOT_FOUND", "配置不存在或已删除。", 404)
        return dict(row)

    def list(self):
        with connect(self.settings) as db:
            db.execute("DELETE FROM model_validation_tickets WHERE expires_at<=?", (now(),))
            rows = db.execute(
                "SELECT * FROM model_configs WHERE owner_id=? ORDER BY verified_at DESC,id",
                (LOCAL_OWNER,),
            ).fetchall()
        return {
            "configs": [self.safe(row) for row in rows],
            "active_id": next((row["id"] for row in rows if row["is_active"]), None),
        }

    def _prepare(self, draft):
        if draft.get("consent") is not True:
            raise AppError("AI_CONSENT_REQUIRED", "请先确认将Key及本次测试需求发送到所选服务商。")
        config = {key: draft[key] for key in ("name", "provider", "base_url", "api_mode", "model")}
        config["base_url"] = normalize_base(config["base_url"], config["provider"])
        provider = next((p for p in PROVIDERS if p["id"] == config["provider"]), None)
        if not provider or config["api_mode"] not in provider["api_modes"]:
            raise AppError("API_MODE_UNSUPPORTED", "所选服务商暂不支持此API模式。")
        existing = self._find(draft["existing_id"]) if draft.get("existing_id") else None
        key = draft.get("api_key")
        if not key:
            if not existing:
                raise AppError("MODEL_KEY_REQUIRED", "请输入API Key。")
            if (
                existing["provider"] != config["provider"]
                or existing["base_url"] != config["base_url"]
            ):
                raise AppError(
                    "NEW_KEY_REQUIRED", "更换服务商或API地址后必须重新输入Key，原Key不会转发。"
                )
            key = self.vault.unseal(existing["encrypted_secret"], existing["secret_context"])
        if (
            not isinstance(key, str)
            or not 8 <= len(key) <= 4096
            or any(not 33 <= ord(c) <= 126 for c in key)
        ):
            raise AppError(
                "MODEL_KEY_FORMAT_INVALID", "Key应为8–4096个可打印ASCII字符，不包含空格或换行。"
            )
        if any(key in value for value in config.values()):
            raise AppError("CREDENTIAL_IN_METADATA", "请勿在名称、地址或模型ID中填写Key。")
        return config, key, existing

    def discover(self, draft):
        config, key, _ = self._prepare(draft)
        try:
            return self.client.discover(config, key)
        finally:
            key = None

    def test(self, draft):
        config, key, existing = self._prepare(draft)
        if not config["model"].strip():
            raise AppError("MODEL_REQUIRED", "请选择或填写模型ID。")
        text = draft["test_text"]
        if not text.strip():
            raise AppError("TEST_TEXT_REQUIRED", "请输入一段需求用于真实解析测试。")
        if key in text:
            raise AppError("KEY_IN_TEST_TEXT", "需求测试文本中包含Key，请移除后再发送。")
        try:
            identifier = str(uuid4())
            context = "model-key:" + identifier
            encrypted = self.vault.seal(key, context)
            output = self.client.parse(config, key, text)
        finally:
            key = None
        verified = now()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            if existing:
                current = db.execute(
                    "SELECT revision FROM model_configs WHERE id=? AND owner_id=?",
                    (existing["id"], LOCAL_OWNER),
                ).fetchone()
                if current is None or current["revision"] != existing["revision"]:
                    raise AppError(
                        "CONFIG_CHANGED", "测试期间原配置已改变或删除，请重新测试。", 409
                    )
            db.execute("DELETE FROM model_validation_tickets WHERE expires_at<=?", (verified,))
            db.execute(
                """INSERT INTO model_validation_tickets
                (id,owner_id,name,provider,base_url,api_mode,model,encrypted_secret,secret_context,verified_at,expires_at,existing_id,expected_revision)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    LOCAL_OWNER,
                    config["name"],
                    config["provider"],
                    config["base_url"],
                    config["api_mode"],
                    config["model"],
                    encrypted,
                    context,
                    verified,
                    expires,
                    existing["id"] if existing else None,
                    existing["revision"] if existing else None,
                ),
            )
            db.execute(
                """DELETE FROM model_validation_tickets WHERE owner_id=? AND id NOT IN
                (SELECT id FROM model_validation_tickets WHERE owner_id=?
                ORDER BY verified_at DESC,id DESC LIMIT 20)""",
                (LOCAL_OWNER, LOCAL_OWNER),
            )
        return {
            "validation_id": identifier,
            "expires_at": expires,
            "result": {
                "requested_model": config["model"],
                "actual_model": output["actual_model"],
                "provider": config["provider"],
                "connection_status": "verified",
                "parsed": output["parsed"],
                "tested_at": verified,
            },
        }

    def save(self, validation_id, make_active=True):
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            ticket = db.execute(
                "SELECT * FROM model_validation_tickets WHERE id=? AND owner_id=?",
                (validation_id, LOCAL_OWNER),
            ).fetchone()
            if ticket is None or ticket["expires_at"] <= now():
                raise AppError("VALIDATION_EXPIRED", "验证已过期或已使用，请重新测试后保存。", 409)
            existing = None
            if ticket["existing_id"]:
                existing = db.execute(
                    "SELECT * FROM model_configs WHERE id=? AND owner_id=?",
                    (ticket["existing_id"], LOCAL_OWNER),
                ).fetchone()
                if not existing or existing["revision"] != ticket["expected_revision"]:
                    raise AppError("CONFIG_CHANGED", "原配置已改变或删除，请重新测试。", 409)
            identifier = existing["id"] if existing else str(uuid4())
            active = bool(make_active or (existing and existing["is_active"]))
            if active:
                db.execute("UPDATE model_configs SET is_active=0 WHERE owner_id=?", (LOCAL_OWNER,))
            values = (
                ticket["name"],
                ticket["provider"],
                ticket["base_url"],
                ticket["api_mode"],
                ticket["model"],
                ticket["encrypted_secret"],
                ticket["secret_context"],
                ticket["verified_at"],
                int(active),
            )
            if existing:
                db.execute(
                    """UPDATE model_configs SET name=?,provider=?,base_url=?,api_mode=?,model=?,
                    encrypted_secret=?,secret_context=?,verified_at=?,is_active=?,revision=revision+1
                    WHERE id=? AND owner_id=?""",
                    (*values, identifier, LOCAL_OWNER),
                )
            else:
                db.execute(
                    """INSERT INTO model_configs
                    (name,provider,base_url,api_mode,model,encrypted_secret,secret_context,verified_at,is_active,id,owner_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (*values, identifier, LOCAL_OWNER),
                )
            db.execute("DELETE FROM model_validation_tickets WHERE id=?", (validation_id,))
        return {"config": self.safe(self._find(identifier)), "active_id": self.list()["active_id"]}

    def activate(self, identifier):
        with connect(self.settings) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM model_configs WHERE id=? AND owner_id=?", (identifier, LOCAL_OWNER)
            ).fetchone()
            if not row:
                raise AppError("MODEL_CONFIG_NOT_FOUND", "配置不存在或已删除。", 404)
            db.execute("UPDATE model_configs SET is_active=0 WHERE owner_id=?", (LOCAL_OWNER,))
            db.execute(
                "UPDATE model_configs SET is_active=1 WHERE id=? AND owner_id=?",
                (identifier, LOCAL_OWNER),
            )
        return {"active_id": identifier}

    def delete(self, identifier):
        with connect(self.settings) as db:
            result = db.execute(
                "DELETE FROM model_configs WHERE id=? AND owner_id=?", (identifier, LOCAL_OWNER)
            )
            if not result.rowcount:
                raise AppError("MODEL_CONFIG_NOT_FOUND", "配置不存在或已删除。", 404)
            db.execute(
                "DELETE FROM model_validation_tickets WHERE existing_id=? AND owner_id=?",
                (identifier, LOCAL_OWNER),
            )
        return {"deleted": True, "active_id": self.list()["active_id"]}

    def parse(self, text, consent, config_id=None):
        if consent is not True:
            raise AppError("AI_CONSENT_REQUIRED", "请先允许向当前服务商发送本次需求。")
        identifier = config_id or self.list()["active_id"]
        if not identifier:
            raise AppError("MODEL_NOT_CONFIGURED", "尚未配置有效模型，请先完成初始化。", 409)
        config = self._find(identifier)
        key = self.vault.unseal(config["encrypted_secret"], config["secret_context"])
        if key in text:
            raise AppError("KEY_IN_TEST_TEXT", "输入中包含Key，请移除后再发送。")
        try:
            output = self.client.parse(config, key, text)
        finally:
            key = None
        return {
            "requested_model": config["model"],
            "actual_model": output["actual_model"],
            "provider": config["provider"],
            "connection_status": "verified",
            "parsed": output["parsed"],
            "tested_at": now(),
        }

    def parse_demand(
        self, text, context, consent, config_id=None, *, on_delta=None, collaborative=False
    ):
        from .ai_demand import parse_demand

        if consent is not True:
            raise AppError("AI_CONSENT_REQUIRED", "请先允许发送本次需求及有限上下文。")
        identifier = config_id or self.list()["active_id"]
        if not identifier:
            raise AppError("MODEL_NOT_CONFIGURED", "请先配置有效模型。", 409)
        config = self._find(identifier)
        key = self.vault.unseal(config["encrypted_secret"], config["secret_context"])
        try:
            kwargs = (
                {"on_delta": on_delta, "collaborative": collaborative}
                if on_delta is not None or collaborative
                else {}
            )
            if not isinstance(context, dict):
                raise AppError("INVALID_DEMAND_CONTEXT", "Demand context must be an object", 422)
            # Both parse and collaborative replies receive server-owned catalog awareness.
            # Copy the outer context; never modify stored/current/confirmed demand snapshots.
            context = {
                **context,
                "application_context": {"simulated_market": build_market_context(self.settings)},
            }
            output = parse_demand(self.client, config, key, text, context, **kwargs)
        finally:
            key = None
        return {
            "requested_model": config["model"],
            "actual_model": output["actual_model"],
            "provider": config["provider"],
            "parsed": output["parsed"],
            "tested_at": now(),
            "prompt_version": output["prompt_version"],
        }
