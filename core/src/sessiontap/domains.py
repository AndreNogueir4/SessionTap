import re
from urllib.parse import urlsplit
from collections.abc import Iterable

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class InvalidDomain(ValueError):
    pass


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain or len(domain) > 253:
        raise InvalidDomain(f"invalid domain: {value!r}")
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as e:
        raise InvalidDomain(f"invalid domain: {value!r}") from e
    labels = domain.split(".")
    if domain != "localhost" and len(labels) < 2:
        raise InvalidDomain(f"invalid domain (needs a dot): {value!r}")
    if not all(_LABEL.match(label) for label in labels):
        raise InvalidDomain(f"invalid domain: {value!r}")
    return domain


def host_of(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def match_any(host: str, domains: Iterable[str]) -> str | None:
    best: str | None = None
    for d in domains:
        if matches(host, d) and (best is None or len(d) > len(best)):
            best = d
    return best


def cookie_applies(cookie_domain: str, host: str) -> bool:
    return matches(host, cookie_domain.lstrip(".").lower())
