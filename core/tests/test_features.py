import json
import pytest
import asyncio
from typing import Any
from pathlib import Path
from .conftest import exchange
from sessiontap.client import Client
from sessiontap.mcp_server import build
from sessiontap.cli import Context, main
from fastapi.testclient import TestClient
from sessiontap.server import codegen, openapi

REQUEST: dict[str, Any] = {
    "url": "https://api.example.com/v1/items?page=2",
    "method": "POST",
    "domain": "example.com",
    "request_headers": {
        "Content-Type": "application/json",
        "Authorization": "Bearer SECRET-TOKEN-123",
        "Cookie": "sid=SECRET-COOKIE",
        "Content-Length": "13",
        ":authority": "api.example.com",
        "X-Client": "web",
    },
    "request_body": '{"name": "it\'s"}',
}


@pytest.mark.parametrize("lang", codegen.LANGUAGES)
def test_generated_code_has_no_secrets_by_default(lang: str) -> None:
    code = codegen.generate(REQUEST, lang)
    assert "SECRET" not in code
    assert "content-length" not in code.lower()
    assert ":authority" not in code
    assert "x-client" in code


@pytest.mark.parametrize("lang", codegen.LANGUAGES)
def test_generated_code_can_include_secrets(lang: str) -> None:
    code = codegen.generate(REQUEST, lang, include_secrets=True)
    assert "SECRET-TOKEN-123" in code


def test_curl_is_shell_safe() -> None:
    code = codegen.generate(
        {**REQUEST, "url": "https://e.com/$(touch pwned)", "request_body": "'; rm -rf / #"}, "curl"
    )
    assert "'https://e.com/$(touch pwned)'" in code
    assert "rm -rf" in code and "''\"'\"'" in code


def test_python_code_compiles() -> None:
    compile(codegen.generate(REQUEST, "python"), "<generated>", "exec")
    compile(codegen.generate(REQUEST, "python", include_secrets=True), "<generated>", "exec")


def test_credential_fields_in_body_are_masked() -> None:
    req = {**REQUEST, "request_body": '{"user": "a", "password": "PLAINTEXT-PASSWORD"}'}
    code = codegen.generate(req, "python")
    assert "PLAINTEXT-PASSWORD" not in code
    assert "masked" in code


def test_path_templating() -> None:
    assert openapi.template_path("/users/123/posts/9f8e7d6c-1234-4abc-8def-0123456789ab") == (
        "/users/{userId}/posts/{post_uuid}",
        ["userId", "post_uuid"],
    )
    assert openapi.template_path("/api/v2/search")[0] == "/api/v2/search"
    assert openapi.template_path("/files/a1b2c3d4e5f6a7b8")[0] == "/files/{file_key}"


def test_schema_inference_merges() -> None:
    a = openapi.schema_of({"id": 1, "name": "x", "tags": ["a"]})
    b = openapi.schema_of({"id": 2.5, "name": None})
    merged = openapi.merge(a, b)
    assert merged["properties"]["id"]["type"] == "number"
    assert merged["properties"]["name"]["type"] == ["null", "string"]
    assert merged["required"] == ["id", "name"]


def test_openapi_endpoint(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest",
        json={
            "events": [
                exchange("https://api.example.com/users/1?fields=a", response_body='{"id": 1}'),
                exchange("https://api.example.com/users/2", response_body='{"id": 2, "x": true}'),
                exchange("https://example.com/", resource_type="Document"),
            ]
        },
    )
    spec = api.get("/v1/openapi/example.com").json()
    assert spec["openapi"] == "3.1.0"
    assert list(spec["paths"]) == ["/users/{userId}"]
    op = spec["paths"]["/users/{userId}"]["get"]
    assert op["x-sessiontap-observed"] == 2
    assert {p["name"] for p in op["parameters"]} == {"userId", "fields"}
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["required"] == ["id"]


def test_code_endpoint(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post("/v1/ingest", json={"events": [exchange("https://example.com/api/x")]})
    rid = api.get("/v1/requests").json()[0]["id"]
    r = api.get(f"/v1/requests/{rid}/code", params={"lang": "python"})
    assert r.status_code == 200
    assert "sessiontap.httpx_client('example.com')" in r.text
    assert api.get(f"/v1/requests/{rid}/code", params={"lang": "cobol"}).status_code == 422


def test_playwright_cookies(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest",
        json={
            "events": [
                {
                    "type": "cookie",
                    "cookie": {
                        "name": "sid",
                        "value": "v",
                        "domain": ".example.com",
                        "same_site": "lax",
                        "http_only": True,
                        "expires": 2e9,
                    },
                }
            ]
        },
    )
    assert sdk.playwright_cookies("example.com") == [
        {
            "name": "sid",
            "value": "v",
            "domain": ".example.com",
            "path": "/",
            "secure": False,
            "httpOnly": True,
            "expires": 2e9,
            "sameSite": "Lax",
        }
    ]


def test_export_import_roundtrip(
    api: TestClient,
    sdk: Client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ctx = Context(client_factory=lambda: sdk)
    monkeypatch.setenv("SESSIONTAP_PASSPHRASE", "correct horse battery")
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest",
        json={
            "events": [
                {
                    "type": "cookie",
                    "cookie": {"name": "sid", "value": "EXPORTED", "domain": "example.com"},
                },
                exchange("https://example.com/a", request_headers={"x-api-key": "KEY-1234567890"}),
            ]
        },
    )
    out = tmp_path / "s.sessiontap"
    main(["export", "--domain", "example.com", "-o", str(out)], ctx)
    assert b"EXPORTED" not in out.read_bytes()
    assert json.loads(out.read_text())["format"] == "sessiontap-export"
    api.delete("/v1/domains/example.com")
    main(["import", str(out)], ctx)
    assert sdk.cookie_header("example.com") == "sid=EXPORTED"
    assert sdk.secret("example.com", "x-api-key") == "KEY-1234567890"
    monkeypatch.setenv("SESSIONTAP_PASSPHRASE", "wrong passphrase!!")
    with pytest.raises(SystemExit):
        main(["import", str(out)], ctx)
    assert "Wrong passphrase" in capsys.readouterr().err


def test_mcp_tools_never_return_secrets(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest",
        json={
            "events": [
                exchange(
                    "https://example.com/a",
                    request_headers={"authorization": "Bearer MCP-SECRET"},
                    response_body='{"access_token": "MCP-SECRET-2-abcdefgh"}',
                ),
            ]
        },
    )
    rid = api.get("/v1/requests").json()[0]["id"]
    server = build(sdk)

    async def call_all() -> str:
        outputs = []
        for name, args in [
            ("list_domains", {}),
            ("list_requests", {"domain": "example.com"}),
            ("get_request", {"request_id": rid}),
            ("generate_code", {"request_id": rid, "language": "curl"}),
            ("session_health", {"domain": "example.com"}),
            ("openapi_spec", {"domain": "example.com"}),
        ]:
            outputs.append(str(await server.call_tool(name, args)))
        return "\n".join(outputs)

    text = asyncio.run(call_all())
    assert "example.com" in text
    assert "MCP-SECRET" not in text
