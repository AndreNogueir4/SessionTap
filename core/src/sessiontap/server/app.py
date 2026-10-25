import hmac
import json
import time
import asyncio
import secrets
import tempfile
from pathlib import Path
from importlib import resources
from sessiontap import __version__
from sessiontap.config import Config
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from sessiontap.server.vault import Vault
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from fastapi.staticfiles import StaticFiles
from sessiontap.server.health import session_health
from starlette.concurrency import run_in_threadpool
from sessiontap.server.policy import Policy, PolicyLocked
from fastapi import FastAPI, HTTPException, Query, Request
from collections.abc import AsyncIterator, Callable, Iterator
from sessiontap.server import bundle, codegen, openapi, sensitive
from sessiontap.server.security import BodyTooLarge, SecurityMiddleware
from sessiontap.domains import InvalidDomain, match_any, normalize_domain
from sessiontap.server.capture import Cookie, IngestBatch, Ingestor, MAX_HTML_BYTES
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)

RETENTION_TASK_INTERVAL = 3600
LOGIN_CODE_TTL = 60


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            if queue.qsize() < 1000:
                queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


@dataclass
class LoginCodes:
    codes: dict[str, float] = field(default_factory=dict)

    def create(self) -> str:
        now = time.monotonic()
        self.codes = {c: exp for c, exp in self.codes.items() if exp > now}
        code = secrets.token_urlsafe(32)
        self.codes[code] = now + LOGIN_CODE_TTL
        return code

    def redeem(self, supplied: str) -> bool:
        now = time.monotonic()
        for code, expires in list(self.codes.items()):
            if hmac.compare_digest(code.encode(), supplied.encode()):
                del self.codes[code]
                return expires > now
        return False


class CaptureToggle(BaseModel):
    capture: bool


class BlocklistEntry(BaseModel):
    domain: Annotated[str, Field(min_length=1, max_length=253)]


class SettingsPatch(BaseModel):
    retention_days: Annotated[int, Field(ge=1, le=365)] | None = None
    capture_html: bool | None = None
    max_body_kb: Annotated[int, Field(ge=0, le=4096)] | None = None


class CodeExchange(BaseModel):
    code: Annotated[str, Field(min_length=10, max_length=100)]


class ImportedToken(BaseModel):
    kind: Annotated[str, Field(min_length=1, max_length=100)]
    value: Annotated[str, Field(min_length=1, max_length=16384)]
    expires_at: float | None = None


class SessionImport(BaseModel):
    domain: str
    cookies: Annotated[list[Cookie], Field(max_length=2000)] = []
    storage: dict[str, dict[str, dict[str, str]]] = {}
    tokens: Annotated[list[ImportedToken], Field(max_length=1000)] = []
    fingerprint: dict[str, Any] | None = None


def _domain(value: str) -> str:
    try:
        return normalize_domain(value)
    except InvalidDomain as e:
        raise HTTPException(422, str(e)) from e


def _header(headers: dict[str, str], name: str) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == name), None)


def _web_root() -> Path | None:
    root = Path(str(resources.files("sessiontap.server") / "web"))
    return root if (root / "index.html").exists() else None


_NO_DASHBOARD = """<!doctype html><meta charset="utf-8"><title>SessionTap</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>SessionTap is running</h1>
<p>The dashboard is not built into this installation. From a source checkout run
<code>npm install &amp;&amp; npm run build -w dashboard</code>, or use the API and SDKs.</p>
</body>"""


