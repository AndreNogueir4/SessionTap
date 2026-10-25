import json
from sessiontap.config import Config
from sessiontap.server.vault import Vault
from sessiontap.domains import match_any, normalize_domain

MAX_BLOCKLIST = 1000


class PolicyLocked(Exception):
    pass


class Policy:
    def __init__(self, vault: Vault, config: Config) -> None:
        self.vault = vault
        self.config = config
        self._blocklist: tuple[str, ...] | None = None

    @property
    def locked(self) -> bool:
        return self.config.capture_locked

    @property
    def defaults(self) -> tuple[str, ...]:
        return self.config.blocklist

    @property
    def blocklist(self) -> tuple[str, ...]:
        if self._blocklist is None:
            stored = None if self.locked else self.vault.get_meta("blocklist")
            self._blocklist = tuple(json.loads(stored)) if stored else self.defaults
        return self._blocklist

    @property
    def customized(self) -> bool:
        return set(self.blocklist) != set(self.defaults)

    def blocks(self, host: str) -> bool:
        return match_any(host, self.blocklist) is not None

    def block(self, domain: str) -> str:
        domain = normalize_domain(domain)
        if domain not in self.blocklist:
            if len(self.blocklist) >= MAX_BLOCKLIST:
                raise ValueError(f"the blocklist is limited to {MAX_BLOCKLIST} entries")
            self._save((*self.blocklist, domain))
        return domain

    def unblock(self, domain: str) -> str:
        domain = normalize_domain(domain)
        self._save(tuple(d for d in self.blocklist if d != domain))
        return domain

    def reset_blocklist(self) -> None:
        self._save(self.defaults)

    @property
    def capture_html(self) -> bool:
        stored = None if self.locked else self.vault.get_meta("capture_html")
        return stored == "1" if stored is not None else self.config.capture_html

    @property
    def max_body_kb(self) -> int:
        stored = None if self.locked else self.vault.get_meta("max_body_kb")
        return int(stored) if stored is not None else self.config.max_body_kb

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_kb * 1024

    def update(self, capture_html: bool | None = None, max_body_kb: int | None = None) -> None:
        if capture_html is None and max_body_kb is None:
            return
        self._check()
        if capture_html is not None:
            self.vault.set_meta("capture_html", "1" if capture_html else "0")
        if max_body_kb is not None:
            self.vault.set_meta("max_body_kb", str(max_body_kb))

    def _save(self, domains: tuple[str, ...]) -> None:
        self._check()
        self.vault.set_meta("blocklist", json.dumps(sorted(set(domains))))
        self._blocklist = None

    def _check(self) -> None:
        if self.locked:
            raise PolicyLocked(
                "capture settings are managed by config.toml ([capture] locked = true)"
            )
