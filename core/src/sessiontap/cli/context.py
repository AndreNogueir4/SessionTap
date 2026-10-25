import sys
from typing import Any, TextIO
from collections.abc import Callable
from sessiontap import config as cfg
from sessiontap.client import Client
from dataclasses import dataclass, field
from sessiontap.cli.process import DaemonProcess


@dataclass
class Context:
    client_factory: Callable[[], Client] = Client
    config_loader: Callable[[], cfg.Config] = cfg.load_config
    daemon: DaemonProcess = field(default_factory=DaemonProcess)
    out: TextIO = field(default_factory=lambda: sys.stdout)
    _client: Client | None = field(default=None, init=False, repr=False)

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = self.client_factory()
        return self._client

    @property
    def config(self) -> cfg.Config:
        return self.config_loader()

    def api(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        return self.client.api(method, path, body, **params)

    def print(self, *lines: str) -> None:
        for line in lines:
            print(line, file=self.out)
