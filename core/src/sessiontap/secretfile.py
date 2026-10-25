import os
import sys
import stat
import secrets
from pathlib import Path


def write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    restrict_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_secret(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def is_private(path: Path) -> bool:
    if sys.platform == "win32":
        return True
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def restrict(path: Path) -> None:
    if sys.platform != "win32" and path.exists():
        os.chmod(path, 0o600)


def restrict_dir(path: Path) -> None:
    if sys.platform != "win32" and path.exists():
        os.chmod(path, 0o700)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_token(path: Path) -> str:
    token = read_secret(path)
    if token is None:
        token = new_token()
        write_secret(path, token)
    elif not is_private(path):
        restrict(path)
    return token


def rotate_token(path: Path) -> str:
    token = new_token()
    write_secret(path, token)
    return token
