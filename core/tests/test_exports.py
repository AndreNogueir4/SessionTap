import io
import json
import pytest
import zipfile
from typing import Any
from .conftest import exchange
from .test_capture import ingest
from sessiontap import nativehost
from fastapi.testclient import TestClient
from sessiontap.server.htmltext import html_to_text
from sessiontap.server.capture import MAX_HTML_BYTES

BEARER = "Bearer s3cr3t-bearer-value"
PAGE = "<!doctype html><html><body>" + "<p>row</p>" * 200_000 + "</body></html>"


def page(url: str, html: str = PAGE, **extra: Any) -> dict[str, Any]:
    return exchange(
        url,
        resource_type="Document",
        mime_type="text/html",
        response_headers={"content-type": "text/html; charset=utf-8"},
        response_body=html,
        **extra,
    )


def seed(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        page("https://www.example.com/orders"),
        exchange(
            "https://api.example.com/users/42/orders?page=2&access_token=t0k3n",
            request_headers={"authorization": BEARER, "content-type": "application/json"},
            method="POST",
            request_body=json.dumps({"filter": "open", "password": "hunter2"}),
            response_body=json.dumps(
                {"items": [{"id": i, "total": 19.9} for i in range(10)], "refresh_token": "r3fr3sh"}
            ),
        ),
        {"type": "cookie", "cookie": {"name": "sid", "value": "c00kie", "domain": ".example.com"}},
    )


def test_html_pages_are_stored_complete(api: TestClient) -> None:
    seed(api)
    assert len(PAGE) > 512 * 1024
    rows = api.get("/v1/requests", params={"domain": "example.com"}).json()
    doc = next(r for r in rows if r["resource_type"] == "Document")
    full = api.get(f"/v1/requests/{doc['id']}").json()
    assert full["response_body"] == PAGE
    assert full["body_truncated"] is False


