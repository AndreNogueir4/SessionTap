import os
import json
import getpass
import argparse
from pathlib import Path
from sessiontap.cli.crypto import ExportCipher, ExportError
from sessiontap.cli.base import Command, CommandError, require_server_extra

PASSPHRASE_ENV = "SESSIONTAP_PASSPHRASE"  # noqa: S105
MIN_PASSPHRASE = 12


def read_passphrase(confirm: bool) -> str:
    from_env = os.environ.get(PASSPHRASE_ENV)
    phrase = from_env or getpass.getpass("Passphrase: ")
    if len(phrase) < MIN_PASSPHRASE:
        raise CommandError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters.")
    if confirm and not from_env and getpass.getpass("Repeat passphrase: ") != phrase:
        raise CommandError("Passphrases do not match.")
    return phrase


class Export(Command):
    name = "export"
    help = "write an encrypted, passphrase-protected session file"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--domain", required=True)
        parser.add_argument("-o", "--output", required=True)

    def run(self, args: argparse.Namespace) -> None:
        require_server_extra()
        session = self.ctx.api("GET", f"/v1/sessions/{args.domain}")
        tokens = self.ctx.api("GET", "/v1/tokens", domain=args.domain, reveal="true")
        data = {
            "domain": session["domain"],
            "cookies": session["cookies"],
            "storage": session["storage"],
            "fingerprint": session["fingerprint"],
            "tokens": [
                {"kind": t["kind"], "value": t["value"], "expires_at": t["expires_at"]}
                for t in tokens
            ],
        }
        doc = ExportCipher().seal(data, read_passphrase(confirm=True))
        out = Path(args.output)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        self.ctx.print(f"Encrypted session for {session['domain']} written to {out}")


class Import(Command):
    name = "import"
    help = "import an encrypted session file"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file")

    def run(self, args: argparse.Namespace) -> None:
        require_server_extra()
        doc = json.loads(Path(args.file).read_text())
        try:
            data = ExportCipher().open(doc, read_passphrase(confirm=False))
        except ExportError as e:
            raise CommandError(str(e)) from e
        result = self.ctx.api("POST", "/v1/sessions/import", data)
        self.ctx.print(
            f"Imported {result['cookies']} cookies and {result['tokens']} tokens "
            f"for {result['imported']}."
        )
