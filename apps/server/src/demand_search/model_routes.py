"""HTTP contract for model configuration. Local session/CSRF enforced by application middleware."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Draft(StrictBody):
    name: str = Field(default="我的模型", min_length=1, max_length=80)
    provider: Literal["openai", "deepseek", "kimi", "qwen", "custom"]
    base_url: str = Field(min_length=1, max_length=500)
    api_mode: Literal["responses", "chat_completions"]
    model: str = Field(default="", max_length=200)
    api_key: SecretStr | None = None
    existing_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")
    consent: bool = False
    test_text: str = Field(default="想找一把预算1500元以内、适合久坐的办公椅。", max_length=8000)

    def payload(self):
        value = self.model_dump()
        value["api_key"] = self.api_key.get_secret_value() if self.api_key is not None else None
        return value


class Save(StrictBody):
    validation_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    make_active: bool = True


class Parse(StrictBody):
    text: str = Field(min_length=1, max_length=8000)
    consent: bool = False
    config_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")


def create_model_router(service):
    router = APIRouter(prefix="/api/v1")

    @router.get("/config/providers")
    def providers():
        return service.catalog()

    @router.get("/config/models")
    def profiles():
        return service.list()

    @router.post("/config/models/discover")
    def discover(body: Draft):
        return service.discover(body.payload())

    @router.post("/config/models/test")
    def test(body: Draft):
        return service.test(body.payload())

    @router.post("/config/models/save")
    def save(body: Save):
        return service.save(body.validation_id, body.make_active)

    @router.post("/config/models/{identifier}/activate")
    def activate(identifier: UUID):
        return service.activate(str(identifier))

    @router.delete("/config/models/{identifier}")
    def delete(identifier: UUID):
        return service.delete(str(identifier))

    @router.post("/config/parse")
    def parse(body: Parse):
        return service.parse(body.text, body.consent, body.config_id)

    return router
