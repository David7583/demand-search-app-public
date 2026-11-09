"""S2 local application; configuration never implies external integrations are live."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .config import ROOT, Settings
from .demand_routes import create_demand_router
from .demand_service import DemandService
from .errors import AppError
from .history_routes import create_history_router
from .history_service import HistoryService
from .local_security import COOKIE_NAME, LocalSecurityMiddleware, LocalSessions, cookie_token
from .market_routes import create_market_router
from .model_routes import create_model_router
from .model_service import ModelService
from .product_routes import create_product_router
from .product_sources import SOURCES, ProductSearchPlanService
from .secret_vault import WindowsDPAPIVault
from .simulated_market import SimulatedMarketService
from .storage import initialize, readiness


def create_app(
    settings: Settings | None = None, *, provider_client=None, secret_vault=None, client_assets=None
) -> FastAPI:
    settings = settings or Settings.from_env()
    vault = secret_vault or WindowsDPAPIVault()
    sessions = LocalSessions()
    models = ModelService(settings, vault, provider_client)
    history = HistoryService(settings)
    demands = DemandService(settings, models)

    @asynccontextmanager
    async def lifespan(_app):
        initialize(settings)
        yield

    app = FastAPI(
        title="Demand Search App — S2 local",
        version="0.0.3.dev0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.models = models
    app.state.history = history
    app.state.demands = demands
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.add_middleware(LocalSecurityMiddleware, sessions=sessions)

    @app.exception_handler(AppError)
    async def known_error(_request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        # Pydantic errors can contain api_key in input/context. Never serialize them.
        return JSONResponse(
            {"error": {"code": "INVALID_REQUEST", "message": "输入格式或长度无效，请检查必填项。"}},
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        messages = {404: "接口或资源不存在。", 405: "不支持此请求方式。"}
        return JSONResponse(
            {
                "error": {
                    "code": "HTTP_ERROR",
                    "message": messages.get(exc.status_code, "请求未能完成。"),
                }
            },
            status_code=exc.status_code,
        )

    @app.get("/healthz")
    async def health():
        healthy = readiness(settings)
        return JSONResponse(
            {"status": "ok" if healthy else "not_ready", "stage": "S2"},
            status_code=200 if healthy else 503,
        )

    @app.get("/api/v1/session")
    async def session(request: Request):
        value = sessions.issue(cookie_token(request.headers))
        if value is None:
            raise AppError("SESSION_RATE_LIMITED", "本地会话创建过于频繁，请稍后重试。", 429)
        token, csrf = value
        response = JSONResponse(
            {
                "csrf_token": csrf,
                "mode": "local-dev",
                "credential_entry_allowed": bool(vault.available),
                "secret_storage": vault.storage_name,
                "hosted_supported": False,
            }
        )
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=8 * 3600,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    @app.get("/api/v1/status")
    async def status():
        active = models.list()["active_id"] is not None
        return {
            "stage": "S2",
            "mode": "local-dev",
            "ai_configured": active,
            "connection_status": "saved_previous_verification" if active else "not_configured",
            "search_enabled": False,
            "simulated_market": {
                "enabled": True,
                "data_origin": "synthetic",
                "merchants": 500,
                "offerings": 1500,
                "network_transport": False,
                "support": "local_capability_and_proposal_simulation",
            },
            "history_enabled": True,
            "demand_versions_enabled": True,
            "ncp": {"wire": "ODIP/0.1.3-exp.1", "support": "local_intent_lifecycle_only"},
            "publication": "local_development_only",
            "public_deployment_blocked": True,
        }

    @app.get("/api/v1/providers/status")
    async def providers():
        return {
            "providers": [
                {
                    "id": source.id,
                    "status": "not_configured",
                    "product_search_verified": False,
                    "market": source.market,
                    "label": source.label,
                    "label_en": source.label_en,
                }
                for source in SOURCES
            ]
        }

    app.include_router(create_market_router(SimulatedMarketService(settings)))
    app.include_router(create_model_router(models))
    app.include_router(create_history_router(history))
    app.include_router(create_demand_router(demands))
    app.include_router(create_product_router(ProductSearchPlanService(settings)))
    assets = ROOT / "apps/client/dist/h5"
    if client_assets is not None:
        # Explicit test factory argument only, never a hosted/environment override.
        if not settings.data_dir.name.startswith("test-"):
            raise ValueError("STAGED_ASSETS_REQUIRE_TEST_DATA")
        assets = client_assets.resolve()
        if not assets.is_relative_to((ROOT / ".local").resolve()):
            raise ValueError("STAGED_ASSETS_OUTSIDE_PRIVATE_TEST_DIRECTORY")
    if (assets / "index.html").is_file():
        app.mount("/", StaticFiles(directory=assets, html=True), name="local-h5")
    else:

        @app.get("/")
        async def missing_build():
            return JSONResponse(
                {"error": {"code": "CLIENT_BUILD_REQUIRED", "message": "请先执行本项目 H5 构建。"}},
                status_code=503,
            )

    return app
