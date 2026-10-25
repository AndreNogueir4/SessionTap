import re
import json
import base64
from typing import Any
from collections.abc import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-csrf-token",
        "x-xsrf-token",
        "csrf-token",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
        "x-amz-security-token",
    }
)
_SENSITIVE_PARTS = ("token", "secret", "session", "auth", "api-key", "apikey", "password")

_BODY_TOKEN_KEYS = frozenset(
    {
        "access_token",
        "accessToken",
        "id_token",
        "idToken",
        "refresh_token",
        "refreshToken",
        "csrf_token",
        "csrfToken",
        "token",
        "jwt",
        "session_token",
        "sessionToken",
        "api_key",
    }
)

_JWT = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")
MIN_TOKEN_LENGTH = 16


def is_sensitive_header(name: str) -> bool:
    name = name.lower()
    return name in SENSITIVE_HEADERS or any(part in name for part in _SENSITIVE_PARTS)


def mask(value: str | None) -> str | None:
    if value is None:
        return None
    return f"•••• ({len(value)} chars)"


def mask_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: (mask(v) or "") if is_sensitive_header(k) else v for k, v in headers.items()}


def jwt_claims(value: str) -> dict[str, Any] | None:
    value = value.removeprefix("Bearer ").removeprefix("bearer ").strip()
    if not _JWT.match(value):
        return None
    payload = value.split(".")[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    return claims if isinstance(claims, dict) else None


def jwt_expiry(value: str) -> float | None:
    claims = jwt_claims(value)
    exp = claims.get("exp") if claims else None
    return float(exp) if isinstance(exp, int | float) else None


def tokens_from_headers(headers: dict[str, str]) -> Iterator[tuple[str, str]]:
    for name, value in headers.items():
        lname = name.lower()
        if lname in ("cookie", "set-cookie") or not is_sensitive_header(lname):
            continue
        if value:
            yield lname, value


def tokens_from_body(body: str | None, mime_type: str | None) -> Iterator[tuple[str, str]]:
    if not body or "json" not in (mime_type or ""):
        return
    try:
        data = json.loads(body)
    except ValueError:
        return
    yield from _walk(data, depth=0)


def _walk(node: Any, depth: int) -> Iterator[tuple[str, str]]:
    if depth > 4:
        return
    if isinstance(node, dict):
        for key, value in list(node.items())[:200]:
            if (
                key in _BODY_TOKEN_KEYS
                and isinstance(value, str)
                and len(value) >= MIN_TOKEN_LENGTH
            ):
                yield f"body:{key}", value
            elif isinstance(value, dict | list):
                yield from _walk(value, depth + 1)
    elif isinstance(node, list):
        for item in node[:20]:
            yield from _walk(item, depth + 1)


_SECRET_KEY_PARTS = ("password", "passwd", "pwd", "secret", "token", "otp", "jwt", "auth")


def _is_secret_key(key: str) -> bool:
    k = key.lower()
    return key in _BODY_TOKEN_KEYS or any(part in k for part in _SECRET_KEY_PARTS)


def _mask_json(node: Any, depth: int = 0) -> Any:
    if depth > 20:
        return node
    if isinstance(node, dict):
        return {
            k: (mask(v) if isinstance(v, str) and _is_secret_key(k) else _mask_json(v, depth + 1))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_mask_json(v, depth + 1) for v in node]
    return node


def mask_body(body: str | None, content_type: str | None) -> str | None:
    if not body:
        return body
    ctype = (content_type or "").lower()
    if "json" in ctype or body.lstrip()[:1] in ("{", "["):
        try:
            parsed = json.loads(body)
        except ValueError:
            return body
        masked = _mask_json(parsed)
        return body if masked == parsed else json.dumps(masked)
    if "x-www-form-urlencoded" in ctype:
        pairs = parse_qsl(body, keep_blank_values=True)
        if not any(_is_secret_key(k) for k, _ in pairs):
            return body
        return urlencode([(k, mask(v) if _is_secret_key(k) else v) for k, v in pairs])
    return body


def mask_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if not any(_is_secret_key(k) or k.lower() in ("key", "sig", "signature") for k, _ in pairs):
        return url
    masked = [
        (k, "****" if _is_secret_key(k) or k.lower() in ("key", "sig", "signature") else v)
        for k, v in pairs
    ]
    return urlunsplit(parts._replace(query=urlencode(masked)))
