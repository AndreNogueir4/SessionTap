import pytest
from typing import Any
from pathlib import Path
from collections.abc import Iterator
from sessiontap.client import Client
from fastapi.testclient import TestClient
from sessiontap.server.vault import Vault
from sessiontap.server.crypto import Cipher
from sessiontap.server.app import create_app
from sessiontap import config as cfg, secretfile

PORT = 8711
BASE = f"http://127.0.0.1:{PORT}"
LOOPBACK_PEER = ("127.0.0.1", 50000)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("SESSIONTAP_HOME", str(home))
    monkeypatch.setenv("SESSIONTAP_KEY_BACKEND", "file")
    monkeypatch.delenv("SESSIONTAP_PORT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    return home


@pytest.fixture
def config() -> cfg.Config:
    return cfg.load_config()


@pytest.fixture
def vault(tmp_path: Path) -> Iterator[Vault]:
    v = Vault(tmp_path / "vault.db", Cipher(b"k" * 32))
    yield v
    v.close()


@pytest.fixture
def token() -> str:
    return secretfile.ensure_token(cfg.token_path())


@pytest.fixture
def app(vault: Vault, config: cfg.Config, token: str) -> Any:
    return create_app(vault, config, lambda: token, key_backend="file")


@pytest.fixture
def anon(app: Any) -> Iterator[TestClient]:
    with TestClient(app, base_url=BASE, client=LOOPBACK_PEER) as c:
        yield c


@pytest.fixture
def api(app: Any, token: str) -> Iterator[TestClient]:
    with TestClient(
        app, base_url=BASE, client=LOOPBACK_PEER, headers={"authorization": f"Bearer {token}"}
    ) as c:
        yield c


@pytest.fixture
def sdk(api: TestClient) -> Client:
    return Client(http=api)


def exchange(url: str, **extra: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "exchange",
        "url": url,
        "method": "GET",
        "status": 200,
        "request_headers": {"accept": "application/json"},
        "response_headers": {"content-type": "application/json"},
        "mime_type": "application/json",
        "resource_type": "XHR",
    }
    event.update(extra)
    return event
