import re
import json
import zipfile
from typing import Any, IO
from datetime import datetime, UTC
from sessiontap import __version__
from sessiontap.server.vault import Vault
from sessiontap.server import openapi, sensitive
from sessiontap.server.capture import is_html_page
from sessiontap.server.health import session_health

_UNSAFE = re.compile(r"[^A-Za-z0-9._{}-]+")

README = """# {domain} — SessionTap bundle

Captured by SessionTap {version} on {created}. Everything here was recorded from a
real, logged-in browser session: {requests} requests ({pages} HTML pages) across
{hosts} host(s).

## Files

- `openapi.json`: inferred API description with real example values (OpenAPI 3.1).
  Start here.
- `timeline.json`: every request in the order it happened, with links to its files. Use
  it to follow flows: login, redirects, a CSRF token read from one response and sent in a
  later request.
- `session.json`: cookie names, token kinds, storage keys and the browser profile. No
  values.
- `endpoints/<METHOD>_<host><path>/NNNN.json`: one captured exchange (URL, headers,
  status, timing). `NNNN` is its position in the timeline.
- `endpoints/.../NNNN.request.*`: the request body, when there was one.
- `endpoints/.../NNNN.response.json` / `.html` / `.txt`: the full response body. `.html`
  files are complete pages as the browser received them.

## Rules for writing a script from this bundle

1. **Never hardcode credentials.** Values shown as `****` are secrets the user keeps
   in SessionTap. Load them at run time:

    ```python
    import sessiontap

    client = sessiontap.httpx_client("{domain}")                 # cookies + user agent
    token = sessiontap.secret("{domain}", "authorization")       # e.g. a Bearer header
    ```

    ```js
    import {{ SessionTap }} from "sessiontap";
    const tap = new SessionTap();
    const headers = await tap.headers("{domain}");
    ```

2. **Do not ask the user to paste cookies or tokens.** If the session expired, ask them
   to open the site in their browser with SessionTap recording that tab.
3. To find where a value comes from, search the `endpoints/` files for it, then check
   `timeline.json` for the request order.
4. For HTML pages, parse the saved `.html` with a real parser (selectolax, BeautifulSoup,
   cheerio), not regular expressions. Look for embedded JSON (`<script type="application/json">`,
   `__NEXT_DATA__`, `window.__INITIAL_STATE__`) first: it is usually easier than the markup.
5. Respect the site's terms of service and rate limits. Undocumented APIs change without
   notice.

## Privacy

Credential headers, cookie values and credential-looking fields are masked. Response
bodies, and especially HTML pages, can still contain personal data and embedded tokens
(for example a CSRF token in a `<meta>` tag). Review the bundle before sharing it.
"""


def build(vault: Vault, domain: str, out: IO[bytes]) -> dict[str, int]:
    health = session_health(vault, domain)
    timeline: list[dict[str, Any]] = []
    hosts: set[str] = set()
    pages = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for seq, r in enumerate(vault.iter_requests(domain), start=1):
            entry = _write_exchange(z, seq, r)
            timeline.append(entry)
            hosts.add(r["host"])
            pages += is_html_page(r["resource_type"], r["mime_type"])
        _json(z, "timeline.json", timeline)
        spec = openapi.infer(domain, vault.iter_requests(domain, api_only=True))
        _json(z, "openapi.json", spec)
        _json(z, "session.json", _session(vault, domain, health))
        created = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        z.writestr(
            "README.md",
            README.format(
                domain=domain,
                version=__version__,
                created=created,
                requests=len(timeline),
                pages=pages,
                hosts=len(hosts),
            ),
        )
    return {"requests": len(timeline), "pages": pages}


def endpoint_dir(method: str, host: str, path: str) -> str:
    templated, _ = openapi.template_path(path)
    name = _UNSAFE.sub("_", f"{method}_{host}{templated.replace('/', '_')}").strip("_")
    return f"endpoints/{name[:150]}"


def _write_exchange(z: zipfile.ZipFile, seq: int, r: dict[str, Any]) -> dict[str, Any]:
    folder = endpoint_dir(r["method"], r["host"], r["path"])
    base = f"{folder}/{seq:04d}"
    req_type = _header(r["request_headers"], "content-type")
    files = {"exchange": f"{base}.json"}
    request_body = sensitive.mask_body(r["request_body"], req_type)
    if request_body:
        files["request_body"] = f"{base}.request.{_extension(req_type, request_body)}"
        z.writestr(files["request_body"], request_body)
    response_body = r["response_body"]
    if response_body:
        page = is_html_page(r["resource_type"], r["mime_type"])
        response_body = (
            response_body if page else sensitive.mask_body(response_body, r["mime_type"])
        )
        ext = "html" if page else _extension(r["mime_type"], response_body or "")
        files["response_body"] = f"{base}.response.{ext}"
        z.writestr(files["response_body"], _pretty(response_body or "", ext))
    url = sensitive.mask_url(r["url"])
    exchange = {
        "seq": seq,
        "id": r["id"],
        "started_at": _iso(r["started_at"]),
        "duration_ms": r["duration_ms"],
        "request": {
            "method": r["method"],
            "url": url,
            "headers": sensitive.mask_headers(r["request_headers"]),
            "body_file": files.get("request_body"),
        },
        "response": {
            "status": r["status"],
            "mime_type": r["mime_type"],
            "headers": sensitive.mask_headers(r["response_headers"]),
            "body_file": files.get("response_body"),
            "body_truncated": r["body_truncated"],
        },
        "resource_type": r["resource_type"],
        "error": r["error"],
    }
    _json(z, files["exchange"], exchange)
    return {
        "seq": seq,
        "time": _iso(r["started_at"]),
        "method": r["method"],
        "url": url,
        "status": r["status"],
        "resource_type": r["resource_type"],
        "mime_type": r["mime_type"],
        "endpoint": f"{r['method']} {openapi.template_path(r['path'])[0]}",
        "files": files,
    }


def _session(vault: Vault, domain: str, health: dict[str, Any]) -> dict[str, Any]:
    storage = vault.storage_for(domain)
    fingerprint = vault.fingerprint_for(domain) or {}
    return {
        "domain": domain,
        "status": health["status"],
        "user_agent": fingerprint.get("userAgent"),
        "fingerprint": fingerprint,
        "cookies": health["cookies"],
        "tokens": [
            {k: t[k] for k in ("kind", "jwt", "subject", "issuer", "expires", "state")}
            for t in health["tokens"]
        ],
        "storage_keys": {
            origin: {area: sorted(items) for area, items in areas.items()}
            for origin, areas in storage.items()
        },
        "how_to_load": f'sessiontap.httpx_client("{domain}")',
    }


def _json(z: zipfile.ZipFile, name: str, data: Any) -> None:
    z.writestr(name, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _pretty(body: str, ext: str) -> str:
    if ext != "json":
        return body
    try:
        return json.dumps(json.loads(body), indent=2, ensure_ascii=False) + "\n"
    except ValueError:
        return body


def _extension(content_type: str | None, body: str) -> str:
    ctype = (content_type or "").lower()
    if "json" in ctype or body.lstrip()[:1] in ("{", "["):
        return "json"
    if "html" in ctype:
        return "html"
    if "xml" in ctype:
        return "xml"
    if "x-www-form-urlencoded" in ctype:
        return "form.txt"
    return "txt"


def _header(headers: dict[str, str], name: str) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == name), None)


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None
