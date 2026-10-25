import argparse
from pathlib import Path
from sessiontap import config as cfg
from sessiontap.cli.base import Command, CommandError, require_server_extra


class Capture(Command):
    name = "capture"
    help = "list domains, or allow/deny capture for one"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("action", choices=["list", "allow", "deny"])
        parser.add_argument("domain", nargs="?")

    def run(self, args: argparse.Namespace) -> None:
        if args.action == "list":
            self._list()
            return
        if not args.domain:
            raise CommandError("usage: sessiontap capture allow|deny DOMAIN")
        result = self.ctx.api(
            "PUT", f"/v1/domains/{args.domain}", {"capture": args.action == "allow"}
        )
        state = "enabled" if result["capture"] else "disabled"
        self.ctx.print(f"Capture {state} for {result['domain']} (and its subdomains).")

    def _list(self) -> None:
        for d in self.ctx.api("GET", "/v1/domains"):
            mark = "●" if d["capture"] else "○"
            self.ctx.print(
                f"{mark} {d['domain']:<40} {d['requests']:>6} requests "
                f"{d['cookies']:>4} cookies {d['tokens']:>4} tokens"
            )


class Purge(Command):
    name = "purge"
    help = "delete stored data for a domain, or everything"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--domain")
        group.add_argument("--all", action="store_true", help="delete the vault and its key")
        parser.add_argument("--yes", action="store_true")

    def run(self, args: argparse.Namespace) -> None:
        if args.domain:
            self.ctx.api("DELETE", f"/v1/domains/{args.domain}")
            self.ctx.print(f"Deleted everything stored for {args.domain}.")
        elif args.all:
            self._purge_all(confirmed=args.yes)
        else:
            raise CommandError("usage: sessiontap purge --domain DOMAIN | --all")

    def _purge_all(self, confirmed: bool) -> None:
        if self.ctx.daemon.running_pid():
            raise CommandError("Stop the daemon first: `sessiontap stop`.")
        if not confirmed and input("Delete the whole vault and its key? [y/N] ").lower() != "y":
            return
        require_server_extra()
        from sessiontap.server.crypto import delete_key

        db = cfg.db_path()
        for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
            path.unlink(missing_ok=True)
        delete_key(cfg.home_dir(), cfg.key_path())
        self.ctx.print("Vault deleted.")
