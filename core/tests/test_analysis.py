import json
import asyncio
from typing import Any
from .conftest import exchange
from .test_capture import ingest
from sessiontap.client import Client
from sessiontap.mcp_server import build
from fastapi.testclient import TestClient
from sessiontap.server.analysis import merge_shape, shape

ORDERS = {
    "items": [
        {"orderId": 1, "total": 19.9, "coupon": None},
        {"orderId": 2, "total": 5, "note": "gift"},
    ]
    * 250,
    "next": "/orders?page=3",
}
PAGE = """<html><head><meta name="csrf-token" content="CSRF-SECRET-VALUE"></head><body>
<table class="orders"><tr data-id="1"><td>Order 1</td><td>R$ 19,90</td></tr>
<tr data-id="2"><td>Order 2</td><td>R$ 5,00</td></tr></table>
<form><input type="hidden" name="authenticity_token" value="FORM-SECRET-VALUE">
<input name="q" value="shoes"></form></body></html>"""


def ids(api: TestClient) -> dict[str, int]:
    return {r["path"]: r["id"] for r in api.get("/v1/requests").json()}


def seed(api: TestClient) -> dict[str, int]:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        exchange(
            "https://api.example.com/orders?page=2&signature=SIG-ONE",
            request_headers={"authorization": "Bearer TOKEN-ONE", "x-page": "2"},
            response_body=json.dumps(ORDERS),
        ),
        exchange(
            "https://api.example.com/orders/v2?page=3&signature=SIG-TWO",
            method="POST",
            request_headers={
                "authorization": "Bearer TOKEN-TWO",
                "content-type": "application/json",
            },
            request_body=json.dumps({"filter": "open", "password": "hunter2", "page": 3}),
            response_body=json.dumps({"items": [], "refresh_token": "REFRESH-SECRET"}),
            status=201,
        ),
        exchange(
            "https://www.example.com/account",
            resource_type="Document",
            mime_type="text/html",
            response_headers={"content-type": "text/html"},
            response_body=PAGE,
        ),
    )
    return ids(api)


def test_search_finds_text_in_bodies_with_snippets(api: TestClient) -> None:
    seed(api)
    found = api.get("/v1/search", params={"domain": "example.com", "q": "r$ 19,90"}).json()
    assert [r["path"] for r in found["results"]] == ["/account"]
    hit = found["results"][0]["hits"][0]
    assert hit["field"] == "response_body"
    assert hit["count"] == 1
    assert "Order 1" in hit["snippets"][0]
    assert found["more"] is False
    order = api.get("/v1/search", params={"domain": "example.com", "q": "orderId"}).json()
    assert [r["path"] for r in order["results"]] == ["/orders"]
    assert order["results"][0]["hits"][0]["count"] == 500
    assert len(order["results"][0]["hits"][0]["snippets"]) == 3


def test_search_cannot_find_secrets(api: TestClient) -> None:
    seed(api)
    for secret in ("TOKEN-ONE", "hunter2", "REFRESH-SECRET", "SIG-ONE"):
        found = api.get("/v1/search", params={"domain": "example.com", "q": secret}).json()
        assert found["results"] == [], secret


def test_search_stops_at_limit_and_scan(api: TestClient) -> None:
    seed(api)
    limited = api.get(
        "/v1/search", params={"domain": "example.com", "q": "example", "limit": 1}
    ).json()
    assert len(limited["results"]) == 1
    assert limited["more"] is True
    scanned = api.get(
        "/v1/search", params={"domain": "example.com", "q": "orderId", "scan": 1}
    ).json()
    assert scanned["scanned"] == 1
    assert scanned["more"] is True


def test_json_shape_summarises_large_lists(api: TestClient) -> None:
    rid = seed(api)["/orders"]
    body = api.get(f"/v1/requests/{rid}/shape").json()["shape"]
    items = body["properties"]["items"]
    assert items["length"] == 500
    props = items["items"]["properties"]
    assert props["orderId"] == {"type": "integer", "example": 1}
    assert props["total"]["type"] == "integer|number"
    assert props["coupon"]["optional"] is True
    assert props["note"] == {"type": "string", "example": "gift", "optional": True}
    assert len(json.dumps(body)) < 1000 < len(json.dumps(ORDERS))
    assert api.get(f"/v1/requests/{seed(api)['/account']}/shape").status_code == 422


def test_json_shape_masks_secrets(api: TestClient) -> None:
    rid = seed(api)["/orders/v2"]
    for part in ("request", "response"):
        text = json.dumps(api.get(f"/v1/requests/{rid}/shape", params={"part": part}).json())
        assert "hunter2" not in text
        assert "REFRESH-SECRET" not in text


