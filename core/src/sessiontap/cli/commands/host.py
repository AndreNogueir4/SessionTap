import argparse
from sessiontap import hostinstall
from sessiontap.cli.base import Command, CommandError


class InstallHost(Command):
    name = "install-host"
    help = "register the native host for your browsers"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--browser", action="append", choices=hostinstall.BROWSER_NAMES)
        parser.add_argument(
            "--extension-id",
            action="append",
            help="also allow this Chromium extension ID (e.g. a store build)",
        )

    def run(self, args: argparse.Namespace) -> None:
        extra_ids: list[str] = args.extension_id or []
        try:
            done = hostinstall.install(args.browser or hostinstall.BROWSER_NAMES, extra_ids)
        except ValueError as e:
            raise CommandError(str(e)) from e
        extra = f" (+ {', '.join(extra_ids)})" if extra_ids else ""
        self.ctx.print(
            "Native host registered for:",
            *(f"  {line}" for line in done),
            f"Allowed Chromium extension ID: {hostinstall.EXTENSION_ID}{extra}",
        )


class UninstallHost(Command):
    name = "uninstall-host"
    help = "remove the native host registration"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--browser", action="append", choices=hostinstall.BROWSER_NAMES)

    def run(self, args: argparse.Namespace) -> None:
        removed = hostinstall.uninstall(args.browser or hostinstall.BROWSER_NAMES)
        self.ctx.print(*(removed or ["Nothing to remove."]))
