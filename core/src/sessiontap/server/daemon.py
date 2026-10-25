import os
import sys
import logging
import uvicorn
from dataclasses import dataclass
from sessiontap.server.vault import Vault
from sessiontap.server.app import create_app
from sessiontap.server.crypto import Cipher, load_key
from sessiontap import __version__, config as cfg, secretfile

LOOPBACK = "127.0.0.1"
log = logging.getLogger("sessiontap")


@dataclass
class Runtime:
    config: cfg.Config
    vault: Vault
    key_backend: str


def open_runtime(config: cfg.Config | None = None) -> Runtime:
    if sys.platform != "win32":
        os.umask(0o077)
    config = config or cfg.load_config()
    home = cfg.home_dir()
    home.mkdir(parents=True, exist_ok=True)
    secretfile.restrict_dir(home)
    key, backend = load_key(config.key_backend, home, cfg.key_path())
    vault = Vault(cfg.db_path(), Cipher(key))
    return Runtime(config, vault, backend)


def serve(config: cfg.Config | None = None) -> None:
    rt = open_runtime(config)
    token_file = cfg.token_path()
    secretfile.ensure_token(token_file)

    def token_getter() -> str:
        return secretfile.read_secret(token_file) or ""

    app = create_app(rt.vault, rt.config, token_getter, key_backend=rt.key_backend)
    if rt.key_backend == "file":
        log.warning(
            "OS keyring unavailable: the vault key is stored in %s. Anyone who can read your "
            "files can decrypt the vault.",
            cfg.key_path(),
        )
    pid_file = cfg.pid_path()
    pid_file.write_text(str(os.getpid()))
    print(
        f"SessionTap {__version__} listening on http://{LOOPBACK}:{rt.config.port} (loopback only)",
        flush=True,
    )
    try:
        uvicorn.run(
            app,
            host=LOOPBACK,
            port=rt.config.port,
            log_level="warning",
            access_log=False,
            server_header=False,
            proxy_headers=False,
        )
    finally:
        pid_file.unlink(missing_ok=True)
        rt.vault.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    serve()
