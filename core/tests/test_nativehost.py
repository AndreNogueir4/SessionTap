import io
import sys
import json
import base64
import pytest
import struct
import hashlib
from typing import Any
from pathlib import Path
from sessiontap import hostinstall, nativehost


def frame(obj: Any) -> bytes:
    data = json.dumps(obj).encode()
    return struct.pack("<I", len(data)) + data


def test_roundtrip() -> None:
    out = io.BytesIO()
    nativehost.write_message(out, {"id": 1, "ok": True})
    out.seek(0)
    assert nativehost.read_message(out) == {"id": 1, "ok": True}


def test_eof_returns_none() -> None:
    assert nativehost.read_message(io.BytesIO(b"")) is None


@pytest.mark.parametrize(
    "data",
    [
        struct.pack("<I", nativehost.MAX_IN + 1),
        struct.pack("<I", 0),
        struct.pack("<I", 100) + b"{}",
        b"\x01\x00",
    ],
)
def test_bad_frames_rejected(data: bytes) -> None:
    with pytest.raises(nativehost.ProtocolError):
        nativehost.read_message(io.BytesIO(data))


def test_non_object_rejected() -> None:
    with pytest.raises(nativehost.ProtocolError):
        nativehost.read_message(io.BytesIO(frame([1, 2])))


def test_oversized_reply_replaced() -> None:
    out = io.BytesIO()
    nativehost.write_message(out, {"id": 7, "data": "x" * (nativehost.MAX_OUT + 1)})
    out.seek(0)
    assert nativehost.read_message(out) == {"id": 7, "ok": False, "error": "reply_too_large"}


class FakeDaemon(nativehost.Daemon):
    def __init__(self) -> None:
        super().__init__(8711, "t")
        self.calls: list[tuple[str, str, Any]] = []

    def call(self, method: str, path: str, body: Any = None) -> Any:
        self.calls.append((method, path, body))
        return {"ok": True, "code": "c0de"}


def test_handle_validates_messages() -> None:
    d = FakeDaemon()
    assert nativehost.handle({"type": "hello"}, d)["error"] == "missing_id"
    assert nativehost.handle({"id": 1, "type": "shell"}, d)["error"] == "unknown_type"
    bad = {"id": 2, "type": "set_capture", "domain": "x.com", "enabled": "yes"}
    assert nativehost.handle(bad, d)["error"] == "invalid_arguments"
    assert nativehost.handle({"id": 3, "type": "ingest", "events": {}}, d)["ok"] is False
    assert d.calls == []


def test_handle_forwards() -> None:
    d = FakeDaemon()
    assert nativehost.handle({"id": 1, "type": "hello"}, d)["ok"] is True
    nativehost.handle({"id": 2, "type": "set_capture", "domain": "a/../b", "enabled": True}, d)
    nativehost.handle({"id": 3, "type": "ingest", "events": []}, d)
    assert d.calls == [
        ("GET", "/v1/capture-state", None),
        ("PUT", "/v1/domains/a%2F..%2Fb", {"capture": True}),
        ("POST", "/v1/ingest", {"events": []}),
    ]


def test_unreachable_daemon() -> None:
    d = nativehost.Daemon(1, "t")
    assert nativehost.handle({"id": 1, "type": "hello"}, d) == {
        "id": 1,
        "ok": False,
        "error": "daemon_unreachable",
    }


def test_manifest_locks_extension_ids(tmp_path: Path) -> None:
    chrome = hostinstall.BROWSERS[0]
    firefox = next(b for b in hostinstall.BROWSERS if b.firefox)
    m = hostinstall.manifest(chrome, tmp_path / "host", [])
    assert m["allowed_origins"] == [f"chrome-extension://{hostinstall.EXTENSION_ID}/"]
    assert "allowed_extensions" not in m
    m = hostinstall.manifest(firefox, tmp_path / "host", [])
    assert m["allowed_extensions"] == [hostinstall.FIREFOX_EXTENSION_ID]


def test_extension_id_matches_manifest_key() -> None:
    manifest = Path(__file__).parents[2] / "extension" / "manifest.chromium.json"
    if not manifest.exists():
        pytest.skip("extension sources not present")
    key = base64.b64decode(json.loads(manifest.read_text())["key"])
    digest = hashlib.sha256(key).hexdigest()[:32]
    assert "".join(chr(ord("a") + int(c, 16)) for c in digest) == hostinstall.EXTENSION_ID


def test_install_rejects_bad_extension_id() -> None:
    with pytest.raises(ValueError):
        hostinstall.install(["chrome"], ["../../etc"])


@pytest.mark.skipif(sys.platform == "win32", reason="registry on Windows")
def test_install_and_uninstall(tmp_path: Path) -> None:
    done = hostinstall.install(["chrome", "firefox"], [])
    assert len(done) == 2
    target = Path.home() / ".config/google-chrome/NativeMessagingHosts/com.sessiontap.host.json"
    if sys.platform == "darwin":
        target = (
            Path.home()
            / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
            / "com.sessiontap.host.json"
        )
    data = json.loads(target.read_text())
    launcher = Path(data["path"])
    assert launcher.exists() and launcher.stat().st_mode & 0o777 == 0o700
    assert "sessiontap.nativehost" in launcher.read_text()
    assert len(hostinstall.uninstall(["chrome", "firefox"])) == 2
    assert not target.exists()


def test_login_code_includes_port() -> None:
    d = FakeDaemon()
    reply = nativehost.handle({"id": 1, "type": "login_code"}, d)
    assert reply["data"] == {"code": "c0de", "port": 8711}
    assert d.calls == [("POST", "/v1/auth/login-code", None)]


def test_site_summary_route() -> None:
    d = FakeDaemon()
    nativehost.handle({"id": 1, "type": "site_summary", "domain": "a/b.com"}, d)
    assert d.calls == [("GET", "/v1/domains/a%2Fb.com/summary", None)]
    assert nativehost.handle({"id": 2, "type": "site_summary"}, d)["error"] == "invalid_arguments"
