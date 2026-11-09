"""Synthetic catalog APIs reuse the app's local session and CSRF middleware."""

from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict


class MarketMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: UUID


def create_market_router(service):
    router = APIRouter(prefix="/api/v1")

    @router.get("/simulated-market")
    def browse(
        query: str = Query(default="", max_length=200),
        category: str = Query(default="", max_length=80),
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=12, ge=1, le=60),
    ):
        return service.browse(query, category, page, page_size)

    @router.get("/simulated-market/merchants/{merchant_id}")
    def merchant(merchant_id: UUID):
        return service.merchant(str(merchant_id))

    @router.post("/conversations/{conversation_id}/demand/simulated-market")
    def match(conversation_id: UUID, body: MarketMatchRequest):
        return service.match(str(conversation_id), str(body.version_id))

    return router