def create_app(
    vault: Vault,
    config: Config,
    token_getter: Callable[[], str],
    *,
    key_backend: str = "unknown",
    require_loopback_peer: bool = True,
) -> FastAPI:
    bus = EventBus()
    codes = LoginCodes()
    policy = Policy(vault, config)
    ingestor = Ingestor(vault, policy)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def retention_loop() -> None:
            while True:
                await run_in_threadpool(vault.apply_retention)
                await asyncio.sleep(RETENTION_TASK_INTERVAL)

        task = asyncio.create_task(retention_loop())
        yield
        task.cancel()

    app = FastAPI(
        title="SessionTap",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(PolicyLocked)
    async def _locked(_: Request, e: PolicyLocked) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=403)

    @app.exception_handler(BodyTooLarge)
    async def _too_large(_: Request, __: BodyTooLarge) -> JSONResponse:
        return JSONResponse({"detail": "request body too large"}, status_code=413)

    def ensure_known(domain: str) -> str:
        domain = _domain(domain)
        if vault.known_domain_for(domain) is None:
            raise HTTPException(404, "unknown domain")
        return domain

    @app.post("/v1/auth/login-code")
    def login_code() -> dict[str, Any]:
        return {"code": codes.create(), "expires_in": LOGIN_CODE_TTL}

    @app.post("/v1/auth/exchange")
    def exchange(body: CodeExchange) -> dict[str, str]:
        if not codes.redeem(body.code):
            raise HTTPException(401, "invalid or expired code")
        return {"token": token_getter()}

    @app.get("/v1/status")
    def status() -> dict[str, Any]:
        return {
            "version": __version__,
            "key_backend": key_backend,
            "vault_bytes": vault.size_bytes(),
            "retention_days": vault.retention_days,
            "capture_domains": vault.capture_domains(),
            "counts": vault.stats(),
        }

    @app.get("/v1/capture-state")
    def capture_state() -> dict[str, Any]:
        return {
            "domains": vault.capture_domains(),
            "blocklist": list(policy.blocklist),
            "max_body_bytes": policy.max_body_bytes,
            "capture_html": policy.capture_html,
            "max_html_bytes": MAX_HTML_BYTES,
            "port": config.port,
        }

    @app.get("/v1/settings")
    def get_settings() -> dict[str, Any]:
        return {
            "retention_days": vault.retention_days,
            "blocklist": list(policy.blocklist),
            "capture_html": policy.capture_html,
            "max_body_kb": policy.max_body_kb,
            "locked": policy.locked,
            "port": config.port,
        }

    @app.patch("/v1/settings")
    def patch_settings(patch: SettingsPatch) -> dict[str, Any]:
        policy.update(patch.capture_html, patch.max_body_kb)
        if patch.retention_days is not None:
            vault.retention_days = patch.retention_days
            vault.apply_retention()
        return get_settings()

    def blocklist_view() -> dict[str, Any]:
        defaults = set(policy.defaults)
        return {
            "domains": [{"domain": d, "default": d in defaults} for d in sorted(policy.blocklist)],
            "removed_defaults": sorted(defaults - set(policy.blocklist)),
            "customized": policy.customized,
            "locked": policy.locked,
        }

    @app.get("/v1/blocklist")
    def get_blocklist() -> dict[str, Any]:
        return blocklist_view()

    @app.post("/v1/blocklist")
    def add_to_blocklist(entry: BlocklistEntry) -> dict[str, Any]:
        domain = _domain(entry.domain)
        try:
            policy.block(domain)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        for enabled in vault.capture_domains():
            if match_any(enabled, [domain]):
                vault.set_capture(enabled, False)
                bus.publish({"type": "capture", "domain": enabled, "capture": False})
        return blocklist_view()

    @app.delete("/v1/blocklist/{domain}")
    def remove_from_blocklist(domain: str) -> dict[str, Any]:
        policy.unblock(_domain(domain))
        return blocklist_view()

    @app.post("/v1/blocklist/reset")
    def reset_blocklist() -> dict[str, Any]:
        policy.reset_blocklist()
        return blocklist_view()

    @app.get("/v1/domains")
    def domains() -> list[dict[str, Any]]:
        return vault.list_domains()

    @app.put("/v1/domains/{domain}")
    def set_capture(domain: str, body: CaptureToggle) -> dict[str, Any]:
        domain = _domain(domain)
        if body.capture and policy.blocks(domain):
            raise HTTPException(
                403,
                f"{domain} is on the blocklist; if you really need it, remove "
                "it in the dashboard (Settings → Blocklist) or with `sessiontap blocklist remove`",
            )
        vault.set_capture(domain, body.capture)
        bus.publish({"type": "capture", "domain": domain, "capture": body.capture})
        return {"domain": domain, "capture": body.capture}

    @app.get("/v1/domains/{domain}/summary")
    def domain_summary(domain: str) -> dict[str, Any]:
        domain = _domain(domain)
        known = vault.known_domain_for(domain)
        if known is None:
            return {"domain": domain, "known": False}
        row = next(d for d in vault.list_domains() if d["domain"] == known)
        health = session_health(vault, known)
        return {
            "domain": known,
            "known": True,
            "capture": row["capture"],
            "last_seen": row["last_seen"],
            "counts": {
                "requests": row["requests"],
                "cookies": row["cookies"],
                "tokens": len(health["tokens"]),
                "storage": row["storage"],
            },
            "health": {"status": health["status"], "next_expiry": health["next_expiry"]},
            "cookies": health["cookies"][:100],
            "tokens": [
                {"kind": t["kind"], "jwt": t["jwt"], "expires": t["expires"], "state": t["state"]}
                for t in health["tokens"]
            ],
            "recent": vault.list_requests(known, limit=5),
        }

    @app.delete("/v1/domains/{domain}")
    def delete_domain(domain: str) -> dict[str, Any]:
        domain = _domain(domain)
        vault.delete_domain(domain)
        bus.publish({"type": "purged", "domain": domain})
        return {"deleted": domain}

    @app.get("/v1/requests")
    def list_requests(
        domain: str | None = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, Any]]:
        return vault.list_requests(_domain(domain) if domain else None, q, limit, offset)

    def load_request(request_id: int) -> dict[str, Any]:
        r = vault.get_request(request_id)
        if r is None:
            raise HTTPException(404, "request not found")
        return r

    @app.get("/v1/requests/{request_id}")
    def get_request(
        request_id: int,
        reveal: bool = False,
        body_limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> dict[str, Any]:
        r = load_request(request_id)
        if not reveal:
            req_type = _header(r["request_headers"], "content-type")
            r["request_body"] = sensitive.mask_body(r["request_body"], req_type)
            r["response_body"] = sensitive.mask_body(r["response_body"], r["mime_type"])
            r["request_headers"] = sensitive.mask_headers(r["request_headers"])
            r["response_headers"] = sensitive.mask_headers(r["response_headers"])
            r["url"] = sensitive.mask_url(r["url"])
        for key in ("request_body", "response_body"):
            body = r[key]
            r[f"{key}_size"] = len(body) if body else 0
            if body_limit and body and len(body) > body_limit:
                r[key] = body[:body_limit]
        return r

    @app.get("/v1/requests/{request_id}/body")
    def get_request_body(
        request_id: int, part: Literal["request", "response"] = "response", reveal: bool = False
    ) -> Response:
        r = get_request(request_id, reveal)
        body = r[f"{part}_body"] or ""
        ext = "html" if "html" in (r["mime_type"] or "") and part == "response" else "txt"
        return Response(
            body,
            media_type="text/plain; charset=utf-8",
            headers={
                "content-disposition": f'attachment; filename="request-{request_id}-{part}.{ext}"'
            },
        )

    @app.get("/v1/requests/{request_id}/code", response_class=PlainTextResponse)
    def request_code(
        request_id: int,
        lang: Literal["curl", "python", "javascript"] = "curl",
        include_secrets: bool = False,
    ) -> str:
        return codegen.generate(load_request(request_id), lang, include_secrets)

    @app.get("/v1/sessions/{domain}")
    def get_session(domain: str, subdomains: bool = True) -> dict[str, Any]:
        domain = ensure_known(domain)
        known = vault.known_domain_for(domain) or domain
        fingerprint = vault.fingerprint_for(known)
        return {
            "domain": domain,
            "cookies": vault.cookies_for(domain, subdomains),
            "storage": vault.storage_for(known),
            "user_agent": (fingerprint or {}).get("userAgent"),
            "fingerprint": fingerprint,
        }

    @app.get("/v1/sessions/{domain}/health")
    def get_health(domain: str) -> dict[str, Any]:
        domain = ensure_known(domain)
        return session_health(vault, vault.known_domain_for(domain) or domain)

    @app.get("/v1/sessions/{domain}/secret")
    def get_secret(domain: str, name: Annotated[str, Query(max_length=100)]) -> dict[str, Any]:
        domain = ensure_known(domain)
        value = vault.latest_token(vault.known_domain_for(domain) or domain, name.lower())
        if value is None:
            raise HTTPException(404, f"no captured value for {name!r}")
        return {"name": name.lower(), "value": value}

    @app.post("/v1/sessions/import")
    def import_session(data: SessionImport) -> dict[str, Any]:
        domain = _domain(data.domain)
        if policy.blocks(domain):
            raise HTTPException(403, f"{domain} is on the blocklist")
        vault.replace_cookies(domain, [c.model_dump() for c in data.cookies])
        for origin, areas in data.storage.items():
            for area in ("local", "session"):
                vault.replace_storage(domain, origin, area, areas.get(area, {}))
        for t in data.tokens:
            vault.upsert_token(domain, t.kind, t.value, "import", t.expires_at)
        if data.fingerprint:
            vault.set_fingerprint(domain, f"https://{domain}", data.fingerprint)
        return {"imported": domain, "cookies": len(data.cookies), "tokens": len(data.tokens)}

    @app.get("/v1/tokens")
    def tokens(domain: str | None = None, reveal: bool = False) -> list[dict[str, Any]]:
        items = vault.list_tokens(_domain(domain) if domain else None)
        for t in items:
            claims = sensitive.jwt_claims(t["value"])
            t["jwt"] = claims is not None
            if not reveal:
                t["value"] = sensitive.mask(t["value"])
        return items

    @app.get("/v1/openapi/{domain}")
    def get_openapi(domain: str) -> dict[str, Any]:
        domain = ensure_known(domain)
        known = vault.known_domain_for(domain) or domain
        return openapi.infer(domain, vault.iter_requests(known, api_only=True))

    @app.get("/v1/export/{domain}/bundle")
    async def export_bundle(domain: str) -> StreamingResponse:
        domain = ensure_known(domain)
        known = vault.known_domain_for(domain) or domain
        spool = tempfile.TemporaryFile()  # noqa: SIM115
        await run_in_threadpool(bundle.build, vault, known, spool)
        spool.seek(0)

        def chunks() -> Iterator[bytes]:
            with spool:
                while chunk := spool.read(1024 * 1024):
                    yield chunk

        return StreamingResponse(
            chunks(),
            media_type="application/zip",
            headers={"content-disposition": f'attachment; filename="{known}-sessiontap.zip"'},
        )

    @app.post("/v1/ingest")
    async def ingest(batch: IngestBatch) -> dict[str, Any]:
        dropped, feed = await run_in_threadpool(ingestor.ingest, batch)
        for event in feed:
            bus.publish(event)
        return {"accepted": len(feed), "dropped": dropped}

    @app.get("/v1/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream() -> AsyncIterator[bytes]:
            async with bus.subscribe() as queue:
                yield b": connected\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield b": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n".encode()

        return StreamingResponse(stream(), media_type="text/event-stream")

    web = _web_root()
    if web is not None:
        if (web / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(web / "index.html")

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon() -> FileResponse:
            return FileResponse(web / "favicon.svg", media_type="image/svg+xml")
    else:

        @app.get("/", include_in_schema=False)
        def index_missing() -> HTMLResponse:
            return HTMLResponse(_NO_DASHBOARD)

    app.add_middleware(
        SecurityMiddleware,
        token_getter=token_getter,
        port=config.port,
        require_loopback_peer=require_loopback_peer,
    )
    app.state.vault = vault
    app.state.bus = bus
    return app
