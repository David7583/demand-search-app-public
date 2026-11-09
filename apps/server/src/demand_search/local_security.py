"""Loopback-only browser sessions and bounded JSON requests, without persistent tokens."""

import asyncio
import ipaddress
import secrets
import time
from collections import deque
from http.cookies import SimpleCookie

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

COOKIE_NAME = "dsa_local_session"
MAX_BODY = 65536


class LocalSessions:
    def __init__(self):
        self.records = {}
        self.bootstraps = deque()
        self.provider_calls = deque()

    def get(self, token):
        value = self.records.get(token or "")
        if value and value[1] > time.monotonic():
            return value[0]
        self.records.pop(token or "", None)
        return None

    def issue(self, token=None):
        existing = self.get(token)
        if existing:
            return token, existing
        now = time.monotonic()
        while self.bootstraps and self.bootstraps[0] < now - 60:
            self.bootstraps.popleft()
        if len(self.bootstraps) >= 30:
            return None
        self.bootstraps.append(now)
        self.records = {k: v for k, v in self.records.items() if v[1] > now}
        if len(self.records) >= 128:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.records[token] = (csrf, now + 8 * 3600)
        return token, csrf

    def allow_provider_call(self):
        now = time.monotonic()
        while self.provider_calls and self.provider_calls[0] < now - 60:
            self.provider_calls.popleft()
        if len(self.provider_calls) >= 20:
            return False
        self.provider_calls.append(now)
        return True


def cookie_token(headers):
    try:
        cookies = SimpleCookie()
        cookies.load(headers.get("cookie", ""))
        item = cookies.get(COOKIE_NAME)
        return item.value if item else None
    except Exception:
        return None


class LocalSecurityMiddleware:
    def __init__(self, app, sessions):
        self.app = app
        self.sessions = sessions
        self.outbound_slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        method, path = scope["method"], scope["path"]

        async def deny(code, message, status):
            response = JSONResponse(
                {"error": {"code": code, "message": message}}, status_code=status
            )
            response.headers["Cache-Control"] = "no-store"
            return await response(scope, receive, send)

        try:
            local = ipaddress.ip_address((scope.get("client") or ("",))[0]).is_loopback
        except ValueError:
            local = False
        if not local:
            return await deny("LOCAL_ONLY", "此服务仅允许本机访问。", 403)
        origin = headers.get("origin")
        own_origin = scope.get("scheme", "http") + "://" + headers.get("host", "")
        if (origin is not None and origin != own_origin) or headers.get(
            "sec-fetch-site"
        ) == "cross-site":
            return await deny("ORIGIN_DENIED", "请求来源不被允许，请从本地应用页面操作。", 403)
        if method == "OPTIONS":
            return await deny("ORIGIN_DENIED", "此本地接口不允许跨域请求。", 403)
        public = path in {
            "/healthz",
            "/api/v1/status",
            "/api/v1/session",
            "/api/v1/providers/status",
        }
        csrf = self.sessions.get(cookie_token(headers))
        if path.startswith("/api/") and not public and not csrf:
            return await deny("LOCAL_SESSION_REQUIRED", "本地会话已过期，请刷新页面。", 401)
        provider_call = path in {
            "/api/v1/config/models/discover",
            "/api/v1/config/models/test",
            "/api/v1/config/parse",
        } or (
            path.startswith("/api/v1/conversations/")
            and path.endswith(("/demand/parse", "/demand/collaborate"))
        )
        if method not in {"GET", "HEAD"} and path.startswith("/api/"):
            token = headers.get("x-dsa-csrf", "")
            if not csrf or not secrets.compare_digest(csrf.encode("ascii"), token.encode("utf-8")):
                return await deny("CSRF_REQUIRED", "请求校验失败，请刷新页面重试。", 403)
            if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                return await deny("JSON_REQUIRED", "此操作需要 JSON 请求。", 415)
            try:
                if int(headers.get("content-length", "0")) > MAX_BODY:
                    return await deny("REQUEST_TOO_LARGE", "请求内容过大。", 413)
            except ValueError:
                return await deny("INVALID_REQUEST", "请求格式无效。", 400)
            body = bytearray()
            deadline = time.monotonic() + 10
            try:
                while True:
                    event = await asyncio.wait_for(
                        receive(), max(0.01, deadline - time.monotonic())
                    )
                    if event["type"] != "http.request":
                        return
                    body.extend(event.get("body", b""))
                    if len(body) > MAX_BODY:
                        return await deny("REQUEST_TOO_LARGE", "请求内容过大。", 413)
                    if not event.get("more_body", False):
                        break
            except TimeoutError:
                return await deny("REQUEST_TIMEOUT", "请求接收超时。", 408)
            original_receive = receive
            consumed = False

            async def bounded_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = bounded_receive
        if provider_call and not self.sessions.allow_provider_call():
            return await deny("REQUEST_RATE_LIMITED", "模型请求过于频繁，请稍后重试。", 429)

        async def secure_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                items = list(message.get("headers", []))
                items += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        b"connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                        b"form-action 'self'; object-src 'none'",
                    ),
                ]
                message = {**message, "headers": items}
            await send(message)

        acquired = False
        response_started = False
        try:
            if provider_call:
                try:
                    await asyncio.wait_for(self.outbound_slots.acquire(), timeout=0.1)
                    acquired = True
                except TimeoutError:
                    return await deny("MODEL_BUSY", "已有模型请求正在处理，请稍后重试。", 429)
            await self.app(scope, receive, secure_send)
        except Exception:
            if not response_started:
                await deny(
                    "INTERNAL_ERROR", "Internal application error; no request data was logged.", 500
                )
        finally:
            if acquired:
                self.outbound_slots.release()
