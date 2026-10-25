import os
import json
import base64
import hashlib
from typing import Any

FORMAT = "sessiontap-export"
VERSION = 1
MAX_SCRYPT_N = 2**20


class ExportError(ValueError):
    pass


class ExportCipher:
    def __init__(self, n: int = 2**15, r: int = 8, p: int = 1) -> None:
        self.n, self.r, self.p = n, r, p

    def seal(self, data: dict[str, Any], passphrase: str) -> dict[str, Any]:
        salt, nonce = os.urandom(16), os.urandom(12)
        sealed = self._aead(passphrase, salt, self.n, self.r, self.p).encrypt(
            nonce, json.dumps(data).encode(), FORMAT.encode()
        )
        return {
            "format": FORMAT,
            "version": VERSION,
            "kdf": {"name": "scrypt", "n": self.n, "r": self.r, "p": self.p, "salt": _b64(salt)},
            "nonce": _b64(nonce),
            "ciphertext": _b64(sealed),
        }

    def open(self, doc: dict[str, Any], passphrase: str) -> dict[str, Any]:
        from cryptography.exceptions import InvalidTag

        if doc.get("format") != FORMAT or doc.get("version") != VERSION:
            raise ExportError("Not a SessionTap export file.")
        kdf = doc["kdf"]
        if kdf.get("name") != "scrypt" or not 0 < kdf.get("n", 0) <= MAX_SCRYPT_N:
            raise ExportError("Unsupported key derivation parameters.")
        aead = self._aead(passphrase, base64.b64decode(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
        try:
            payload = aead.decrypt(
                base64.b64decode(doc["nonce"]), base64.b64decode(doc["ciphertext"]), FORMAT.encode()
            )
        except InvalidTag as e:
            raise ExportError("Wrong passphrase or corrupted file.") from e
        result: dict[str, Any] = json.loads(payload)
        return result

    @staticmethod
    def _aead(passphrase: str, salt: bytes, n: int, r: int, p: int) -> Any:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = hashlib.scrypt(
            passphrase.encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * n * r * 2
        )
        return AESGCM(key)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
