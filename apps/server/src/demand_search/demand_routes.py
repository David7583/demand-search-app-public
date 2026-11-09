"""S2 demand routes; application supplies loopback/session/CSRF protection."""

import asyncio
import json
import queue
import threading
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .demand_models import ConfirmRequest, ExportRequest, ParseRequest, WithdrawRequest
from .errors import AppError


def create_demand_router(service):
    router = APIRouter(prefix="/api/v1/conversations/{conversation_id}/demand")

    @router.get("")
    def detail(conversation_id: UUID):
        return service.get(str(conversation_id))

    @router.post("/parse")
    def parse(conversation_id: UUID, body: ParseRequest):
        return service.parse(str(conversation_id), body.model_dump())

    @router.post("/collaborate")
    async def collaborate(conversation_id: UUID, body: ParseRequest):
        # Bounded bridge: model I/O stays off the event loop. The surrounding local
        # security middleware keeps its provider concurrency slot until stream close.
        events = queue.Queue(maxsize=64)
        cancelled = threading.Event()

        def cancel_check():
            if cancelled.is_set():
                raise AppError("STREAM_CANCELLED", "连接已断开；请刷新查看已保存版本。", 409)

        def emit(event):
            while True:
                cancel_check()
                try:
                    events.put(event, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def worker():
            try:
                result = service.parse(
                    str(conversation_id),
                    body.model_dump(),
                    collaborative=True,
                    on_delta=lambda text: emit({"type": "delta", "text": text}),
                    cancel_check=cancel_check,
                )
                emit({"type": "complete", "view": result})
            except AppError as error:
                if not cancelled.is_set():
                    emit({"type": "error", "error": {"code": error.code, "message": error.message}})
            except Exception:
                if not cancelled.is_set():
                    emit(
                        {
                            "type": "error",
                            "error": {
                                "code": "COLLABORATION_FAILED",
                                "message": "协作未完成；旧记录保留，请刷新检查，不会自动重试。",
                            },
                        }
                    )

        async def stream():
            try:
                yield json.dumps({"type": "start", "provisional": True}) + "\n"
                threading.Thread(target=worker, name="demand-collaboration", daemon=True).start()
                while True:
                    try:
                        event = events.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.02)
                        continue
                    yield json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n"
                    if event["type"] in ("complete", "error"):
                        return
            finally:
                cancelled.set()

        return StreamingResponse(
            stream(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @router.post("/confirm")
    def confirm(conversation_id: UUID, body: ConfirmRequest):
        return service.confirm(str(conversation_id), body.model_dump())

    @router.post("/withdraw")
    def withdraw(conversation_id: UUID, body: WithdrawRequest):
        return service.withdraw(str(conversation_id), body.model_dump())

    @router.post("/export")
    def export(conversation_id: UUID, body: ExportRequest):
        return service.export(str(conversation_id), body.acknowledge_private_export)

    return router
