import argparse
from sessiontap.cli.base import Command


class CookieHeader(Command):
    name = "cookie-header"
    help = "print the Cookie header for a domain"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("domain")

    def run(self, args: argparse.Namespace) -> None:
        self.ctx.print(self.ctx.client.cookie_header(args.domain))


class Secret(Command):
    name = "secret"
    help = "print the latest captured value of a credential header"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("domain")
        parser.add_argument("name", help='header name, e.g. "authorization"')

    def run(self, args: argparse.Namespace) -> None:
        self.ctx.print(self.ctx.client.secret(args.domain, args.name))
