import re
import json
from typing import Any
from sessiontap.server import sensitive
from urllib.parse import parse_qsl, urlsplit

MAX_DEPTH = 20
MAX_LEAVES = 5000
MAX_PROPERTIES = 200
MAX_HITS = 1000
SAMPLE_ITEMS = 50
EXAMPLE_CHARS = 80
VALUE_CHARS = 200
MAX_CHANGES = 100
SNIPPETS_PER_FIELD = 3
SEARCH_FIELDS = ("url", "request_headers", "request_body", "response_headers", "response_body")
_WHITESPACE = re.compile(r"\s+")


def _trim(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def _field_text(r: dict[str, Any], field: str) -> str:
    value = r.get(field)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    return value or ""


def search_request(
    r: dict[str, Any], pattern: re.Pattern[str], context: int
) -> list[dict[str, Any]]:
    hits = []
    for field in SEARCH_FIELDS:
        text = _field_text(r, field)
        count = 0
        snippets: list[str] = []
        for m in pattern.finditer(text):
            count += 1
            if len(snippets) < SNIPPETS_PER_FIELD:
                start, end = max(0, m.start() - context), min(len(text), m.end() + context)
                snippet = _WHITESPACE.sub(" ", text[start:end])
                snippets.append(("…" if start else "") + snippet + ("…" if end < len(text) else ""))
            if count >= MAX_HITS:
                break
        if count:
            hits.append({"field": field, "count": count, "snippets": snippets})
    return hits


def _type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def shape(value: Any, depth: int = 0) -> dict[str, Any]:
    kind = _type(value)
    if depth > MAX_DEPTH:
        return {"type": kind}
    if isinstance(value, list):
        items: dict[str, Any] = {}
        for item in value[:SAMPLE_ITEMS]:
            items = merge_shape(items, shape(item, depth + 1))
        return {"type": kind, "length": len(value), **({"items": items} if items else {})}
    if isinstance(value, dict):
        keys = list(value.items())[:MAX_PROPERTIES]
        out: dict[str, Any] = {
            "type": kind,
            "properties": {str(k): shape(v, depth + 1) for k, v in keys},
        }
        if len(value) > MAX_PROPERTIES:
            out["more_properties"] = len(value) - MAX_PROPERTIES
        return out
    if value is None:
        return {"type": kind}
    return {"type": kind, "example": _trim(value, EXAMPLE_CHARS)}


def merge_shape(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if not a:
        return b
    if not b:
        return a
    types = sorted(set(a["type"].split("|")) | set(b["type"].split("|")))
    out = {**a, "type": "|".join(types)}
    if "properties" in a or "properties" in b:
        pa, pb = a.get("properties", {}), b.get("properties", {})
        props = {}
        for key in {**pa, **pb}:
            merged = merge_shape(pa.get(key, {}), pb.get(key, {}))
            if key not in pa or key not in pb:
                merged = {**merged, "optional": True}
            props[key] = merged
        out["properties"] = props
    if "length" in a or "length" in b:
        out["length"] = max(a.get("length", 0), b.get("length", 0))
        items = merge_shape(a.get("items", {}), b.get("items", {}))
        if items:
            out["items"] = items
    if "example" not in out and "example" in b:
        out["example"] = b["example"]
    return out


def _flatten(
    node: Any, prefix: str, out: dict[str, tuple[Any, bool]], secret: bool, depth: int
) -> None:
    if len(out) >= MAX_LEAVES:
        return
    if isinstance(node, dict) and node and depth < MAX_DEPTH:
        for k, v in node.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten(v, key, out, sensitive.is_secret_key(str(k)), depth + 1)
    elif isinstance(node, list) and node and depth < MAX_DEPTH:
        for i, v in enumerate(node):
            _flatten(v, f"{prefix}[{i}]", out, secret, depth + 1)
    else:
        out[prefix or "$"] = (node, secret and isinstance(node, str))


def _pairs(pairs: list[tuple[str, str]], is_secret: Any) -> dict[str, tuple[Any, bool]]:
    grouped: dict[str, list[str]] = {}
    for k, v in pairs:
        grouped.setdefault(k, []).append(v)
    return {k: (v[0] if len(v) == 1 else v, bool(is_secret(k))) for k, v in grouped.items()}


def _body_leaves(body: str | None, content_type: str | None) -> dict[str, tuple[Any, bool]] | None:
    if not body:
        return {}
    ctype = (content_type or "").lower()
    if "json" in ctype or body.lstrip()[:1] in ("{", "["):
        try:
            parsed = json.loads(body)
        except ValueError:
            return None
        out: dict[str, tuple[Any, bool]] = {}
        _flatten(parsed, "", out, False, 0)
        return out
    if "x-www-form-urlencoded" in ctype:
        return _pairs(parse_qsl(body, keep_blank_values=True), sensitive.is_secret_key)
    return None


def _show(value: Any, secret: bool) -> Any:
    if secret:
        return sensitive.mask(value if isinstance(value, str) else json.dumps(value))
    return _trim(value, VALUE_CHARS)


def _compare(a: dict[str, tuple[Any, bool]], b: dict[str, tuple[Any, bool]]) -> dict[str, Any]:
    changes = []
    for key in {**a, **b}:
        va, vb = a.get(key), b.get(key)
        if va is not None and vb is not None and va[0] == vb[0]:
            continue
        change: dict[str, Any] = {"key": key}
        if va is not None:
            change["a"] = _show(*va)
        if vb is not None:
            change["b"] = _show(*vb)
        if va is None or vb is None:
            change["only_in"] = "a" if vb is None else "b"
        changes.append(change)
    out: dict[str, Any] = {"changes": changes[:MAX_CHANGES]}
    if len(changes) > MAX_CHANGES:
        out["more"] = len(changes) - MAX_CHANGES
    return out


def _headers(headers: dict[str, str]) -> dict[str, tuple[Any, bool]]:
    return {k.lower(): (v, sensitive.is_sensitive_header(k)) for k, v in headers.items()}


def _content_type(headers: dict[str, str]) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == "content-type"), None)


