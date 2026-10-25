import time
from typing import Any
from sessiontap.server import sensitive
from sessiontap.server.vault import Vault

SOON = 24 * 3600


def _state(expires: float | None, now: float) -> str:
    if expires is None:
        return "session"
    if expires <= now:
        return "expired"
    if expires - now < SOON:
        return "expiring"
    return "ok"


def session_health(vault: Vault, domain: str, now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    cookies = vault.cookies_for(domain)
    tokens = list({t["kind"]: t for t in reversed(vault.list_tokens(domain))}.values())[::-1]
    cookie_items = [
        {
            "name": c["name"],
            "domain": c["domain"],
            "expires": c["expires"],
            "state": _state(c["expires"], now),
        }
        for c in cookies
    ]
    token_items = []
    for t in tokens:
        claims = sensitive.jwt_claims(t["value"])
        token_items.append(
            {
                "id": t["id"],
                "kind": t["kind"],
                "jwt": claims is not None,
                "subject": claims.get("sub") if claims else None,
                "issuer": claims.get("iss") if claims else None,
                "expires": t["expires_at"],
                "state": _state(t["expires_at"], now) if claims else "unknown",
                "last_seen": t["last_seen"],
            }
        )
    states = [i["state"] for i in cookie_items] + [
        i["state"] for i in token_items if i["state"] != "unknown"
    ]
    if not cookies and not tokens:
        overall = "empty"
    elif "expired" in states and not any(s in ("ok", "session") for s in states):
        overall = "expired"
    elif "expiring" in states or "expired" in states:
        overall = "warning"
    else:
        overall = "ok"
    future = [e for e in (i["expires"] for i in cookie_items + token_items) if e and e > now]
    domains = {d["domain"]: d for d in vault.list_domains()}
    return {
        "domain": domain,
        "status": overall,
        "next_expiry": min(future) if future else None,
        "last_activity": domains.get(domain, {}).get("last_seen"),
        "cookies": cookie_items,
        "tokens": token_items,
    }
