import argparse
import webbrowser
from sessiontap.client import SessionTapError
from sessiontap import __version__, config as cfg, secretfile
from sessiontap.cli.base import Command, CommandError, require_server_extra


class Start(Command):
    name = "start"
    help = "start the daemon (foreground unless --detach)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--detach", "-d", action="store_true", help="run in the background")

    def run(self, args: argparse.Namespace) -> None:
        require_server_extra()
        if self.ctx.daemon.running_pid():
            raise CommandError("SessionTap is already running (`sessiontap status`).")
        if not args.detach:
            from sessiontap.server.daemon import serve

            serve()
            return
        if not self.ctx.daemon.start_detached():
            raise CommandError(f"SessionTap did not start; see {self.ctx.daemon.log_file}")
        self.ctx.print(
            f"SessionTap started on http://127.0.0.1:{self.ctx.config.port} "
            f"(log: {self.ctx.daemon.log_file})"
        )


class Stop(Command):
    name = "stop"
    help = "stop a detached daemon"

    def run(self, args: argparse.Namespace) -> None:
        stopped = self.ctx.daemon.stop()
        self.ctx.print("SessionTap stopped." if stopped else "SessionTap is not running.")


class Status(Command):
    name = "status"
    help = "show daemon and vault status"

    def run(self, args: argparse.Namespace) -> None:
        try:
            status = self.ctx.client.status()
        except SessionTapError as e:
            raise CommandError(f"SessionTap {__version__}: not running ({e})") from e
        backend = status["key_backend"]
        note = (
            "" if backend == "keyring" else "  ⚠ key file next to the vault; prefer an OS keyring"
        )
        capturing = ", ".join(status["capture_domains"]) or "(nothing — opt in per site)"
        self.ctx.print(
            f"SessionTap {status['version']} — running on 127.0.0.1:{self.ctx.config.port}",
            f"  home:        {cfg.home_dir()}",
            f"  vault key:   {backend}{note}",
            f"  vault size:  {status['vault_bytes'] / 1024:.0f} KiB, "
            f"retention {status['retention_days']} days",
            f"  capturing:   {capturing}",
            "  stored:      " + ", ".join(f"{v} {k}" for k, v in status["counts"].items()),
        )


class Open(Command):
    name = "open"
    help = "open the dashboard, already signed in"

    def run(self, args: argparse.Namespace) -> None:
        data = self.ctx.api("POST", "/v1/auth/login-code")
        url = f"http://127.0.0.1:{self.ctx.config.port}/#code={data['code']}"
        if not webbrowser.open(url):
            self.ctx.print(f"Open this link within {data['expires_in']} seconds: {url}")


class Token(Command):
    name = "token"
    help = "print the token file path, the token, or rotate it"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--show", action="store_true", help="print the token itself")
        group.add_argument("--rotate", action="store_true", help="replace the token")

    def run(self, args: argparse.Namespace) -> None:
        path = cfg.token_path()
        if args.rotate:
            secretfile.rotate_token(path)
            self.ctx.print(
                f"New token written to {path}. Clients reading the file pick it up automatically."
            )
        elif args.show:
            token = secretfile.read_secret(path)
            if token is None:
                raise CommandError("No token yet; run `sessiontap start` once.")
            self.ctx.print(token)
        else:
            self.ctx.print(str(path))
