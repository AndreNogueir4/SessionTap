from typing import Any, Literal
from sessiontap.client import Client
from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = """SessionTap stores browser traffic the user chose to capture, per domain.
Use list_domains first, then list_requests / search_bodies to find the right requests.
Prefer the compact views over raw bodies: json_shape for JSON, query_html or read_body with
text=true for HTML pages, diff_requests to see which values change between two calls. Use
get_request / read_body for the full content, and generate_code to produce a script.
Secrets are never shown to you; generated code loads them at run time through the
SessionTap SDK. Respect the site's terms of service."""


def build(client: Client | None = None) -> MCPServer:
    api = client or Client()
    server = MCPServer("sessiontap", instructions=INSTRUCTIONS)

    @server.tool(
        description="Domains with captured data, whether capture is on, and how much is stored."
    )
    def list_domains() -> list[dict[str, Any]]:
        return list(api.api("GET", "/v1/domains"))

    @server.tool(
        description="Whether the captured session for a domain still works: cookie and JWT expiry."
    )
    def session_health(domain: str) -> dict[str, Any]:
        return dict(api.api("GET", f"/v1/sessions/{domain}/health"))

    @server.tool(
        description="Captured requests for a domain, newest first. `query` filters by path/host."
    )
    def list_requests(domain: str, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"domain": domain, "limit": max(1, min(limit, 200))}
        if query:
            params["q"] = query
        return list(api.api("GET", "/v1/requests", **params))

    @server.tool(
        description=(
            "One request with headers (credentials masked) and bodies (truncated). "
            "`*_body_size` is the full length; use read_body for the rest."
        )
    )
    def get_request(request_id: int, max_body_chars: int = 20000) -> dict[str, Any]:
        limit = max(1, max_body_chars)
        r = dict(api.api("GET", f"/v1/requests/{request_id}", body_limit=limit))
        for key in ("request_body", "response_body"):
            if r.get(key) and r.get(f"{key}_size", 0) > len(r[key]):
                r[key] += f"\n…[truncated at {len(r[key])} of {r[f'{key}_size']} chars]"
        return r

    @server.tool(
        description=(
            "Read a request or response body in chunks. With text=true an HTML page is "
            "reduced to its visible text (no tags, scripts or styles), which is far smaller. "
            "Keep calling with offset=next_offset until next_offset is null."
        )
    )
    def read_body(
        request_id: int,
        part: Literal["request", "response"] = "response",
        text: bool = False,
        offset: int = 0,
        length: int = 20000,
    ) -> dict[str, Any]:
        return dict(
            api.api(
                "GET",
                f"/v1/requests/{request_id}/chunk",
                part=part,
                text=str(text).lower(),
                offset=max(0, offset),
                length=max(1, min(length, 200_000)),
            )
        )

    @server.tool(
        description=(
            "Find which captured requests contain some text (case-insensitive) in the URL, "
            "headers or bodies, newest first, with snippets around each hit. Secrets are masked "
            "before searching, so they can't be found. `more` means older requests were not "
            "scanned; raise `scan` to look further back."
        )
    )
    def search_bodies(domain: str, query: str, limit: int = 20, scan: int = 500) -> dict[str, Any]:
        return dict(
            api.api(
                "GET",
                "/v1/search",
                domain=domain,
                q=query,
                limit=max(1, min(limit, 100)),
                scan=max(1, min(scan, 2000)),
            )
        )

    @server.tool(
        description=(
            "The structure of a JSON body instead of the body itself: keys, types, one short "
            "example per field and array lengths (items merged; `optional` marks keys missing "
            "in some items). Use it before reading a large JSON response."
        )
    )
    def json_shape(
        request_id: int, part: Literal["request", "response"] = "response"
    ) -> dict[str, Any]:
        return dict(api.api("GET", f"/v1/requests/{request_id}/shape", part=part))

    @server.tool(
        description=(
            "Run a CSS selector (e.g. 'table.orders tr', 'a[href*=invoice]') on a captured HTML "
            "page and get each match's text and attributes, plus its HTML with "
            "include_html=true. `total` counts all matches even when `limit` cuts the list."
        )
    )
    def query_html(
        request_id: int, selector: str, limit: int = 20, include_html: bool = False
    ) -> dict[str, Any]:
        return dict(
            api.api(
                "GET",
                f"/v1/requests/{request_id}/html",
                selector=selector,
                limit=max(1, min(limit, 500)),
                html=str(include_html).lower(),
            )
        )

    @server.tool(
        description=(
            "Compare two captured requests: method/host/path/status, query parameters, "
            "headers and JSON or form bodies field by field. Use it to find which values change "
            "between calls (pagination, filters, nonces, signatures). Secret values show as "
            "masked, but you still see whether they changed."
        )
    )
    def diff_requests(request_a: int, request_b: int) -> dict[str, Any]:
        return dict(api.api("GET", f"/v1/requests/{request_a}/diff/{request_b}"))

    @server.tool(
        description=(
            "Runnable code for a captured request (curl, python or javascript). The code "
            "fetches credentials from SessionTap when it runs; it contains no secrets."
        )
    )
    def generate_code(request_id: int, language: str = "python") -> str:
        return str(api.api("GET", f"/v1/requests/{request_id}/code", lang=language))

    @server.tool(
        description="OpenAPI 3.1 description inferred from the domain's captured API traffic."
    )
    def openapi_spec(domain: str) -> dict[str, Any]:
        return dict(api.api("GET", f"/v1/openapi/{domain}"))

    return server


def run() -> None:
    build().run("stdio")