def test_shape_merges_nested_arrays() -> None:
    merged = merge_shape(shape({"tags": ["a"]}), shape({"tags": ["b", "c", "d"], "x": 1}))
    assert merged["properties"]["tags"]["length"] == 3
    assert merged["properties"]["x"]["optional"] is True
    assert "optional" not in merged["properties"]["tags"]


def test_query_html_returns_text_and_attributes(api: TestClient) -> None:
    rid = seed(api)["/account"]
    rows = api.get(
        f"/v1/requests/{rid}/html", params={"selector": "table.orders tr", "limit": 1}
    ).json()
    assert rows["total"] == 2
    assert rows["matches"] == [{"tag": "tr", "text": "Order 1 R$ 19,90", "attrs": {"data-id": "1"}}]
    full = api.get(
        f"/v1/requests/{rid}/html", params={"selector": "meta, input", "html": True}
    ).json()
    text = json.dumps(full)
    assert "CSRF-SECRET-VALUE" not in text
    assert "FORM-SECRET-VALUE" not in text
    assert full["matches"][2]["attrs"]["value"] == "shoes"
    assert full["matches"][0]["html"].startswith("<meta")


def test_query_html_rejects_bad_input(api: TestClient) -> None:
    rids = seed(api)
    bad = api.get(f"/v1/requests/{rids['/account']}/html", params={"selector": "tr[["})
    assert bad.status_code == 422
    assert "invalid CSS selector" in bad.json()["detail"]
    not_html = api.get(f"/v1/requests/{rids['/orders']}/html", params={"selector": "tr"})
    assert not_html.status_code == 422


def test_diff_shows_what_changes_without_secrets(api: TestClient) -> None:
    rids = seed(api)
    d = api.get(f"/v1/requests/{rids['/orders']}/diff/{rids['/orders/v2']}").json()
    text = json.dumps(d)
    for secret in ("TOKEN-ONE", "TOKEN-TWO", "SIG-ONE", "SIG-TWO", "hunter2", "REFRESH-SECRET"):
        assert secret not in text, secret
    assert d["same_endpoint"] is False
    assert d["request"]["method"] == {"a": "GET", "b": "POST"}
    assert d["request"]["status"] == {"a": 200, "b": 201}
    query = {c["key"]: c for c in d["query"]["changes"]}
    assert query["page"] == {"key": "page", "a": "2", "b": "3"}
    assert query["signature"]["a"].startswith("••••")
    headers = {c["key"]: c for c in d["request_headers"]["changes"]}
    assert headers["authorization"]["a"].startswith("••••")
    assert headers["x-page"]["only_in"] == "a"
    body = {c["key"]: c for c in d["request_body"]["changes"]}
    assert body["password"] == {"key": "password", "b": "•••• (7 chars)", "only_in": "b"}
    assert d["response_body"]["more"] > 0
    assert len(d["response_body"]["changes"]) == 100


def test_diff_of_identical_requests_is_empty(api: TestClient) -> None:
    rid = seed(api)["/account"]
    d = api.get(f"/v1/requests/{rid}/diff/{rid}").json()
    assert d["same_endpoint"] is True
    assert d["request"] == {}
    assert d["query"]["changes"] == []
    assert d["response_body"] == {"equal": True, "a_size": len(PAGE), "b_size": len(PAGE)}


def test_mcp_analysis_tools(api: TestClient, sdk: Client) -> None:
    rids = seed(api)
    server = build(sdk)

    async def call(name: str, args: dict[str, Any]) -> Any:
        result: Any = await server.call_tool(name, args)
        return json.loads(result.content[0].text)

    found = asyncio.run(call("search_bodies", {"domain": "example.com", "query": "orderId"}))
    shaped = asyncio.run(call("json_shape", {"request_id": rids["/orders"]}))
    rows = asyncio.run(call("query_html", {"request_id": rids["/account"], "selector": "td"}))
    diff = asyncio.run(
        call("diff_requests", {"request_a": rids["/orders"], "request_b": rids["/orders/v2"]})
    )
    assert found["results"][0]["id"] == rids["/orders"]
    assert shaped["shape"]["properties"]["items"]["length"] == 500
    assert rows["total"] == 4
    assert diff["request"]["method"] == {"a": "GET", "b": "POST"}
    assert "TOKEN-ONE" not in json.dumps([found, shaped, rows, diff])
