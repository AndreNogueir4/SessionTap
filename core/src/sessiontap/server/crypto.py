import os
import hmac
import base64
import hashlib
import keyring
import logging
from pathlib import Path
from keyring.backends import fail
from sessiontap import secretfile
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger(__name__)

KEYRING_SERVICE = "sessiontap"
_NONCE = 12


class VaultKeyError(RuntimeError):
    pass


class Cipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("vault key must be 32 bytes")
        self._aead = AESGCM(key)
        self._mac_key = hmac.new(key, b"sessiontap-lookup", hashlib.sha256).digest()

    def seal(self, value: str | bytes | None, column: str) -> bytes | None:
        if value is None:
            return None
        data = value.encode("utf-8") if isinstance(value, str) else value
        nonce = os.urandom(_NONCE)
        return nonce + self._aead.encrypt(nonce, data, column.encode())

    def open_bytes(self, blob: bytes | None, column: str) -> bytes | None:
        if blob is None:
            return None
        try:
            return self._aead.decrypt(blob[:_NONCE], blob[_NONCE:], column.encode())
        except InvalidTag as e:
            raise VaultKeyError(
                f"cannot decrypt {column}: wrong vault key or corrupted data"
            ) from e

    def open(self, blob: bytes | None, column: str) -> str | None:
        data = self.open_bytes(blob, column)
        return None if data is None else data.decode("utf-8", errors="replace")

    def lookup_hash(self, value: str) -> str:
        return hmac.new(self._mac_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _keyring_usable() -> bool:
    try:
        backend = keyring.get_keyring()
        return not isinstance(backend, fail.Keyring) and backend.priority > 0
    except Exception:
        return False


def _keyring_username(home: Path) -> str:
    digest = hashlib.sha256(str(home.resolve()).encode()).hexdigest()[:16]
    return f"vault-key:{digest}"


def load_key(backend: str, home: Path, key_file: Path) -> tuple[bytes, str]:
    use_keyring = backend == "keyring" or (backend == "auto" and _keyring_usable())
    if use_keyring:
        username = _keyring_username(home)
        try:
            stored = keyring.get_password(KEYRING_SERVICE, username)
            if stored is None:
                stored = base64.b64encode(os.urandom(32)).decode()
                keyring.set_password(KEYRING_SERVICE, username, stored)
            return base64.b64decode(stored), "keyring"
        except Exception as e:
            if backend == "keyring":
                raise VaultKeyError(f"OS keyring unavailable: {e}") from e
            log.warning("OS keyring failed (%s); falling back to a key file", type(e).__name__)
    stored_file = secretfile.read_secret(key_file)
    if stored_file is None:
        stored_file = base64.b64encode(os.urandom(32)).decode()
        secretfile.write_secret(key_file, stored_file)
    elif not secretfile.is_private(key_file):
        secretfile.restrict(key_file)
    return base64.b64decode(stored_file), "file"


def delete_key(home: Path, key_file: Path) -> None:
    key_file.unlink(missing_ok=True)
    if _keyring_usable():
        try:
            keyring.delete_password(KEYRING_SERVICE, _keyring_username(home))
        except Exception:
            log.debug("no keyring entry to delete")
