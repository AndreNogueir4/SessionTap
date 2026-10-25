import pytest
from typing import Any
from .test_capture import ingest
from collections.abc import Iterator
from sessiontap.config import Config
from fastapi.testclient import TestClient
from sessiontap.server.vault import Vault
from .test_exports import PAGE, page, seed
from sessiontap.server.app import create_app
from .conftest import BASE, exchange, LOOPBACK_PEER


@pytest.fixture
def locked(vault: Vault, token: str) -> Iterator[TestClient]:
    vault.set_meta("blocklist", '["only.example"]')
    vault.set_meta("capture_html", "0")
    app: Any = create_app(vault, Config(capture_locked=True), lambda: token, key_backend="file")
    with TestClient(
        app, base_url=BASE, client=LOOPBACK_PEER, headers={"authorization": f"Bearer {token}"}
    ) as c:
        yield c


def test_defaults_are_listed(api: TestClient) -> None:
    view = api.get("/v1/blocklist").json()
    domains = {d["domain"]: d["default"] for d in view["domains"]}
    assert domains["example.block.com"] is True
    assert view["customized"] is False
    assert view["locked"] is False


def test_adding_a_domain_blocks_it_and_stops_capture(api: TestClient) -> None:
    api.put("/v1/domains/shop.example.com", json={"capture": True})
    api.put("/v1/domains/example.org", json={"capture": True})
    view = api.post("/v1/blocklist", json={"domain": "WWW.Example.com"}).json()
    assert {"domain": "example.com", "default": False} in view["domains"]
    assert view["customized"] is True
    assert api.get("/v1/capture-state").json()["domains"] == ["example.org"]
    assert "example.com" in api.get("/v1/capture-state").json()["blocklist"]
    assert api.put("/v1/domains/example.com", json={"capture": True}).status_code == 403
    assert ingest(api, exchange("https://shop.example.com/api"))["dropped"] == 1


def test_removing_a_default_allows_capture(api: TestClient) -> None:
    assert api.put("/v1/domains/example.block.com", json={"capture": True}).status_code == 403
    view = api.delete("/v1/blocklist/example.block.com").json()
    assert "example.block.com" in view["removed_defaults"]
    assert api.put("/v1/domains/example.block.com", json={"capture": True}).status_code == 200
    assert ingest(api, exchange("https://api.example.block.com/api"))["accepted"] == 1


def test_reset_restores_defaults(api: TestClient) -> None:
    api.delete("/v1/blocklist/example.block.com")
    api.post("/v1/blocklist", json={"domain": "example.com"})
    view = api.post("/v1/blocklist/reset").json()
    names = [d["domain"] for d in view["domains"]]
    assert "example.block.com" in names
    assert "example.com" not in names
    assert view["customized"] is False


@pytest.mark.parametrize("bad", ["*.example.com", "com", "exa mple.com", ""])
def test_invalid_entries_rejected(api: TestClient, bad: str) -> None:
    assert api.post("/v1/blocklist", json={"domain": bad}).status_code == 422


def test_capture_settings_apply_at_runtime(api: TestClient) -> None:
    settings = api.patch("/v1/settings", json={"capture_html": False, "max_body_kb": 1}).json()
    assert settings["capture_html"] is False
    assert settings["max_body_kb"] == 1
    state = api.get("/v1/capture-state").json()
    assert state["capture_html"] is False
    assert state["max_body_bytes"] == 1024
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        page("https://example.com/"),
        exchange("https://example.com/api", response_body="x" * 5000),
    )
    rows = {r["path"]: r["id"] for r in api.get("/v1/requests").json()}
    assert api.get(f"/v1/requests/{rows['/']}").json()["response_body"] is None
    assert len(api.get(f"/v1/requests/{rows['/api']}").json()["response_body"]) == 1024
    assert api.patch("/v1/settings", json={"max_body_kb": 5000}).status_code == 422


def test_html_back_on(api: TestClient) -> None:
    api.patch("/v1/settings", json={"capture_html": False})
    api.patch("/v1/settings", json={"capture_html": True})
    seed(api)
    doc = next(r for r in api.get("/v1/requests").json() if r["resource_type"] == "Document")
    assert api.get(f"/v1/requests/{doc['id']}").json()["response_body"] == PAGE


def test_locked_policy_ignores_overrides_and_refuses_edits(locked: TestClient) -> None:
    view = locked.get("/v1/blocklist").json()
    assert view["locked"] is True
    assert "example.block.com" in [d["domain"] for d in view["domains"]]
    assert "only.example" not in [d["domain"] for d in view["domains"]]
    assert locked.get("/v1/settings").json()["capture_html"] is True
    for r in (
        locked.post("/v1/blocklist", json={"domain": "example.com"}),
        locked.delete("/v1/blocklist/example.block.com"),
        locked.post("/v1/blocklist/reset"),
        locked.patch("/v1/settings", json={"capture_html": False}),
    ):
        assert r.status_code == 403
        assert "locked" in r.json()["detail"]
    assert locked.patch("/v1/settings", json={"retention_days": 3}).status_code == 200
