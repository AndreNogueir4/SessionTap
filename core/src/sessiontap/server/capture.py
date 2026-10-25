from urllib.parse import urlsplit
from sessiontap.server import sensitive
from sessiontap.server.vault import Vault
from typing import Annotated, Any, Literal
from sessiontap.server.policy import Policy
from sessiontap.domains import host_of, matches
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

MAX_URL = 8192
MAX_HEADERS = 200
MAX_STORAGE_ITEMS = 500
MAX_STORAGE_VALUE = 64 * 1024
MAX_HTML_BYTES = 100 * 1024 * 1024

Url = Annotated[str, Field(min_length=1, max_length=MAX_URL)]
Headers = Annotated[
    dict[str, Annotated[str, Field(max_length=MAX_URL)]], Field(max_length=MAX_HEADERS)
]


class _Event(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)


class Exchange(_Event):
    type: Literal["exchange"]
    url: Url
    method: Annotated[str, Field(pattern=r"^[A-Z]{1,16}$")]
    request_headers: Headers = {}
    request_body: str | None = None
    status: Annotated[int, Field(ge=0, le=999)] | None = None
    response_headers: Headers = {}
    response_body: str | None = None
    mime_type: Annotated[str, Field(max_length=200)] | None = None
    resource_type: Annotated[str, Field(max_length=50)] | None = None
    started_at: float | None = None
    duration_ms: Annotated[float, Field(ge=0)] | None = None
    error: Annotated[str, Field(max_length=500)] | None = None


