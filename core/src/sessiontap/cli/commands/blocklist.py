import argparse
from urllib.parse import quote
from sessiontap.cli.base import Command, CommandError


class Blocklist(Command):
    name = "blocklist"
    help = "list, add or remove sites that can never be captured"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("action", choices=["list", "add", "remove", "reset"])
        parser.add_argument("domain", nargs="?")

    def run(self, args: argparse.Namespace) -> None:
        if args.action in ("add", "remove") and not args.domain:
            raise CommandError(f"usage: sessiontap blocklist {args.action} DOMAIN")
        if args.action == "add":
            view = self.ctx.api("POST", "/v1/blocklist", {"domain": args.domain})
            self.ctx.print(f"{args.domain} added: it and its subdomains will never be captured.")
        elif args.action == "remove":
            view = self.ctx.api("DELETE", f"/v1/blocklist/{quote(args.domain, safe='')}")
            self.ctx.print(f"{args.domain} removed from the blocklist.")
        elif args.action == "reset":
            view = self.ctx.api("POST", "/v1/blocklist/reset")
            self.ctx.print("Blocklist restored to the defaults.")
        else:
            view = self.ctx.api("GET", "/v1/blocklist")
            for entry in view["domains"]:
                origin = "default" if entry["default"] else "custom"
                self.ctx.print(f"{entry['domain']:<40} {origin}")
        if view["locked"]:
            self.ctx.print("(managed by config.toml: [capture] locked = true)")
