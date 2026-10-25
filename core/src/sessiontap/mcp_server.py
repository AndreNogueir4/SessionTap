from typing import Any
from sessiontap.client import Client
from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = """SessionTap stores browser traffic the user chose to capture, per domain.
Use list_domains first, then list_requests / get_request to understand an API, and
generate_code to produce a script. Secrets are never shown to you; generated code loads
them at run time through the SessionTap SDK. Respect the site's terms of service."""


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
        description="One request with headers (credentials masked) and bodies (truncated)."
    )
    def get_request(request_id: int, max_body_chars: int = 20000) -> dict[str, Any]:
        r = dict(api.api("GET", f"/v1/requests/{request_id}"))
        for key in ("request_body", "response_body"):
            if r.get(key) and len(r[key]) > max_body_chars:
                r[key] = r[key][:max_body_chars] + "\n…[truncated]"
        return r

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
