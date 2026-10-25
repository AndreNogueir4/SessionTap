from sessiontap.cli.app import App
from collections.abc import Sequence
from sessiontap.cli.context import Context
from sessiontap.cli.commands import COMMANDS


def main(argv: Sequence[str] | None = None, ctx: Context | None = None) -> None:
    App(COMMANDS, ctx).run(argv)


__all__ = ["App", "Context", "main"]
