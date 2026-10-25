import sys
import argparse
from sessiontap import __version__
from collections.abc import Sequence
from sessiontap.cli.context import Context
from sessiontap.client import SessionTapError
from sessiontap.cli.base import Command, CommandError


class App:
    def __init__(self, commands: Sequence[type[Command]], ctx: Context | None = None) -> None:
        self.ctx = ctx or Context()
        self.commands = [command(self.ctx) for command in commands]

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="sessiontap",
            description="Hand your real browser session to your scripts, locally and securely.",
        )
        parser.add_argument("--version", action="version", version=f"sessiontap {__version__}")
        sub = parser.add_subparsers(dest="command", required=True)
        for command in self.commands:
            command_parser = sub.add_parser(command.name, help=command.help)
            command.configure(command_parser)
            command_parser.set_defaults(handler=command)
        return parser

    def run(self, argv: Sequence[str] | None = None) -> None:
        args = self.parser().parse_args(argv)
        handler: Command = args.handler
        try:
            handler.run(args)
        except (CommandError, SessionTapError) as e:
            print(e, file=sys.stderr)
            raise SystemExit(1) from e
