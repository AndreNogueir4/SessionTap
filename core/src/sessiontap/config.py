import os
import tomllib
import platformdirs
from pathlib import Path
from dataclasses import dataclass, field

APP_NAME = "sessiontap"
DEFAULT_PORT = 8711
NATIVE_HOST_NAME = "com.sessiontap.host"

DEFAULT_BLOCKLIST: tuple[str, ...] = ("example.block.com",)


def home_dir() -> Path:
    override = os.environ.get("SESSIONTAP_HOME")
    if override:
        return Path(override).expanduser()
    return platformdirs.user_data_path(APP_NAME, appauthor=False)


def config_path() -> Path:
    return home_dir() / "config.toml"


def token_path() -> Path:
    return home_dir() / "token"


def db_path() -> Path:
    return home_dir() / "vault.db"


def key_path() -> Path:
    return home_dir() / "vault.key"


def pid_path() -> Path:
    return home_dir() / "daemon.pid"


@dataclass(frozen=True)
class Config:
    port: int = DEFAULT_PORT
    key_backend: str = "auto"
    max_body_kb: int = 512
    capture_html: bool = True
    capture_locked: bool = False
    blocklist: tuple[str, ...] = field(default=DEFAULT_BLOCKLIST)

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_kb * 1024


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    data: dict[str, object] = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)
    server = data.get("server", {})
    capture = data.get("capture", {})
    vault = data.get("vault", {})
    if not isinstance(server, dict) or not isinstance(capture, dict) or not isinstance(vault, dict):
        raise ValueError(f"{path}: [server], [capture] and [vault] must be tables")
    port = int(str(os.environ.get("SESSIONTAP_PORT") or server.get("port", DEFAULT_PORT)))
    if not 1024 <= port <= 65535:
        raise ValueError(f"port must be between 1024 and 65535, got {port}")
    key_backend = str(os.environ.get("SESSIONTAP_KEY_BACKEND", vault.get("key_backend", "auto")))
    if key_backend not in ("auto", "keyring", "file"):
        raise ValueError(f"key_backend must be auto, keyring or file, got {key_backend!r}")
    blocklist = capture.get("blocklist", list(DEFAULT_BLOCKLIST))
    if not isinstance(blocklist, list) or not all(isinstance(d, str) for d in blocklist):
        raise ValueError("capture.blocklist must be a list of domains")
    max_body_kb = int(capture.get("max_body_kb", 512))
    if not 0 <= max_body_kb <= 4096:
        raise ValueError("capture.max_body_kb must be between 0 and 4096")
    capture_html = capture.get("html", True)
    capture_locked = capture.get("locked", False)
    if not isinstance(capture_html, bool) or not isinstance(capture_locked, bool):
        raise ValueError("capture.html and capture.locked must be true or false")
    return Config(
        port=port,
        key_backend=key_backend,
        max_body_kb=max_body_kb,
        capture_html=capture_html,
        capture_locked=capture_locked,
        blocklist=tuple(d.lower().strip(".") for d in blocklist),
    )