def test_api_bodies_still_respect_max_body(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(api, exchange("https://example.com/api/big", response_body="x" * (600 * 1024)))
    r = api.get("/v1/requests", params={"domain": "example.com"}).json()[0]
    assert api.get(f"/v1/requests/{r['id']}").json()["body_truncated"] is True


def test_html_has_a_safety_ceiling(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sessiontap.server.capture.MAX_HTML_BYTES", 1000)
    seed(api)
    doc = next(
        r
        for r in api.get("/v1/requests", params={"domain": "example.com"}).json()
        if r["resource_type"] == "Document"
    )
    full = api.get(f"/v1/requests/{doc['id']}").json()
    assert len(full["response_body"]) == 1000
    assert full["body_truncated"] is True
    assert MAX_HTML_BYTES == 100 * 1024 * 1024


def test_body_limit_and_download(api: TestClient) -> None:
    seed(api)
    doc = next(
        r
        for r in api.get("/v1/requests", params={"domain": "example.com"}).json()
        if r["resource_type"] == "Document"
    )
    short = api.get(f"/v1/requests/{doc['id']}", params={"body_limit": 100}).json()
    assert len(short["response_body"]) == 100
    assert short["response_body_size"] == len(PAGE)
    raw = api.get(f"/v1/requests/{doc['id']}/body")
    assert raw.text == PAGE
    assert raw.headers["content-type"].startswith("text/plain")
    assert "attachment" in raw.headers["content-disposition"]


def test_body_chunks_page_through_the_whole_body(api: TestClient) -> None:
    seed(api)
    doc = next(
        r
        for r in api.get("/v1/requests", params={"domain": "example.com"}).json()
        if r["resource_type"] == "Document"
    )
    parts: list[str] = []
    offset: int | None = 0
    while offset is not None:
        chunk = api.get(
            f"/v1/requests/{doc['id']}/chunk", params={"offset": offset, "length": 200_000}
        ).json()
        assert chunk["total"] == len(PAGE)
        parts.append(chunk["content"])
        offset = chunk["next_offset"]
    assert "".join(parts) == PAGE
    assert len(parts) == -(-len(PAGE) // 200_000)
    too_big = api.get(f"/v1/requests/{doc['id']}/chunk", params={"length": 200_001})
    assert too_big.status_code == 422


def test_body_chunks_turn_html_into_text(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    html = (
        "<html><head><title>Orders</title><style>p{color:red}</style>"
        "<script>var token='SCRIPT-ONLY'</script></head><body><h1>My   orders</h1>"
        "<p>Total: R$&nbsp;19,90</p><noscript>enable js</noscript><ul><li>one</li>"
        "<li>two</li></ul></body></html>"
    )
    ingest(api, page("https://www.example.com/orders", html))
    rid = api.get("/v1/requests").json()[0]["id"]
    chunk = api.get(f"/v1/requests/{rid}/chunk", params={"text": True}).json()
    assert chunk["text"] is True
    assert chunk["content"] == "Orders\nMy orders\nTotal: R$\xa019,90\none\ntwo"
    assert chunk["next_offset"] is None


def test_html_text_ignores_svg_titles_and_scripts() -> None:
    html = (
        "<p>Pay<svg><g><title>credit card icon</title></g></svg>ment</p>"
        "<p>a<script>if (a < b) { x = '</p>' }</script>b</p><div>unclosed <b>bold"
    )
    assert html_to_text(html) == "Payment\nab\nunclosed bold"
    assert html_to_text("") == ""


def test_body_chunks_mask_secrets(api: TestClient) -> None:
    seed(api)
    rows = api.get("/v1/requests", params={"domain": "example.com"}).json()
    rid = next(r for r in rows if r["resource_type"] != "Document")["id"]
    for part in ("request", "response"):
        chunk = api.get(f"/v1/requests/{rid}/chunk", params={"part": part, "text": True}).json()
        assert chunk["text"] is False
        assert "hunter2" not in chunk["content"]
        assert "r3fr3sh" not in chunk["content"]


def test_openapi_has_masked_examples(api: TestClient) -> None:
    seed(api)
    spec = api.get("/v1/openapi/example.com").json()
    assert list(spec["paths"]) == ["/users/{userId}/orders"]
    op = spec["paths"]["/users/{userId}/orders"]["post"]
    params = {p["name"]: p["example"] for p in op["parameters"]}
    assert params == {"userId": "42", "page": "2", "access_token": "****"}
    response = op["responses"]["200"]["content"]["application/json"]["example"]
    assert len(response["items"]) == 3
    assert response["items"][0] == {"id": 0, "total": 19.9}
    request = op["requestBody"]["content"]["application/json"]["example"]
    assert request["filter"] == "open"
    text = json.dumps(spec)
    for secret in ("hunter2", "r3fr3sh", "t0k3n", "s3cr3t"):
        assert secret not in text


def test_bundle(api: TestClient) -> None:
    seed(api)
    r = api.get("/v1/export/example.com/bundle")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"README.md", "openapi.json", "timeline.json", "session.json"} <= names
    timeline = json.loads(z.read("timeline.json"))
    assert [t["seq"] for t in timeline] == [1, 2]
    html_file = timeline[0]["files"]["response_body"]
    assert html_file.endswith(".response.html")
    assert z.read(html_file).decode() == PAGE
    api_entry = timeline[1]
    assert api_entry["endpoint"] == "POST /users/{userId}/orders"
    assert api_entry["files"]["exchange"].startswith(
        "endpoints/POST_api.example.com_users_{userId}_orders/"
    )
    exchange_doc = json.loads(z.read(api_entry["files"]["exchange"]))
    assert exchange_doc["request"]["headers"]["authorization"] != BEARER
    session = json.loads(z.read("session.json"))
    assert [c["name"] for c in session["cookies"]] == ["sid"]
    everything = b"".join(z.read(n) for n in names if not n.endswith(".html")).decode()
    for secret in ("hunter2", "r3fr3sh", "t0k3n", "s3cr3t", "c00kie"):
        assert secret not in everything
    assert 'sessiontap.httpx_client("example.com")' in z.read("README.md").decode()


def test_bundle_unknown_domain(api: TestClient) -> None:
    assert api.get("/v1/export/nothing.example/bundle").status_code == 404


class RecordingDaemon:
    def __init__(self) -> None:
        self.raw: list[bytes] = []

    def call(self, method: str, path: str, body: Any = None, raw: bytes | None = None) -> Any:
        assert raw is not None
        self.raw.append(raw)
        return {"accepted": 1, "dropped": 0}


def part(seq: int, data: str, last: bool, upload: str = "u1") -> dict[str, Any]:
    return {
        "id": seq + 1,
        "type": "ingest_part",
        "upload": upload,
        "seq": seq,
        "data": data,
        "last": last,
    }


def test_native_host_reassembles_uploads() -> None:
    d, uploads = RecordingDaemon(), nativehost.Uploads()
    payload = json.dumps({"events": [{"type": "exchange", "body": "é" * 10}]})
    chunks = [payload[i : i + 7] for i in range(0, len(payload), 7)]
    replies = [
        nativehost.handle(part(i, c, i == len(chunks) - 1), d, uploads)
        for i, c in enumerate(chunks)
    ]
    assert all(r["ok"] for r in replies)
    assert replies[0]["data"] == {"partial": True}
    assert replies[-1]["data"] == {"accepted": 1, "dropped": 0}
    assert d.raw == [payload.encode()]
    assert uploads.parts == {}


def test_native_host_rejects_bad_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    d, uploads = RecordingDaemon(), nativehost.Uploads()
    assert nativehost.handle(part(1, "x", False), d, uploads)["error"] == "out_of_order"
    bad = {"id": 1, "type": "ingest_part", "upload": "", "seq": 0, "data": "x", "last": True}
    assert nativehost.handle(bad, d, uploads)["error"] == "invalid_arguments"
    monkeypatch.setattr(nativehost, "MAX_UPLOAD", 5)
    assert nativehost.handle(part(0, "123456", False), d, uploads)["error"] == "upload_too_large"
    assert d.raw == []
    for i in range(nativehost.MAX_UPLOADS + 2):
        nativehost.handle(part(0, "x", False, upload=f"u{i}"), d, uploads)
    assert len(uploads.parts) == nativehost.MAX_UPLOADS


def seed_mixed(api: TestClient) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    ingest(
        api,
        exchange("https://api.example.com/a", status=200),
        exchange("https://api.example.com/b", method="POST", status=201),
        exchange("https://api.example.com/c", method="DELETE", status=404),
        exchange("https://cdn.example.com/d", status=503, mime_type="text/plain"),
        exchange("https://api.example.com/e", status=None, error="net::ERR_FAILED"),
        page("https://www.example.com/", "<p>hi</p>"),
    )


def paths(api: TestClient, **params: Any) -> list[str]:
    rows = api.get("/v1/requests", params={"domain": "example.com", **params}).json()
    return sorted(r["path"] for r in rows)


def test_request_filters(api: TestClient) -> None:
    seed_mixed(api)
    assert paths(api, method=["post", "delete"]) == ["/b", "/c"]
    assert paths(api, status=["4xx", "5xx"]) == ["/c", "/d"]
    assert paths(api, status=["error"]) == ["/e"]
    assert paths(api, host="cdn.example.com") == ["/d"]
    assert paths(api, mime="text/html") == ["/"]
    assert paths(api, api_only=True) == ["/a", "/b", "/c", "/d", "/e"]
    assert paths(api, method="GET", status="2xx", api_only=True) == ["/a"]
    bad = api.get("/v1/requests", params={"domain": "example.com", "status": "6xx"})
    assert bad.status_code == 422


def test_request_pages_do_not_overlap(api: TestClient) -> None:
    seed_mixed(api)
    first = api.get("/v1/requests", params={"domain": "example.com", "limit": 4}).json()
    rest = api.get("/v1/requests", params={"domain": "example.com", "limit": 4, "offset": 4}).json()
    assert len(first) == 4
    assert len(rest) == 2
    assert not {r["id"] for r in first} & {r["id"] for r in rest}


def test_request_facets(api: TestClient) -> None:
    seed_mixed(api)
    facets = api.get("/v1/requests/facets", params={"domain": "example.com"}).json()
    assert facets["total"] == 6
    assert facets["methods"][0] == {"value": "GET", "count": 4}
    statuses = {s["value"]: s["count"] for s in facets["statuses"]}
    assert statuses == {"2xx": 3, "4xx": 1, "5xx": 1, "error": 1}
    assert {h["value"] for h in facets["hosts"]} == {
        "api.example.com",
        "cdn.example.com",
        "www.example.com",
    }
    api_only = api.get(
        "/v1/requests/facets", params={"domain": "example.com", "api_only": True}
    ).json()
    assert api_only["total"] == 5
    assert "text/html" not in {m["value"] for m in api_only["mime_types"]}