def _body_diff(a: dict[str, Any], b: dict[str, Any], part: str) -> dict[str, Any]:
    body_a, body_b = a[f"{part}_body"], b[f"{part}_body"]
    ctype_a = a["mime_type"] if part == "response" else _content_type(a["request_headers"])
    ctype_b = b["mime_type"] if part == "response" else _content_type(b["request_headers"])
    leaves_a, leaves_b = _body_leaves(body_a, ctype_a), _body_leaves(body_b, ctype_b)
    if leaves_a is not None and leaves_b is not None:
        return _compare(leaves_a, leaves_b)
    return {
        "equal": body_a == body_b,
        "a_size": len(body_a or ""),
        "b_size": len(body_b or ""),
    }


def diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    url_a, url_b = urlsplit(a["url"]), urlsplit(b["url"])
    fields = {
        "method": (a["method"], b["method"]),
        "host": (url_a.netloc, url_b.netloc),
        "path": (url_a.path, url_b.path),
        "status": (a["status"], b["status"]),
        "mime_type": (a["mime_type"], b["mime_type"]),
    }
    query = [
        _pairs(parse_qsl(u.query, keep_blank_values=True), sensitive.is_secret_param)
        for u in (url_a, url_b)
    ]
    return {
        "a": a["id"],
        "b": b["id"],
        "same_endpoint": all(fields[k][0] == fields[k][1] for k in ("method", "host", "path")),
        "request": {k: {"a": va, "b": vb} for k, (va, vb) in fields.items() if va != vb},
        "query": _compare(*query),
        "request_headers": _compare(_headers(a["request_headers"]), _headers(b["request_headers"])),
        "request_body": _body_diff(a, b, "request"),
        "response_headers": _compare(
            _headers(a["response_headers"]), _headers(b["response_headers"])
        ),
        "response_body": _body_diff(a, b, "response"),
    }
