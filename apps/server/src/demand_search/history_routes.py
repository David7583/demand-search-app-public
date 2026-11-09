"""Conversation routes; root app supplies local session and CSRF enforcement."""

from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from .history_service import HistoryService


class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=120)


class RenameConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)


class AddMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)
    client_message_id: UUID
    reference_version_id: UUID | None = None


def create_history_router(service: HistoryService):
    router = APIRouter(prefix="/api/v1")

    @router.get("/conversations")
    def list_conversations(
        query: str = Query(default="", max_length=200),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
    ):
        return service.list(query, limit, offset)

    @router.post("/conversations", status_code=201)
    def create_conversation(payload: CreateConversation):
        return service.create(payload.title)

    @router.get("/conversations/{conversation_id}")
    def get_conversation(conversation_id: UUID):
        return service.get(str(conversation_id))

    @router.patch("/conversations/{conversation_id}")
    def rename_conversation(conversation_id: UUID, payload: RenameConversation):
        return service.rename(str(conversation_id), payload.title)

    @router.delete("/conversations/{conversation_id}")
    def delete_conversation(conversation_id: UUID):
        return service.delete(str(conversation_id))

    @router.post("/conversations/{conversation_id}/messages")
    def add_message(conversation_id: UUID, payload: AddMessage):
        return service.add_message(
            str(conversation_id),
            payload.content,
            str(payload.client_message_id),
            reference_version_id=(
                str(payload.reference_version_id) if payload.reference_version_id else None
            ),
        )

    @router.get("/conversations/{conversation_id}/export")
    def export_conversation(conversation_id: UUID):
        return service.export(str(conversation_id))

    @router.get("/me/export")
    def export_all_conversations():
        return service.export()

    @router.delete("/me/data")
    def delete_all_conversations():
        return service.delete_all()

    return router
