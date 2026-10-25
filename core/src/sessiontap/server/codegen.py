import json
import shlex
from typing import Any
from sessiontap.server.sensitive import is_sensitive_header, mask_body, mask_url

LANGUAGES = ("curl", "python", "javascript")

_SKIP = frozenset({"host", "content-length", "connection", "accept-encoding", "te", "upgrade"})


def _split_headers(headers: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    plain: dict[str, str] = {}
    secret: dict[str, str] = {}
    for name, value in headers.items():
        lname = name.lower()
        if lname.startswith(":") or lname in _SKIP:
            continue
        (secret if is_sensitive_header(lname) else plain)[lname] = value
    return plain, secret


def generate(request: dict[str, Any], lang: str, include_secrets: bool = False) -> str:
    if lang not in LANGUAGES:
        raise ValueError(f"unsupported language {lang!r}; choose one of {', '.join(LANGUAGES)}")
    headers = request.get("request_headers") or {}
    plain, secret = _split_headers(headers)
    url, body = request["url"], request.get("request_body")
    note = ""
    if not include_secrets:
        content_type = next((v for k, v in headers.items() if k.lower() == "content-type"), None)
        masked_url, masked_body = mask_url(url), mask_body(body, content_type)
        if (masked_url, masked_body) != (url, body):
            note = "NOTE: credential-looking fields in the URL/body were masked; fill them in.\n"
            url, body = masked_url, masked_body
    args = (url, request["method"], request["domain"], plain, secret, body, include_secrets)
    if lang == "curl":
        code = _curl(*args)
    elif lang == "python":
        code = _python(*args)
    else:
        return (f"// {note}" if note else "") + _javascript(*args)
    return (f"# {note}" if note else "") + code


def _env_name(header: str) -> str:
    return "ST_" + "".join(ch if ch.isalnum() else "_" for ch in header.upper())


def _curl(
    url: str,
    method: str,
    domain: str,
    plain: dict[str, str],
    secret: dict[str, str],
    body: str | None,
    include_secrets: bool,
) -> str:
    lines: list[str] = []
    if secret and not include_secrets:
        lines.append("# Credentials are read from SessionTap at run time:")
        for name in secret:
            source = (
                f"sessiontap cookie-header {domain}"
                if name == "cookie"
                else f"sessiontap secret {domain} {name}"
            )
            lines.append(f'{_env_name(name)}="$({source})"')
        lines.append("")
    cmd = [f"curl --compressed -X {method} {shlex.quote(url)}"]
    for name, value in plain.items():
        cmd.append(f"-H {shlex.quote(f'{name}: {value}')}")
    for name, value in secret.items():
        if include_secrets:
            cmd.append(f"-H {shlex.quote(f'{name}: {value}')}")
        else:
            cmd.append(f'-H "{name}: ${_env_name(name)}"')
    if body is not None:
        cmd.append(f"--data-raw {shlex.quote(body)}")
    return "\n".join(lines) + " \\\n  ".join(cmd) + "\n"


def _python(
    url: str,
    method: str,
    domain: str,
    plain: dict[str, str],
    secret: dict[str, str],
    body: str | None,
    include_secrets: bool,
) -> str:
    out = ["import sessiontap", ""]
    if include_secrets:
        out[0] = "import httpx"
        out.append("client = httpx.Client()")
        headers = {**plain, **secret}
    else:
        out.append(f"# Your browser's cookies and user agent for {domain}, loaded at run time.")
        out.append(f"client = sessiontap.httpx_client({domain!r})")
        headers = dict(plain)
        headers.pop("cookie", None)
        headers.pop("user-agent", None)
    out.append(f"headers = {_py_dict(headers)}")
    if not include_secrets:
        for name in secret:
            if name != "cookie":
                out.append(f"headers[{name!r}] = sessiontap.secret({domain!r}, {name!r})")
    out.append("")
    call = f"response = client.request({method!r}, {url!r}, headers=headers"
    if body is not None:
        call += f", content={body!r}"
    out.append(call + ")")
    out.append("response.raise_for_status()")
    out.append("print(response.text)")
    return "\n".join(out) + "\n"


def _javascript(
    url: str,
    method: str,
    domain: str,
    plain: dict[str, str],
    secret: dict[str, str],
    body: str | None,
    include_secrets: bool,
) -> str:
    out: list[str] = []
    if include_secrets:
        headers = {**plain, **secret}
        out.append(f"const headers = {json.dumps(headers, indent=2)};")
    else:
        out.append('import { SessionTap } from "sessiontap";')
        out.append("")
        out.append("const tap = new SessionTap();")
        out.append(f"const headers = {json.dumps(plain, indent=2)};")
        for name in secret:
            if name == "cookie":
                out.append(f'headers["cookie"] = await tap.cookieHeader({json.dumps(domain)});')
            else:
                out.append(
                    f"headers[{json.dumps(name)}] = "
                    f"await tap.secret({json.dumps(domain)}, {json.dumps(name)});"
                )
    out.append("")
    opts = [f"method: {json.dumps(method)}", "headers"]
    if body is not None:
        opts.append(f"body: {json.dumps(body)}")
    out.append(f"const response = await fetch({json.dumps(url)}, {{ {', '.join(opts)} }});")
    out.append("console.log(response.status, await response.text());")
    return "\n".join(out) + "\n"


def _py_dict(d: dict[str, str]) -> str:
    if not d:
        return "{}"
    items = ",\n".join(f"    {k!r}: {v!r}" for k, v in d.items())
    return "{\n" + items + ",\n}"
