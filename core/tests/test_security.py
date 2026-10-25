import pytest
import time as time_module
from typing import Any
from sessiontap.server import security
from fastapi.testclient import TestClient
from .conftest import BASE, exchange, LOOPBACK_PEER


def test_api_requires_token(anon: TestClient) -> None:
    r = anon.get("/v1/status")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_wrong_token_rejected(anon: TestClient) -> None:
    assert anon.get("/v1/status", headers={"authorization": "Bearer nope"}).status_code == 401
    assert anon.get("/v1/status", headers={"authorization": "Basic abc"}).status_code == 401


def test_valid_token_accepted(api: TestClient) -> None:
    assert api.get("/v1/status").status_code == 200


def test_session_data_needs_token(anon: TestClient) -> None:
    for path in ("/v1/sessions/example.com", "/v1/tokens", "/v1/requests", "/v1/events"):
        assert anon.get(path).status_code == 401, path


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8711", "127.0.0.1:9999", ""])
def test_dns_rebinding_host_rejected(api: TestClient, host: str) -> None:
    r = api.get("/v1/status", headers={"host": host})
    assert r.status_code == 403
    assert "Host" in r.json()["detail"]


@pytest.mark.parametrize("host", ["127.0.0.1:8711", "localhost:8711", "[::1]:8711"])
def test_loopback_hosts_allowed(api: TestClient, host: str) -> None:
    assert api.get("/v1/status", headers={"host": host}).status_code == 200


def test_foreign_origin_rejected_even_with_token(api: TestClient) -> None:
    r = api.get("/v1/sessions/example.com", headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_null_origin_rejected(api: TestClient) -> None:
    assert api.get("/v1/status", headers={"origin": "null"}).status_code == 403


def test_same_origin_allowed(api: TestClient) -> None:
    assert api.get("/v1/status", headers={"origin": BASE}).status_code == 200


def test_cross_site_fetch_metadata_rejected(api: TestClient) -> None:
    assert api.get("/v1/status", headers={"sec-fetch-site": "cross-site"}).status_code == 403


def test_non_loopback_peer_rejected(app: Any, token: str) -> None:
    with TestClient(app, base_url=BASE, client=("192.168.1.20", 4000)) as c:
        r = c.get("/v1/status", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_simple_cross_site_post_rejected(api: TestClient) -> None:
    r = api.post("/v1/ingest", content=b'{"events": []}', headers={"content-type": "text/plain"})
    assert r.status_code == 415


def test_form_post_rejected(api: TestClient) -> None:
    r = api.put(
        "/v1/domains/example.com",
        content=b"capture=true",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 415


def test_body_size_limit(api: TestClient) -> None:
    big = b'{"x": "' + b"a" * (security.MAX_BODY + 10) + b'"}'
    r = api.put(
        "/v1/domains/example.com", content=big, headers={"content-type": "application/json"}
    )
    assert r.status_code == 413


def test_failed_auth_is_throttled(anon: TestClient, token: str) -> None:
    for _ in range(security.FAILED_AUTH_LIMIT):
        anon.get("/v1/status", headers={"authorization": "Bearer guess"})
    r = anon.get("/v1/status", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 429


def test_security_headers(api: TestClient, anon: TestClient) -> None:
    for r in (api.get("/v1/status"), anon.get("/"), anon.get("/v1/status")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert "access-control-allow-origin" not in r.headers
    assert api.get("/v1/status").headers["cache-control"] == "no-store"


def test_no_cors_preflight_support(anon: TestClient) -> None:
    r = anon.options(
        "/v1/status",
        headers={"origin": "https://evil.example", "access-control-request-method": "GET"},
    )
    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers


def test_no_public_api_docs(anon: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anon.get(path).status_code == 404, path


def test_dashboard_is_public_but_has_no_data(anon: TestClient) -> None:
    r = anon.get("/")
    assert r.status_code == 200
    assert "cookie" not in r.text.lower()


def test_login_code_is_single_use(api: TestClient, anon: TestClient, token: str) -> None:
    code = api.post("/v1/auth/login-code").json()["code"]
    first = anon.post("/v1/auth/exchange", json={"code": code})
    assert first.status_code == 200
    assert first.json()["token"] == token
    assert anon.post("/v1/auth/exchange", json={"code": code}).status_code == 401


def test_login_code_requires_token(anon: TestClient) -> None:
    assert anon.post("/v1/auth/login-code").status_code == 401


def test_login_code_expires(api: TestClient, anon: TestClient, monkeypatch: Any) -> None:
    code = api.post("/v1/auth/login-code").json()["code"]
    real = time_module.monotonic
    monkeypatch.setattr(time_module, "monotonic", lambda: real() + 3600)
    assert anon.post("/v1/auth/exchange", json={"code": code}).status_code == 401


def test_secrets_masked_unless_revealed(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest",
        json={
            "events": [
                exchange(
                    "https://example.com/api/login?token=supersecretvalue123",
                    method="POST",
                    request_headers={
                        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
                        "content-type": "application/json",
                    },
                    request_body='{"user": "ana", "password": "hunter2hunter2"}',
                    response_body='{"access_token": "tok_1234567890abcdef1234"}',
                )
            ]
        },
    )
    rid = api.get("/v1/requests").json()[0]["id"]
    masked = api.get(f"/v1/requests/{rid}").text
    for secret in ("abcdefghijklmnopqrstuvwxyz", "hunter2", "tok_1234567890", "supersecretvalue"):
        assert secret not in masked, secret
    revealed = api.get(f"/v1/requests/{rid}", params={"reveal": "true"}).text
    assert "hunter2hunter2" in revealed
    tokens = api.get("/v1/tokens").text
    assert "abcdefghijklmnopqrstuvwxyz" not in tokens


def test_loopback_peer_fixture_is_loopback() -> None:
    assert LOOPBACK_PEER[0] in security.LOOPBACK_PEERS
