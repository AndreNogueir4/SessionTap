import json
import time
import sqlite3
import threading
from typing import Any
from pathlib import Path
from sessiontap import secretfile
from contextlib import contextmanager
from collections.abc import Iterable, Iterator
from sessiontap.server.crypto import Cipher, VaultKeyError
from sessiontap.domains import cookie_applies, match_any, matches

DEFAULT_RETENTION_DAYS = 7
_KEY_CHECK = "sessiontap-key-check"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS domains (
    domain     TEXT PRIMARY KEY,
    capture    INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_seen  REAL
);
CREATE TABLE IF NOT EXISTS requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    domain           TEXT NOT NULL,
    host             TEXT NOT NULL,
    method           TEXT NOT NULL,
    path             TEXT NOT NULL,
    url              BLOB NOT NULL,
    status           INTEGER,
    mime_type        TEXT,
    resource_type    TEXT,
    request_headers  BLOB,
    request_body     BLOB,
    response_headers BLOB,
    response_body    BLOB,
    body_truncated   INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    started_at       REAL NOT NULL,
    duration_ms      REAL
);
CREATE INDEX IF NOT EXISTS requests_domain_time ON requests (domain, started_at DESC);
CREATE TABLE IF NOT EXISTS cookies (
    domain        TEXT NOT NULL,
    cookie_domain TEXT NOT NULL,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    value         BLOB NOT NULL,
    secure        INTEGER NOT NULL DEFAULT 0,
    http_only     INTEGER NOT NULL DEFAULT 0,
    same_site     TEXT,
    expires       REAL,
    updated_at    REAL NOT NULL,
    PRIMARY KEY (cookie_domain, name, path)
);
CREATE INDEX IF NOT EXISTS cookies_domain ON cookies (domain);
CREATE TABLE IF NOT EXISTS tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    domain     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    value      BLOB NOT NULL,
    lookup     TEXT NOT NULL,
    source     TEXT,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    expires_at REAL,
    UNIQUE (domain, kind, lookup)
);
CREATE TABLE IF NOT EXISTS storage (
    domain     TEXT NOT NULL,
    origin     TEXT NOT NULL,
    area       TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      BLOB NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (origin, area, key)
);
CREATE TABLE IF NOT EXISTS fingerprints (
    domain     TEXT PRIMARY KEY,
    origin     TEXT NOT NULL,
    data       TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Vault:
    def __init__(self, path: Path, cipher: Cipher) -> None:
        self.path = path
        self.cipher = cipher
        path.parent.mkdir(parents=True, exist_ok=True)
        secretfile.restrict_dir(path.parent)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        for f in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
            secretfile.restrict(f)
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(_SCHEMA)
        self._check_key()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, tuple(params)).fetchall()

    def _check_key(self) -> None:
        row = self._query("SELECT value FROM meta WHERE key = 'key_check'")
        if not row:
            sealed = self.cipher.seal(_KEY_CHECK, "meta.key_check")
            assert sealed is not None
            self.set_meta("key_check", sealed.hex())
            return
        try:
            ok = self.cipher.open(bytes.fromhex(row[0]["value"]), "meta.key_check") == _KEY_CHECK
        except VaultKeyError:
            ok = False
        if not ok:
            raise VaultKeyError(
                "the vault key does not match this vault. If the key was lost, reset with "
                "`sessiontap purge --all`."
            )

    def get_meta(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as db:
            db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @property
    def retention_days(self) -> int:
        value = self.get_meta("retention_days")
        return int(value) if value else DEFAULT_RETENTION_DAYS

    @retention_days.setter
    def retention_days(self, days: int) -> None:
        self.set_meta("retention_days", str(days))

    def set_capture(self, domain: str, enabled: bool) -> None:
        now = time.time()
        with self._tx() as db:
            db.execute(
                "INSERT INTO domains (domain, capture, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(domain) DO UPDATE SET capture = excluded.capture",
                (domain, int(enabled), now),
            )

    def capture_domains(self) -> list[str]:
        return [r["domain"] for r in self._query("SELECT domain FROM domains WHERE capture = 1")]

    def capture_domain_for(self, host: str) -> str | None:
        return match_any(host, self.capture_domains())

    def known_domain_for(self, host: str) -> str | None:
        return match_any(host, [r["domain"] for r in self._query("SELECT domain FROM domains")])

    def _touch(self, db: sqlite3.Connection, domain: str, now: float) -> None:
        db.execute(
            "INSERT INTO domains (domain, capture, created_at, last_seen) VALUES (?, 0, ?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen = excluded.last_seen",
            (domain, now, now),
        )

    def list_domains(self) -> list[dict[str, Any]]:
        rows = self._query(
            """
            SELECT d.domain, d.capture, d.created_at, d.last_seen,
                   (SELECT COUNT(*) FROM requests r WHERE r.domain = d.domain) AS requests,
                   (SELECT COUNT(*) FROM cookies c WHERE c.domain = d.domain) AS cookies,
                   (SELECT COUNT(*) FROM tokens t WHERE t.domain = d.domain) AS tokens,
                   (SELECT COUNT(*) FROM storage s WHERE s.domain = d.domain) AS storage
            FROM domains d ORDER BY COALESCE(d.last_seen, d.created_at) DESC
            """
        )
        return [{**dict(r), "capture": bool(r["capture"])} for r in rows]

    def delete_domain(self, domain: str) -> None:
        with self._tx() as db:
            for table in ("requests", "cookies", "tokens", "storage", "fingerprints", "domains"):
                db.execute(f"DELETE FROM {table} WHERE domain = ?", (domain,))  # noqa: S608

    def add_request(self, domain: str, host: str, path: str, data: dict[str, Any]) -> int:
        c = self.cipher
        now = time.time()
        with self._tx() as db:
            self._touch(db, domain, now)
            cur = db.execute(
                """
                INSERT INTO requests (domain, host, method, path, url, status, mime_type,
                    resource_type, request_headers, request_body, response_headers,
                    response_body, body_truncated, error, started_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    domain,
                    host,
                    data["method"],
                    path,
                    c.seal(data["url"], "requests.url"),
                    data.get("status"),
                    data.get("mime_type"),
                    data.get("resource_type"),
                    c.seal(json.dumps(data.get("request_headers", {})), "requests.request_headers"),
                    c.seal(data.get("request_body"), "requests.request_body"),
                    c.seal(
                        json.dumps(data.get("response_headers", {})), "requests.response_headers"
                    ),
                    c.seal(data.get("response_body"), "requests.response_body"),
                    int(bool(data.get("body_truncated"))),
                    data.get("error"),
                    data.get("started_at") or now,
                    data.get("duration_ms"),
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    def list_requests(
        self, domain: str | None = None, q: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, domain, host, method, path, status, mime_type, resource_type, "
            "started_at, duration_ms, error FROM requests WHERE 1 = 1"
        )
        params: list[Any] = []
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if q:
            sql += " AND (path LIKE ? ESCAPE '\\' OR host LIKE ? ESCAPE '\\')"
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [like, like]
        sql += " ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [dict(r) for r in self._query(sql, params)]

    def get_request(self, request_id: int) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM requests WHERE id = ?", (request_id,))
        if not rows:
            return None
        r = dict(rows[0])
        c = self.cipher
        r["url"] = c.open(r["url"], "requests.url")
        r["request_headers"] = json.loads(
            c.open(r["request_headers"], "requests.request_headers") or "{}"
        )
        r["response_headers"] = json.loads(
            c.open(r["response_headers"], "requests.response_headers") or "{}"
        )
        r["request_body"] = c.open(r["request_body"], "requests.request_body")
        r["response_body"] = c.open(r["response_body"], "requests.response_body")
        r["body_truncated"] = bool(r["body_truncated"])
        return r

    def iter_requests(self, domain: str, api_only: bool = False) -> Iterator[dict[str, Any]]:
        sql = "SELECT id FROM requests WHERE domain = ?"
        if api_only:
            sql += " AND (resource_type IS NULL OR resource_type != 'Document')"
        sql += " ORDER BY started_at, id"
        ids = [r["id"] for r in self._query(sql, (domain,))]
        for request_id in ids:
            r = self.get_request(request_id)
            if r is not None:
                yield r

    def upsert_cookie(self, domain: str, cookie: dict[str, Any]) -> None:
        now = time.time()
        with self._tx() as db:
            self._touch(db, domain, now)
            self._upsert_cookie(db, domain, cookie, now)

    def _upsert_cookie(
        self, db: sqlite3.Connection, domain: str, cookie: dict[str, Any], now: float
    ) -> None:
        db.execute(
            """
            INSERT INTO cookies (domain, cookie_domain, name, path, value, secure, http_only,
                                 same_site, expires, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cookie_domain, name, path) DO UPDATE SET
                domain = excluded.domain, value = excluded.value, secure = excluded.secure,
                http_only = excluded.http_only, same_site = excluded.same_site,
                expires = excluded.expires, updated_at = excluded.updated_at
            """,
            (
                domain,
                cookie["domain"],
                cookie["name"],
                cookie.get("path") or "/",
                self.cipher.seal(cookie["value"], "cookies.value"),
                int(bool(cookie.get("secure"))),
                int(bool(cookie.get("http_only"))),
                cookie.get("same_site"),
                cookie.get("expires"),
                now,
            ),
        )

    def remove_cookie(self, cookie_domain: str, name: str, path: str) -> None:
        with self._tx() as db:
            db.execute(
                "DELETE FROM cookies WHERE cookie_domain = ? AND name = ? AND path = ?",
                (cookie_domain, name, path or "/"),
            )

    def replace_cookies(self, domain: str, cookies: list[dict[str, Any]]) -> None:
        now = time.time()
        with self._tx() as db:
            self._touch(db, domain, now)
            db.execute("DELETE FROM cookies WHERE domain = ?", (domain,))
            for cookie in cookies:
                self._upsert_cookie(db, domain, cookie, now)

    def cookies_for(self, host: str, subdomains: bool = True) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM cookies ORDER BY cookie_domain, name")
        out = []
        for r in rows:
            cd = r["cookie_domain"].lstrip(".")
            if cookie_applies(r["cookie_domain"], host) or (subdomains and matches(cd, host)):
                out.append(
                    {
                        "name": r["name"],
                        "value": self.cipher.open(r["value"], "cookies.value"),
                        "domain": r["cookie_domain"],
                        "path": r["path"],
                        "secure": bool(r["secure"]),
                        "http_only": bool(r["http_only"]),
                        "same_site": r["same_site"],
                        "expires": r["expires"],
                    }
                )
        return out

    def upsert_token(
        self,
        domain: str,
        kind: str,
        value: str,
        source: str | None = None,
        expires_at: float | None = None,
    ) -> None:
        now = time.time()
        lookup = self.cipher.lookup_hash(value)
        with self._tx() as db:
            self._touch(db, domain, now)
            db.execute(
                """
                INSERT INTO tokens (domain, kind, value, lookup, source, first_seen, last_seen,
                                    expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, kind, lookup) DO UPDATE SET
                    last_seen = excluded.last_seen, source = excluded.source
                """,
                (
                    domain,
                    kind,
                    self.cipher.seal(value, "tokens.value"),
                    lookup,
                    source,
                    now,
                    now,
                    expires_at,
                ),
            )

    def list_tokens(self, domain: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tokens"
        params: tuple[Any, ...] = ()
        if domain:
            sql += " WHERE domain = ?"
            params = (domain,)
        sql += " ORDER BY last_seen DESC"
        return [
            {
                "id": r["id"],
                "domain": r["domain"],
                "kind": r["kind"],
                "value": self.cipher.open(r["value"], "tokens.value"),
                "source": r["source"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "expires_at": r["expires_at"],
            }
            for r in self._query(sql, params)
        ]

    def latest_token(self, domain: str, kind: str) -> str | None:
        rows = self._query(
            "SELECT value FROM tokens WHERE domain = ? AND kind = ? "
            "ORDER BY last_seen DESC LIMIT 1",
            (domain, kind),
        )
        return self.cipher.open(rows[0]["value"], "tokens.value") if rows else None

    def replace_storage(self, domain: str, origin: str, area: str, items: dict[str, str]) -> None:
        now = time.time()
        with self._tx() as db:
            self._touch(db, domain, now)
            db.execute("DELETE FROM storage WHERE origin = ? AND area = ?", (origin, area))
            for key, value in items.items():
                db.execute(
                    "INSERT INTO storage (domain, origin, area, key, value, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (domain, origin, area, key, self.cipher.seal(value, "storage.value"), now),
                )

    def storage_for(self, domain: str) -> dict[str, dict[str, dict[str, str]]]:
        out: dict[str, dict[str, dict[str, str]]] = {}
        for r in self._query("SELECT * FROM storage WHERE domain = ?", (domain,)):
            area = out.setdefault(r["origin"], {"local": {}, "session": {}})
            area.setdefault(r["area"], {})[r["key"]] = (
                self.cipher.open(r["value"], "storage.value") or ""
            )
        return out

    def set_fingerprint(self, domain: str, origin: str, data: dict[str, Any]) -> None:
        now = time.time()
        with self._tx() as db:
            self._touch(db, domain, now)
            db.execute(
                "INSERT INTO fingerprints (domain, origin, data, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(domain) DO UPDATE SET origin = excluded.origin, data = excluded.data, "
                "updated_at = excluded.updated_at",
                (domain, origin, json.dumps(data), now),
            )

    def fingerprint_for(self, domain: str) -> dict[str, Any] | None:
        rows = self._query("SELECT data FROM fingerprints WHERE domain = ?", (domain,))
        return json.loads(rows[0]["data"]) if rows else None

    def apply_retention(self, now: float | None = None) -> dict[str, int]:
        now = now or time.time()
        cutoff = now - self.retention_days * 86400
        with self._tx() as db:
            requests = db.execute("DELETE FROM requests WHERE started_at < ?", (cutoff,)).rowcount
            cookies = db.execute(
                "DELETE FROM cookies WHERE expires IS NOT NULL AND expires < ?", (now,)
            ).rowcount
            tokens = db.execute(
                "DELETE FROM tokens WHERE (expires_at IS NOT NULL AND expires_at < ?) "
                "OR last_seen < ?",
                (now - 86400, now - max(self.retention_days, 30) * 86400),
            ).rowcount
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"requests": requests, "cookies": cookies, "tokens": tokens}

    def stats(self) -> dict[str, int]:
        out = {}
        for table in ("domains", "requests", "cookies", "tokens", "storage"):
            out[table] = self._query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]  # noqa: S608
        return out

    def size_bytes(self) -> int:
        return sum(
            p.stat().st_size
            for p in (self.path, self.path.with_name(self.path.name + "-wal"))
            if p.exists()
        )
