"""Local search planning routes protected by the root app session/CSRF middleware."""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from .product_sources import ProductSearchPlanService


class SearchPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: UUID
    item_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=30)


def create_product_router(service: ProductSearchPlanService):
    router = APIRouter(prefix="/api/v1/conversations/{conversation_id}/demand")

    @router.post("/search-plan")
    def search_plan(conversation_id: UUID, body: SearchPlanRequest):
        return service.plan(
            str(conversation_id),
            str(body.version_id),
            None if body.item_ids is None else [str(value) for value in body.item_ids],
        )

    return router
