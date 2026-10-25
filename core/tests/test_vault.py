import os
import sys
import stat
import time
import pytest
import hashlib
import sqlite3
from pathlib import Path
from sessiontap.server.vault import Vault
from sessiontap import config as cfg, secretfile
from sessiontap.server.daemon import open_runtime
from sessiontap.server.crypto import Cipher, load_key, VaultKeyError


def test_secrets_are_encrypted_at_rest(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = Vault(path, Cipher(os.urandom(32)))
    vault.set_capture("example.com", True)
    vault.upsert_cookie(
        "example.com", {"name": "sid", "value": "COOKIE-SECRET-VALUE", "domain": "example.com"}
    )
    vault.upsert_token("example.com", "authorization", "Bearer TOKEN-SECRET-VALUE")
    vault.add_request(
        "example.com",
        "example.com",
        "/api",
        {
            "url": "https://example.com/api?key=URL-SECRET",
            "method": "POST",
            "request_headers": {"cookie": "sid=HEADER-SECRET"},
            "request_body": "BODY-SECRET",
        },
    )
    vault.replace_storage("example.com", "https://example.com", "local", {"k": "STORAGE-SECRET"})
    vault.close()
    raw = b""
    for p in tmp_path.iterdir():
        raw += p.read_bytes()
    for secret in (
        b"COOKIE-SECRET",
        b"TOKEN-SECRET",
        b"URL-SECRET",
        b"HEADER-SECRET",
        b"BODY-SECRET",
        b"STORAGE-SECRET",
    ):
        assert secret not in raw, secret


def test_wrong_key_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    Vault(path, Cipher(os.urandom(32))).close()
    with pytest.raises(VaultKeyError):
        Vault(path, Cipher(os.urandom(32)))


def test_ciphertext_bound_to_column() -> None:
    c = Cipher(os.urandom(32))
    sealed = c.seal("value", "cookies.value")
    with pytest.raises(VaultKeyError):
        c.open(sealed, "tokens.value")


def test_retention(vault: Vault) -> None:
    vault.add_request(
        "example.com",
        "example.com",
        "/old",
        {"url": "https://example.com/old", "method": "GET", "started_at": time.time() - 30 * 86400},
    )
    vault.add_request(
        "example.com", "example.com", "/new", {"url": "https://example.com/new", "method": "GET"}
    )
    vault.upsert_cookie(
        "example.com",
        {"name": "gone", "value": "v", "domain": "example.com", "expires": time.time() - 1},
    )
    removed = vault.apply_retention()
    assert removed["requests"] == 1
    assert removed["cookies"] == 1
    assert [r["path"] for r in vault.list_requests()] == ["/new"]


def test_search_escapes_wildcards(vault: Vault) -> None:
    vault.add_request(
        "example.com", "example.com", "/a_b", {"url": "https://e/a_b", "method": "GET"}
    )
    vault.add_request(
        "example.com", "example.com", "/axb", {"url": "https://e/axb", "method": "GET"}
    )
    assert [r["path"] for r in vault.list_requests(q="a_b")] == ["/a_b"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_files_are_private(tmp_path: Path) -> None:
    rt = open_runtime()
    rt.vault.set_capture("example.com", True)
    token = secretfile.ensure_token(cfg.token_path())
    assert token
    for path in (cfg.db_path(), cfg.token_path(), cfg.key_path()):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    assert stat.S_IMODE(cfg.home_dir().stat().st_mode) == 0o700
    rt.vault.close()


def test_file_key_backend_is_stable(tmp_path: Path) -> None:
    k1, b1 = load_key("file", tmp_path, tmp_path / "vault.key")
    k2, b2 = load_key("file", tmp_path, tmp_path / "vault.key")
    assert k1 == k2 and len(k1) == 32 and b1 == b2 == "file"


def test_token_rotation(tmp_path: Path) -> None:
    path = tmp_path / "token"
    first = secretfile.ensure_token(path)
    assert secretfile.ensure_token(path) == first
    assert secretfile.rotate_token(path) != first
    assert len(first) >= 43


def test_lookup_hash_does_not_leak_value(vault: Vault) -> None:
    vault.upsert_token("example.com", "authorization", "Bearer A")
    vault.upsert_token("example.com", "authorization", "Bearer A")
    assert len(vault.list_tokens()) == 1
    db = sqlite3.connect(vault.path)
    lookup = db.execute("SELECT lookup FROM tokens").fetchone()[0]
    assert lookup != hashlib.sha256(b"Bearer A").hexdigest()
