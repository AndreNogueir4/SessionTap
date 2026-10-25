import hmac
import json
import time
from typing import Any
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
PUBLIC_PATHS = frozenset({"/v1/auth/exchange"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

MAX_BODY = 1024 * 1024
MAX_INGEST_BODY = 256 * 1024 * 1024

FAILED_AUTH_LIMIT = 20
FAILED_AUTH_WINDOW = 60.0

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        b"connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        b"form-action 'none'",
    ),
]


class SecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token_getter: Callable[[], str],
        port: int,
        require_loopback_peer: bool = True,
    ) -> None:
        self.app = app
        self.token_getter = token_getter
        self.require_loopback_peer = require_loopback_peer
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
        self._failures: deque[float] = deque()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        path: str = scope["path"]
        method: str = scope.get("method", "GET")
        client = scope.get("client")
        if self.require_loopback_peer and (not client or client[0] not in LOOPBACK_PEERS):
            await _reject(send, 403, "loopback connections only")
            return
        if headers.get("host") not in self.allowed_hosts:
            await _reject(send, 403, "invalid Host header")
            return
        origin = headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            await _reject(send, 403, "cross-origin requests are not allowed")
            return
        if headers.get("sec-fetch-site") == "cross-site":
            await _reject(send, 403, "cross-site requests are not allowed")
            return
        if path.startswith("/v1/") and path not in PUBLIC_PATHS:
            if self._throttled():
                await _reject(send, 429, "too many failed authentication attempts")
                return
            if not self._authorized(headers.get("authorization", "")):
                self._failures.append(time.monotonic())
                await _reject(
                    send, 401, "missing or invalid token", [(b"www-authenticate", b"Bearer")]
                )
                return
        if method in WRITE_METHODS:
            has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
            if has_body and not headers.get("content-type", "").startswith("application/json"):
                await _reject(send, 415, "request bodies must be application/json")
                return
            limit = MAX_INGEST_BODY if path == "/v1/ingest" else MAX_BODY
            try:
                declared = int(headers.get("content-length", "0"))
            except ValueError:
                await _reject(send, 400, "invalid Content-Length")
                return
            if declared > limit:
                await _reject(send, 413, "request body too large")
                return
            receive = _limited(receive, limit)
        await self.app(scope, receive, _with_headers(send, path))

    def _authorized(self, header: str) -> bool:
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            return False
        return hmac.compare_digest(supplied.strip().encode(), self.token_getter().encode())

    def _throttled(self) -> bool:
        now = time.monotonic()
        while self._failures and now - self._failures[0] > FAILED_AUTH_WINDOW:
            self._failures.popleft()
        return len(self._failures) >= FAILED_AUTH_LIMIT


class BodyTooLarge(Exception):
    pass


def _limited(receive: Receive, limit: int) -> Receive:
    seen = 0

    async def wrapped() -> Message:
        nonlocal seen
        message = await receive()
        if message["type"] == "http.request":
            seen += len(message.get("body", b""))
            if seen > limit:
                raise BodyTooLarge
        return message

    return wrapped


def _with_headers(send: Send, path: str) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.extend(SECURITY_HEADERS)
            if path.startswith("/v1/") or path == "/":
                headers.append((b"cache-control", b"no-store"))
            message["headers"] = headers
        await send(message)

    return wrapped


async def _reject(
    send: Send, status: int, detail: str, extra: list[tuple[bytes, bytes]] | None = None
) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
                *SECURITY_HEADERS,
                *(extra or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
