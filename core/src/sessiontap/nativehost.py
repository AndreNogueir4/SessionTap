import sys
import json
import struct
import urllib.error
import urllib.request
from typing import Any, IO
from urllib.parse import quote
from sessiontap import config as cfg, secretfile

MAX_IN = 16 * 1024 * 1024
MAX_OUT = 1024 * 1024
TIMEOUT = 10
INGEST_TIMEOUT = 120
MAX_UPLOAD = 256 * 1024 * 1024
MAX_UPLOADS = 4

ROUTES = frozenset(
    {"hello", "state", "ingest", "ingest_part", "set_capture", "login_code", "site_summary"}
)


class ProtocolError(Exception):
    pass


def read_message(stream: IO[bytes]) -> dict[str, Any] | None:
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ProtocolError("truncated length header")
    (length,) = struct.unpack("<I", header)
    if length == 0 or length > MAX_IN:
        raise ProtocolError(f"invalid message length {length}")
    payload = stream.read(length)
    if len(payload) != length:
        raise ProtocolError("truncated message")
    message = json.loads(payload)
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    return message


def write_message(stream: IO[bytes], message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode()
    if len(payload) > MAX_OUT:
        payload = json.dumps(
            {"id": message.get("id"), "ok": False, "error": "reply_too_large"}
        ).encode()
    stream.write(struct.pack("<I", len(payload)) + payload)
    stream.flush()


class Daemon:
    def __init__(self, port: int, token: str | None) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, method: str, path: str, body: Any = None, raw: bytes | None = None) -> Any:
        if not self.token:
            raise ConnectionError("no_token")
        data = raw if raw is not None else None if body is None else json.dumps(body).encode()
        timeout = INGEST_TIMEOUT if path == "/v1/ingest" else TIMEOUT
        req = urllib.request.Request(  # noqa: S310
            self.base + path,
            data=data,
            method=method,
            headers={"authorization": f"Bearer {self.token}", "content-type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail", str(e))
            except ValueError:
                detail = str(e)
            raise RuntimeError(detail) from e
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionError("daemon_unreachable") from e


class Uploads:
    def __init__(self) -> None:
        self.parts: dict[str, list[str]] = {}
        self.sizes: dict[str, int] = {}

    def add(self, upload: Any, seq: Any, data: Any, last: Any) -> bytes | None:
        if (
            not isinstance(upload, str)
            or not 0 < len(upload) <= 64
            or not isinstance(seq, int)
            or not isinstance(data, str)
            or not isinstance(last, bool)
        ):
            raise ValueError("invalid_arguments")
        parts = self.parts.get(upload)
        if seq == 0:
            if parts is None and len(self.parts) >= MAX_UPLOADS:
                self.drop(next(iter(self.parts)))
            parts = self.parts[upload] = []
            self.sizes[upload] = 0
        if parts is None or seq != len(parts):
            self.drop(upload)
            raise ValueError("out_of_order")
        self.sizes[upload] += len(data)
        if self.sizes[upload] > MAX_UPLOAD:
            self.drop(upload)
            raise ValueError("upload_too_large")
        parts.append(data)
        if not last:
            return None
        self.drop(upload)
        return "".join(parts).encode("utf-8", errors="replace")

    def drop(self, upload: str) -> None:
        self.parts.pop(upload, None)
        self.sizes.pop(upload, None)


def handle(
    message: dict[str, Any], daemon: Daemon, uploads: Uploads | None = None
) -> dict[str, Any]:
    msg_id = message.get("id")
    if not isinstance(msg_id, int):
        return {"id": None, "ok": False, "error": "missing_id"}
    kind = message.get("type")
    if kind not in ROUTES:
        return {"id": msg_id, "ok": False, "error": "unknown_type"}
    try:
        if kind in ("hello", "state"):
            data = daemon.call("GET", "/v1/capture-state")
        elif kind == "login_code":
            data = daemon.call("POST", "/v1/auth/login-code")
            data = {"code": data["code"], "port": daemon.port}
        elif kind == "site_summary":
            domain = message.get("domain")
            if not isinstance(domain, str):
                return {"id": msg_id, "ok": False, "error": "invalid_arguments"}
            data = daemon.call("GET", f"/v1/domains/{quote(domain, safe='')}/summary")
        elif kind == "ingest":
            events = message.get("events")
            if not isinstance(events, list):
                return {"id": msg_id, "ok": False, "error": "events_must_be_list"}
            data = daemon.call("POST", "/v1/ingest", {"events": events})
        elif kind == "ingest_part":
            uploads = uploads if uploads is not None else Uploads()
            try:
                payload = uploads.add(
                    message.get("upload"),
                    message.get("seq"),
                    message.get("data"),
                    message.get("last"),
                )
            except ValueError as e:
                return {"id": msg_id, "ok": False, "error": str(e)}
            if payload is None:
                return {"id": msg_id, "ok": True, "data": {"partial": True}}
            data = daemon.call("POST", "/v1/ingest", raw=payload)
        else:
            domain = message.get("domain")
            enabled = message.get("enabled")
            if not isinstance(domain, str) or not isinstance(enabled, bool):
                return {"id": msg_id, "ok": False, "error": "invalid_arguments"}
            data = daemon.call(
                "PUT",
                f"/v1/domains/{quote(domain, safe='')}",
                {"capture": enabled},
            )
    except ConnectionError as e:
        return {"id": msg_id, "ok": False, "error": str(e)}
    except RuntimeError as e:
        return {"id": msg_id, "ok": False, "error": "rejected", "detail": str(e)[:500]}
    return {"id": msg_id, "ok": True, "data": data}


def main() -> None:
    config = cfg.load_config()
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    uploads = Uploads()
    while True:
        try:
            message = read_message(stdin)
        except (ProtocolError, ValueError) as e:
            print(f"sessiontap-host: {e}", file=sys.stderr)
            return
        if message is None:
            return
        daemon = Daemon(config.port, secretfile.read_secret(cfg.token_path()))
        write_message(stdout, handle(message, daemon, uploads))


if __name__ == "__main__":
    main()
