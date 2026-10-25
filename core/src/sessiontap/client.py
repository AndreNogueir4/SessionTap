import os
import httpx
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Self, TYPE_CHECKING
from sessiontap import config as cfg, secretfile

if TYPE_CHECKING:
    import requests as _requests


class SessionTapError(RuntimeError):
    pass


@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    http_only: bool = False
    same_site: str | None = None
    expires: float | None = None


@dataclass
class Session:
    domain: str
    cookies: list[Cookie]
    user_agent: str | None = None
    storage: dict[str, dict[str, dict[str, str]]] = field(default_factory=dict)
    fingerprint: dict[str, Any] | None = None

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.cookies)

    def local_storage(self, origin: str | None = None) -> dict[str, str]:
        return self.storage.get(origin or f"https://{self.domain}", {}).get("local", {})

    def headers(self) -> dict[str, str]:
        return {"user-agent": self.user_agent} if self.user_agent else {}


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 10.0,
        http: httpx.Client | None = None,
    ) -> None:
        if http is not None:
            self._http = http
            return
        if base_url is None:
            base_url = f"http://127.0.0.1:{cfg.load_config().port}"
        if token is None:
            token = secretfile.read_secret(cfg.token_path())
        if not token:
            raise SessionTapError(
                f"no SessionTap token found at {cfg.token_path()}; is the daemon installed and "
                "started (`sessiontap start`)?"
            )
        self._http = httpx.Client(
            base_url=base_url,
            headers={"authorization": f"Bearer {token}"},
            timeout=timeout,
            trust_env=False,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def api(self, method: str, path: str, body: Any = None, **params: Any) -> Any:
        try:
            response = self._http.request(method, path, json=body, params=params or None)
        except httpx.ConnectError as e:
            raise SessionTapError("SessionTap daemon is not running (`sessiontap start`)") from e
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise SessionTapError(f"{response.status_code}: {detail}")
        if "json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    def download(self, path: str, dest: Path) -> int:
        size = 0
        try:
            with self._http.stream("GET", path, timeout=None) as response:
                if response.status_code >= 400:
                    raise SessionTapError(f"{response.status_code}: {response.read().decode()}")
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as f:
                    for chunk in response.iter_bytes():
                        size += f.write(chunk)
        except httpx.ConnectError as e:
            raise SessionTapError("SessionTap daemon is not running (`sessiontap start`)") from e
        return size

    def _get(self, path: str, **params: Any) -> Any:
        return self.api("GET", path, **params)

    def status(self) -> dict[str, Any]:
        return dict(self._get("/v1/status"))

    def domains(self) -> list[dict[str, Any]]:
        return list(self._get("/v1/domains"))

    def health(self, domain: str) -> dict[str, Any]:
        return dict(self._get(f"/v1/sessions/{domain}/health"))

    def secret(self, domain: str, name: str) -> str:
        return str(self._get(f"/v1/sessions/{domain}/secret", name=name)["value"])

    def session(self, domain: str, subdomains: bool = True) -> Session:
        data = self._get(f"/v1/sessions/{domain}", subdomains=str(subdomains).lower())
        return Session(
            domain=data["domain"],
            cookies=[Cookie(**c) for c in data["cookies"]],
            user_agent=data.get("user_agent"),
            storage=data.get("storage") or {},
            fingerprint=data.get("fingerprint"),
        )

    def cookie_header(self, domain: str) -> str:
        return self.session(domain, subdomains=False).cookie_header()

    def httpx_client(self, domain: str, **kwargs: Any) -> httpx.Client:
        s = self.session(domain)
        jar = httpx.Cookies()
        for c in s.cookies:
            jar.set(c.name, c.value, domain=c.domain, path=c.path)
        headers = {**s.headers(), **kwargs.pop("headers", {})}
        return httpx.Client(cookies=jar, headers=headers, follow_redirects=True, **kwargs)

    def requests_session(self, domain: str) -> "_requests.Session":
        try:
            import requests
        except ImportError as e:
            raise SessionTapError("pip install requests") from e
        s = self.session(domain)
        session = requests.Session()
        for c in s.cookies:
            session.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
        session.headers.update(s.headers())
        return session

    def curl_cffi_session(self, domain: str, impersonate: str = "chrome") -> Any:
        try:
            from curl_cffi import requests as cffi
        except ImportError as e:
            raise SessionTapError("pip install curl_cffi") from e
        s = self.session(domain)
        session = cffi.Session(impersonate=impersonate)
        for c in s.cookies:
            session.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
        session.headers.update(s.headers())
        return session

    def playwright_cookies(self, domain: str) -> list[dict[str, Any]]:
        same_site = {"lax": "Lax", "strict": "Strict", "no_restriction": "None", "none": "None"}
        out = []
        for c in self.session(domain).cookies:
            cookie: dict[str, Any] = {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "secure": c.secure,
                "httpOnly": c.http_only,
            }
            if c.expires:
                cookie["expires"] = c.expires
            if c.same_site and c.same_site.lower() in same_site:
                cookie["sameSite"] = same_site[c.same_site.lower()]
            out.append(cookie)
        return out


_default: Client | None = None


def default_client() -> Client:
    global _default
    if _default is None:
        _default = Client()
    return _default


def session(domain: str, subdomains: bool = True) -> Session:
    return default_client().session(domain, subdomains)


def secret(domain: str, name: str) -> str:
    return default_client().secret(domain, name)


def cookie_header(domain: str) -> str:
    return default_client().cookie_header(domain)


def httpx_client(domain: str, **kwargs: Any) -> httpx.Client:
    return default_client().httpx_client(domain, **kwargs)


def requests_session(domain: str) -> "_requests.Session":
    return default_client().requests_session(domain)


def curl_cffi_session(domain: str, impersonate: str = "chrome") -> Any:
    return default_client().curl_cffi_session(domain, impersonate)


def playwright_cookies(domain: str) -> list[dict[str, Any]]:
    return default_client().playwright_cookies(domain)
