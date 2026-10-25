import io
import json
import pytest
import zipfile
import argparse
from pathlib import Path
from .conftest import exchange
from sessiontap.client import Client
from fastapi.testclient import TestClient
from sessiontap.cli.commands import COMMANDS
from sessiontap.cli import App, Context, main
from sessiontap.cli.process import DaemonProcess
from sessiontap.cli.base import Command, CommandError
from sessiontap.cli.crypto import ExportCipher, ExportError


class FakeDaemon(DaemonProcess):
    def __init__(self, pid: int | None) -> None:
        super().__init__()
        self.pid = pid
        self.stopped = False

    def running_pid(self) -> int | None:
        return self.pid

    def stop(self) -> bool:
        self.stopped = self.pid is not None
        return self.stopped


def run(argv: list[str], ctx: Context) -> str:
    out = io.StringIO()
    ctx.out = out
    main(argv, ctx)
    return out.getvalue()


def test_every_command_is_registered_once() -> None:
    names = [c.name for c in COMMANDS]
    assert len(names) == len(set(names))
    help_text = App(COMMANDS).parser().format_help()
    for name in names:
        assert name in help_text


def test_stop_uses_injected_daemon() -> None:
    daemon = FakeDaemon(pid=123)
    assert run(["stop"], Context(daemon=daemon)) == "SessionTap stopped.\n"
    assert daemon.stopped
    assert run(["stop"], Context(daemon=FakeDaemon(None))) == "SessionTap is not running.\n"


def test_start_refuses_when_running(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["start", "--detach"], Context(daemon=FakeDaemon(pid=1)))
    assert exit_info.value.code == 1
    assert "already running" in capsys.readouterr().err


def test_capture_commands(api: TestClient, sdk: Client) -> None:
    ctx = Context(client_factory=lambda: sdk)
    assert "Capture enabled for example.com" in run(["capture", "allow", "example.com"], ctx)
    assert "● example.com" in run(["capture", "list"], ctx)
    assert "disabled" in run(["capture", "deny", "example.com"], ctx)


def test_api_errors_become_clean_messages(
    api: TestClient, sdk: Client, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["capture", "allow", "example.block.com"], Context(client_factory=lambda: sdk))
    err = capsys.readouterr().err
    assert "blocklist" in err
    assert "Traceback" not in err


def test_client_is_created_lazily() -> None:
    def explode() -> Client:
        raise AssertionError("commands that don't need the daemon must not create a client")

    out = run(["token"], Context(client_factory=explode))
    assert out.strip().endswith("token")


def test_custom_command_can_be_plugged_in() -> None:
    class Hello(Command):
        name = "hello"
        help = "say hello"

        def configure(self, parser: argparse.ArgumentParser) -> None:
            parser.add_argument("who")

        def run(self, args: argparse.Namespace) -> None:
            if args.who == "nobody":
                raise CommandError("no one to greet")
            self.ctx.print(f"hello {args.who}")

    out = io.StringIO()
    App([Hello], Context(out=out)).run(["hello", "ana"])
    assert out.getvalue() == "hello ana\n"
    with pytest.raises(SystemExit):
        App([Hello], Context(out=out)).run(["hello", "nobody"])


def test_export_cipher_roundtrip_and_tamper(tmp_path: Path) -> None:
    cipher = ExportCipher(n=2**10)
    doc = cipher.seal({"domain": "example.com"}, "a long passphrase")
    assert cipher.open(doc, "a long passphrase") == {"domain": "example.com"}
    with pytest.raises(ExportError, match="Wrong passphrase"):
        cipher.open(doc, "another passphrase")
    with pytest.raises(ExportError, match="Unsupported"):
        cipher.open({**doc, "kdf": {**doc["kdf"], "n": 2**30}}, "a long passphrase")
    with pytest.raises(ExportError, match="Not a SessionTap"):
        cipher.open({"format": "zip"}, "x")


def test_openapi_and_bundle_commands(
    api: TestClient, sdk: Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.put("/v1/domains/example.com", json={"capture": True})
    api.post(
        "/v1/ingest", json={"events": [exchange("https://example.com/api/x", response_body="{}")]}
    )
    monkeypatch.chdir(tmp_path)
    ctx = Context(client_factory=lambda: sdk)
    assert "1 endpoints" in run(["openapi", "example.com"], ctx)
    assert json.loads((tmp_path / "example.com.openapi.json").read_text())["openapi"] == "3.1.0"
    assert "Bundle written" in run(["bundle", "example.com", "-o", "b.zip"], ctx)
    bundle = tmp_path / "b.zip"
    assert "README.md" in zipfile.ZipFile(bundle).namelist()
    assert bundle.stat().st_mode & 0o777 == 0o600


def test_blocklist_command(sdk: Client) -> None:
    ctx = Context(client_factory=lambda: sdk)
    assert "example.block.com" in run(["blocklist", "list"], ctx)
    assert "never be captured" in run(["blocklist", "add", "example.com"], ctx)
    assert "example.com                              custom" in run(["blocklist", "list"], ctx)
    assert "removed" in run(["blocklist", "remove", "example.com"], ctx)
    assert "defaults" in run(["blocklist", "reset"], ctx)
