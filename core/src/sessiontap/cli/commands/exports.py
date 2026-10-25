import os
import json
import argparse
from pathlib import Path
from urllib.parse import quote
from sessiontap.cli.base import Command


class OpenApi(Command):
    name = "openapi"
    help = "write the inferred OpenAPI description of a site (with masked examples)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("domain")
        parser.add_argument("-o", "--output", help="default: DOMAIN.openapi.json")

    def run(self, args: argparse.Namespace) -> None:
        spec = self.ctx.api("GET", f"/v1/openapi/{quote(args.domain, safe='')}")
        out = Path(args.output or f"{args.domain}.openapi.json")
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(spec, f, indent=2, ensure_ascii=False)
        self.ctx.print(f"{len(spec['paths'])} endpoints written to {out}")


class Bundle(Command):
    name = "bundle"
    help = "write a .zip for AI agents: OpenAPI, timeline, every request/response and HTML page"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("domain")
        parser.add_argument("-o", "--output", help="default: DOMAIN-sessiontap.zip")

    def run(self, args: argparse.Namespace) -> None:
        out = Path(args.output or f"{args.domain}-sessiontap.zip")
        size = self.ctx.client.download(f"/v1/export/{quote(args.domain, safe='')}/bundle", out)
        self.ctx.print(
            f"Bundle written to {out} ({size / 1024 / 1024:.1f} MiB).",
            "Secrets are masked, but pages and responses can hold personal data.",
            "Review the bundle before sharing it.",
        )
