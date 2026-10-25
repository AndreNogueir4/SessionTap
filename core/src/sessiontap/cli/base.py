import argparse
from typing import ClassVar
from importlib.util import find_spec
from sessiontap.cli.context import Context


class CommandError(Exception):
    pass


class Command:
    name: ClassVar[str]
    help: ClassVar[str]

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    def configure(self, parser: argparse.ArgumentParser) -> None:
        pass

    def run(self, args: argparse.Namespace) -> None:
        raise NotImplementedError


def require_server_extra() -> None:
    if find_spec("cryptography") is None or find_spec("fastapi") is None:
        raise CommandError(
            "This command needs the daemon. In the SessionTap folder run: "
            'uv tool install "./core[server]"'
        )
