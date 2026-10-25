import re
import json
from typing import Any
from sessiontap import __version__
from collections import defaultdict
from collections.abc import Iterable
from sessiontap.server import sensitive
from urllib.parse import parse_qsl, urlsplit

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HEX = re.compile(r"^[0-9a-f]{12,}$", re.I)
_NUM = re.compile(r"^\d+$")
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_DEPTH = 6
MAX_PROPERTIES = 100
EXAMPLE_ITEMS = 3
EXAMPLE_STRING = 300

_API_RESOURCE_TYPES = {"xhr", "fetch", "XHR", "Fetch", "xmlhttprequest"}


def _param_name(segment: str, previous: str | None) -> str | None:
    kind = None
    if _NUM.match(segment):
        kind = "id"
    elif _UUID.match(segment):
        kind = "uuid"
    elif _DATE.match(segment):
        kind = "date"
    elif _HEX.match(segment) or (_OPAQUE.match(segment) and any(c.isdigit() for c in segment)):
        kind = "key"
    if kind is None:
        return None
    if previous and previous.isalpha():
        stem = previous[:-1] if previous.endswith("s") and len(previous) > 3 else previous
        return f"{stem}_{kind}" if kind != "id" else f"{stem}Id"
    return kind


def template_path(path: str) -> tuple[str, list[str]]:
    templated, params = template_path_values(path)
    return templated, list(params)


def template_path_values(path: str) -> tuple[str, dict[str, str]]:
    segments = path.split("/")
    params: dict[str, str] = {}
    out = []
    previous = None
    for seg in segments:
        name = _param_name(seg, previous) if seg else None
        if name:
            base, n = name, 2
            while name in params:
                name, n = f"{base}{n}", n + 1
            params[name] = seg
            out.append("{" + name + "}")
        else:
            out.append(seg)
        previous = seg or previous
    return "/".join(out) or "/", params


def trim_example(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return None
    if isinstance(value, str) and len(value) > EXAMPLE_STRING:
        return value[:EXAMPLE_STRING] + "…"
    if isinstance(value, list):
        return [trim_example(v, depth + 1) for v in value[:EXAMPLE_ITEMS]]
    if isinstance(value, dict):
        items = list(value.items())[:MAX_PROPERTIES]
        return {str(k): trim_example(v, depth + 1) for k, v in items}
    return value


def json_example(body: str | None, content_type: str | None) -> Any:
    masked = _json_body(sensitive.mask_body(body, content_type))
    return None if masked is None else trim_example(masked)


def schema_of(value: Any, depth: int = 0) -> dict[str, Any]:
    if depth > MAX_DEPTH:
        return {}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        items: dict[str, Any] = {}
        for item in value[:20]:
            items = merge(items, schema_of(item, depth + 1))
        return {"type": "array", "items": items} if items else {"type": "array"}
    if isinstance(value, dict):
        props = {str(k): schema_of(v, depth + 1) for k, v in list(value.items())[:MAX_PROPERTIES]}
        return {"type": "object", "properties": props, "required": sorted(props)}
    return {}


def _types(schema: dict[str, Any]) -> list[str]:
    t = schema.get("type")
    if t is None:
        return []
    return list(t) if isinstance(t, list) else [t]


def merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if not a:
        return b
    if not b:
        return a
    types = sorted(set(_types(a)) | set(_types(b)))
    if "number" in types and "integer" in types:
        types.remove("integer")
    out: dict[str, Any] = {"type": types[0] if len(types) == 1 else types}
    if "object" in types:
        pa, pb = a.get("properties", {}), b.get("properties", {})
        props = {k: merge(pa.get(k, {}), pb.get(k, {})) for k in list({**pa, **pb})}
        required = set(a.get("required", props)) & set(b.get("required", props))
        if "object" not in _types(a) or "object" not in _types(b):
            required = set()
        out["properties"] = props
        out["required"] = sorted(required)
    if "array" in types:
        items = merge(a.get("items", {}), b.get("items", {}))
        if items:
            out["items"] = items
    return out


def _media(schema: dict[str, Any], example: Any) -> dict[str, Any]:
    return {"schema": schema, "example": example} if example is not None else {"schema": schema}


def _content_type(headers: dict[str, str]) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == "content-type"), None)


def _json_body(body: str | None) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def infer(domain: str, requests: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ops: dict[tuple[str, str], dict[str, Any]] = {}
    servers: set[str] = set()
    hosts_per_path: dict[str, set[str]] = defaultdict(set)
    for r in requests:
        if r.get("resource_type") and r["resource_type"] not in _API_RESOURCE_TYPES:
            continue
        parts = urlsplit(r["url"])
        origin = f"{parts.scheme}://{parts.netloc}"
        servers.add(origin)
        path, params = template_path_values(parts.path or "/")
        hosts_per_path[path].add(origin)
        key = (path, r["method"].lower())
        op = ops.setdefault(
            key,
            {
                "path_params": params,
                "query": {},
                "request": {},
                "request_example": None,
                "responses": {},
                "examples": {},
                "count": 0,
            },
        )
        op["count"] += 1
        masked_query = parse_qsl(
            urlsplit(sensitive.mask_url(r["url"])).query, keep_blank_values=True
        )
        for k, v in masked_query:
            op["query"].setdefault(k, v)
        req_type = _content_type(r.get("request_headers") or {})
        req_json = _json_body(r.get("request_body"))
        if req_json is not None:
            op["request"] = merge(op["request"], schema_of(req_json))
            if op["request_example"] is None:
                op["request_example"] = json_example(r.get("request_body"), req_type)
        status = str(r.get("status") or "default")
        resp = op["responses"].setdefault(status, {})
        if "json" in (r.get("mime_type") or "") and not r.get("body_truncated"):
            body = _json_body(r.get("response_body"))
            if body is not None:
                op["responses"][status] = merge(resp, schema_of(body))
                if status not in op["examples"]:
                    op["examples"][status] = json_example(
                        r.get("response_body"), r.get("mime_type")
                    )
    paths: dict[str, dict[str, Any]] = defaultdict(dict)
    for (path, method), op in sorted(ops.items()):
        parameters = [
            {"name": n, "in": "path", "required": True, "schema": {"type": "string"}, "example": v}
            for n, v in op["path_params"].items()
        ] + [
            {
                "name": n,
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "example": op["query"][n],
            }
            for n in sorted(op["query"])
        ]
        operation: dict[str, Any] = {
            "summary": f"{method.upper()} {path}",
            "x-sessiontap-observed": op["count"],
            "responses": {
                status: (
                    {
                        "description": f"Observed {status}",
                        "content": {"application/json": _media(schema, op["examples"].get(status))},
                    }
                    if schema
                    else {"description": f"Observed {status}"}
                )
                for status, schema in sorted(op["responses"].items())
            },
        }
        if parameters:
            operation["parameters"] = parameters
        if op["request"]:
            operation["requestBody"] = {
                "content": {"application/json": _media(op["request"], op["request_example"])}
            }
        if len(servers) > 1:
            operation["servers"] = [{"url": s} for s in sorted(hosts_per_path[path])]
        paths[path][method] = operation
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{domain} (observed)",
            "version": "observed",
            "description": (
                f"Inferred by SessionTap {__version__} from captured traffic. Examples are real "
                "observed values with credentials masked as ****. Undocumented APIs change "
                "without notice; respect the site's terms of service."
            ),
        },
        "servers": [{"url": s} for s in sorted(servers)],
        "paths": dict(paths),
    }