class Cookie(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Annotated[str, Field(min_length=1, max_length=4096)]
    value: Annotated[str, Field(max_length=16384)]
    domain: Annotated[str, Field(min_length=1, max_length=253)]
    path: Annotated[str, Field(max_length=1024)] = "/"
    secure: bool = False
    http_only: bool = False
    same_site: Annotated[str, Field(max_length=20)] | None = None
    expires: float | None = None


class CookieChange(_Event):
    type: Literal["cookie"]
    removed: bool = False
    cookie: Cookie


class CookieSnapshot(_Event):
    type: Literal["cookies"]
    domain: Annotated[str, Field(min_length=1, max_length=253)]
    cookies: Annotated[list[Cookie], Field(max_length=2000)]


StorageItems = Annotated[
    dict[
        Annotated[str, Field(max_length=1024)], Annotated[str, Field(max_length=MAX_STORAGE_VALUE)]
    ],
    Field(max_length=MAX_STORAGE_ITEMS),
]


class StorageSnapshot(_Event):
    type: Literal["storage"]
    origin: Url
    local: StorageItems = {}
    session: StorageItems = {}


Scalar = str | int | float | bool | None


class Fingerprint(_Event):
    type: Literal["fingerprint"]
    origin: Url
    data: Annotated[dict[str, Scalar | list[Scalar]], Field(max_length=50)]


AnyEvent = Exchange | CookieChange | CookieSnapshot | StorageSnapshot | Fingerprint
Event = Annotated[AnyEvent, Field(discriminator="type")]


EVENT_ADAPTER: TypeAdapter[AnyEvent] = TypeAdapter(Event)


class IngestBatch(BaseModel):
    events: Annotated[list[Any], Field(max_length=500)]

    def parsed(self) -> tuple[list[AnyEvent], int]:
        good: list[AnyEvent] = []
        invalid = 0
        for raw in self.events:
            try:
                good.append(EVENT_ADAPTER.validate_python(raw))
            except ValidationError:
                invalid += 1
        return good, invalid


class Ingestor:
    def __init__(self, vault: Vault, policy: Policy) -> None:
        self.vault = vault
        self.policy = policy

    def is_blocked(self, host: str) -> bool:
        return self.policy.blocks(host)

    def domain_for(self, host: str | None) -> str | None:
        if not host or self.is_blocked(host):
            return None
        return self.vault.capture_domain_for(host)

    def cookie_domain_for(self, cookie_domain: str) -> str | None:
        host = cookie_domain.lstrip(".").lower()
        domain = self.domain_for(host)
        if domain is not None:
            return domain
        for enabled in self.vault.capture_domains():
            if matches(enabled, host) and not self.is_blocked(enabled):
                return enabled
        return None

    def ingest(self, batch: IngestBatch) -> tuple[int, list[dict[str, Any]]]:
        events, dropped = batch.parsed()
        feed: list[dict[str, Any]] = []
        for event in events:
            summary = self._one(event)
            if summary is None:
                dropped += 1
            else:
                feed.append(summary)
        return dropped, feed

    def _one(
        self, event: Exchange | CookieChange | CookieSnapshot | StorageSnapshot | Fingerprint
    ) -> dict[str, Any] | None:
        match event:
            case Exchange():
                return self._exchange(event)
            case CookieChange():
                domain = self.cookie_domain_for(event.cookie.domain)
                if domain is None:
                    return None
                c = event.cookie
                if event.removed:
                    self.vault.remove_cookie(c.domain, c.name, c.path)
                else:
                    self.vault.upsert_cookie(domain, c.model_dump())
                    self._cookie_token(domain, c)
                return {
                    "type": "cookie",
                    "domain": domain,
                    "name": c.name,
                    "removed": event.removed,
                }
            case CookieSnapshot():
                domain = self.domain_for(event.domain.lstrip(".").lower())
                if domain is None:
                    return None
                cookies = [c for c in event.cookies if self.cookie_domain_for(c.domain) == domain]
                self.vault.replace_cookies(domain, [c.model_dump() for c in cookies])
                for c in cookies:
                    self._cookie_token(domain, c)
                return {"type": "cookies", "domain": domain, "count": len(cookies)}
            case StorageSnapshot():
                domain = self.domain_for(host_of(event.origin))
                if domain is None:
                    return None
                origin = _origin(event.origin)
                self.vault.replace_storage(domain, origin, "local", event.local)
                self.vault.replace_storage(domain, origin, "session", event.session)
                return {"type": "storage", "domain": domain, "origin": origin}
            case Fingerprint():
                domain = self.domain_for(host_of(event.origin))
                if domain is None:
                    return None
                self.vault.set_fingerprint(domain, _origin(event.origin), event.data)
                return {"type": "fingerprint", "domain": domain}

    def _exchange(self, ev: Exchange) -> dict[str, Any] | None:
        host = host_of(ev.url)
        domain = self.domain_for(host)
        if domain is None or host is None:
            return None
        data = ev.model_dump()
        page = is_html_page(ev.resource_type, ev.mime_type)
        if page and not self.policy.capture_html:
            data["response_body"] = None
        max_body = self.policy.max_body_bytes
        truncated = False
        for key in ("request_body", "response_body"):
            limit = MAX_HTML_BYTES if page and key == "response_body" else max_body
            body = data[key]
            if body is not None and len(body.encode("utf-8", errors="replace")) > limit:
                data[key] = body.encode("utf-8", errors="replace")[:limit].decode(
                    "utf-8", errors="ignore"
                )
                truncated = True
        data["body_truncated"] = truncated
        path = urlsplit(ev.url).path or "/"
        request_id = self.vault.add_request(domain, host, path, data)
        for kind, value in sensitive.tokens_from_headers(ev.request_headers):
            self.vault.upsert_token(domain, kind, value, path, sensitive.jwt_expiry(value))
        if not truncated:
            for kind, value in sensitive.tokens_from_body(ev.response_body, ev.mime_type):
                self.vault.upsert_token(domain, kind, value, path, sensitive.jwt_expiry(value))
        return {
            "type": "request",
            "id": request_id,
            "domain": domain,
            "host": host,
            "method": ev.method,
            "path": path,
            "status": ev.status,
        }

    def _cookie_token(self, domain: str, cookie: Cookie) -> None:
        expiry = sensitive.jwt_expiry(cookie.value)
        if expiry is not None:
            self.vault.upsert_token(domain, f"cookie:{cookie.name}", cookie.value, None, expiry)


def is_html_page(resource_type: str | None, mime_type: str | None) -> bool:
    return resource_type == "Document" and "html" in (mime_type or "").lower()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
