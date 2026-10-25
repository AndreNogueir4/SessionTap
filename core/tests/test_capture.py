import json
import time
import base64
from .conftest import exchange
from sessiontap.client import Client
from sessiontap.config import Config
from fastapi.testclient import TestClient
from sessiontap.server.policy import Policy
from sessiontap.server.capture import IngestBatch, Ingestor


def _jwt(exp: float) -> str:
    def enc(obj: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{enc({'alg': 'HS256'})}.{enc({'sub': 'user-1', 'exp': exp})}.signaturepart"


def ingest(api: TestClient, *events: dict[str, object]) -> dict[str, int]:
    r = api.post("/v1/ingest", json={"events": list(events)})
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_nothing_is_captured_until_enabled(api: TestClient) -> None:
    assert ingest(api, exchange("https://example.com/api/a")) == {"accepted": 0, "dropped": 1}
    api.put("/v1/domains/example.com", json={"capture": True})
    assert ingest(api, exchange("https://example.com/api/a")) == {"accepted": 1, "dropped": 0}


def test_subdomains_are_covered_but_lookalikes_are_not(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    result = ingest(
        api,
        exchange("https://api.example.com/v1/x"),
        exchange("https://notexample.com/x"),
        exchange("https://example.com.evil.net/x"),
    )
    assert result == {"accepted": 1, "dropped": 2}


def test_blocklisted_domains_cannot_be_enabled(api: TestClient) -> None:
    r = api.put("/v1/domains/example.block.com", json={"capture": True})
    assert r.status_code == 403
    r = api.put("/v1/domains/api.example.block.com", json={"capture": True})
    assert r.status_code == 403


def test_blocklist_wins_over_enabled_parent(api: TestClient) -> None:
    api.put("/v1/domains/block.com", json={"capture": True})
    assert ingest(api, exchange("https://example.block.com/mail/x"))["dropped"] == 1
    assert ingest(api, exchange("https://www.block.com/search"))["accepted"] == 1


def test_invalid_domains_rejected(api: TestClient) -> None:
    for bad in ("*.example.com", "exa mple.com", "localhost:80", "com"):
        assert api.put(f"/v1/domains/{bad}", json={"capture": True}).status_code in (404, 422), bad


def test_disabling_stops_capture(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.put("/v1/domains/example.com", json={"capture": False})
    assert ingest(api, exchange("https://example.com/a"))["dropped"] == 1


def test_tokens_and_cookies_extracted(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    exp = time.time() + 3 * 86400
    ingest(
        api,
        exchange(
            "https://api.example.com/me",
            request_headers={"Authorization": f"Bearer {_jwt(exp)}", "X-CSRF-Token": "abc"},
        ),
        {
            "type": "cookies",
            "domain": "example.com",
            "cookies": [
                {"name": "sid", "value": "s3cr3t", "domain": ".example.com", "http_only": True},
                {"name": "other", "value": "x", "domain": "unrelated.org"},
            ],
        },
    )
    assert sdk.secret("example.com", "x-csrf-token") == "abc"
    assert sdk.secret("example.com", "authorization").startswith("Bearer ")
    session = sdk.session("example.com")
    assert [c.name for c in session.cookies] == ["sid"]
    assert session.cookie_header() == "sid=s3cr3t"
    health = sdk.health("example.com")
    assert health["status"] == "ok"
    jwt_tokens = [t for t in health["tokens"] if t["jwt"]]
    assert jwt_tokens[0]["subject"] == "user-1"


def test_parent_domain_cookie_belongs_to_enabled_subdomain(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/app.example.com", json={"capture": True})
    ingest(
        api,
        {
            "type": "cookie",
            "cookie": {"name": "sid", "value": "v", "domain": ".example.com"},
        },
    )
    assert [c.name for c in sdk.session("app.example.com").cookies] == ["sid"]


def test_expired_session_health(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        {
            "type": "cookie",
            "cookie": {
                "name": "sid",
                "value": "v",
                "domain": "example.com",
                "expires": time.time() - 10,
            },
        },
    )
    assert sdk.health("example.com")["status"] == "expired"


def test_large_bodies_truncated(api: TestClient, config: object) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(api, exchange("https://example.com/big", response_body="x" * (600 * 1024)))
    rid = api.get("/v1/requests").json()[0]["id"]
    r = api.get(f"/v1/requests/{rid}").json()
    assert r["body_truncated"] is True
    assert len(r["response_body"]) == 512 * 1024


def test_malformed_events_dropped_individually(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    bad = [
        {"type": "exchange", "url": "https://example.com", "method": "get; rm -rf"},
        {"type": "unknown"},
        {"type": "exchange", "url": "x" * 9000, "method": "GET"},
        "not an object",
    ]
    r = api.post("/v1/ingest", json={"events": [*bad, exchange("https://example.com/ok")]})
    assert r.status_code == 200
    assert r.json() == {"accepted": 1, "dropped": 4}


def test_batch_size_limit(api: TestClient) -> None:
    events = [exchange("https://example.com/x")] * 501
    assert api.post("/v1/ingest", json={"events": events}).status_code == 422


def test_storage_and_fingerprint(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        {"type": "storage", "origin": "https://example.com/page", "local": {"k": "v"}},
        {"type": "fingerprint", "origin": "https://example.com", "data": {"userAgent": "UA/1"}},
    )
    s = sdk.session("example.com")
    assert s.local_storage() == {"k": "v"}
    assert s.user_agent == "UA/1"
    assert sdk.httpx_client("example.com").headers["user-agent"] == "UA/1"


def test_purge_domain(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(api, exchange("https://example.com/a"))
    assert api.delete("/v1/domains/example.com").status_code == 200
    assert api.get("/v1/requests").json() == []
    assert api.get("/v1/sessions/example.com").status_code == 404


def test_live_feed_has_no_secrets(api: TestClient) -> None:
    vault = api.app.state.vault  # type: ignore[attr-defined]
    vault.set_capture("example.com", True)
    ingestor = Ingestor(vault, Policy(vault, Config(blocklist=(), max_body_kb=1)))
    _, feed = ingestor.ingest(
        IngestBatch.model_validate(
            {
                "events": [
                    exchange(
                        "https://example.com/a?token=zzzsecretzzz",
                        request_headers={"authorization": "Bearer zzzsecretzzz"},
                    )
                ]
            }
        )
    )
    assert "zzzsecretzzz" not in json.dumps(feed)


def test_health_shows_latest_token_per_kind(api: TestClient, sdk: Client) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    for i in range(3):
        ingest(
            api,
            exchange(
                f"https://example.com/{i}",
                request_headers={"authorization": f"Bearer {_jwt(time.time() + 86400 * (i + 2))}"},
            ),
        )
    tokens = sdk.health("example.com")["tokens"]
    assert [t["kind"] for t in tokens] == ["authorization"]


def test_domain_summary_for_the_popup(api: TestClient) -> None:
    assert api.get("/v1/domains/example.com/summary").json() == {
        "domain": "example.com",
        "known": False,
    }
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        exchange(
            "https://api.example.com/me",
            request_headers={"authorization": f"Bearer {_jwt(time.time() + 3 * 86400)}"},
        ),
        exchange("https://example.com/feed", status=500),
        {"type": "cookie", "cookie": {"name": "sid", "value": "s3cr3t", "domain": ".example.com"}},
        {"type": "storage", "origin": "https://example.com", "local": {"a": "1", "b": "2"}},
    )
    summary = api.get("/v1/domains/app.example.com/summary").json()
    assert summary["domain"] == "example.com"
    assert summary["capture"] is True
    assert summary["counts"] == {"requests": 2, "cookies": 1, "tokens": 1, "storage": 2}
    assert summary["health"]["status"] == "ok"
    assert [r["path"] for r in summary["recent"]] == ["/feed", "/me"]
    assert [(c["name"], c["domain"]) for c in summary["cookies"]] == [("sid", ".example.com")]
    assert [(t["kind"], t["jwt"]) for t in summary["tokens"]] == [("authorization", True)]
    assert "s3cr3t" not in str(summary)
    assert "Bearer" not in str(summary)
