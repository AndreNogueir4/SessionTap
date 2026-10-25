import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { SessionTap, SessionTapError } from "../dist/index.js";

const SESSION = {
  domain: "example.com",
  cookies: [
    { name: "sid", value: "abc", domain: ".example.com", path: "/", secure: true, http_only: true, same_site: "lax", expires: 2e9 },
    { name: "pref", value: "1", domain: "example.com", path: "/", secure: false, http_only: false, same_site: null, expires: null },
  ],
  user_agent: "UA/1",
  storage: {},
  fingerprint: null,
};

function daemon(token) {
  const seen = [];
  const server = createServer((req, res) => {
    seen.push({ url: req.url, auth: req.headers.authorization });
    if (req.headers.authorization !== `Bearer ${token}`) {
      res.writeHead(401, { "content-type": "application/json" });
      return res.end(JSON.stringify({ detail: "missing or invalid token" }));
    }
    const url = new URL(req.url, "http://x");
    res.writeHead(200, { "content-type": "application/json" });
    if (url.pathname.endsWith("/secret")) return res.end(JSON.stringify({ name: "authorization", value: "Bearer T" }));
    res.end(JSON.stringify(SESSION));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, seen })));
}

test("reads the token from the home directory and authenticates", async () => {
  const home = mkdtempSync(join(tmpdir(), "st-"));
  writeFileSync(join(home, "token"), "tok\n");
  const { server, seen } = await daemon("tok");
  const tap = new SessionTap({ home, baseUrl: `http://127.0.0.1:${server.address().port}` });
  assert.equal(await tap.cookieHeader("example.com"), "sid=abc; pref=1");
  assert.deepEqual(await tap.headers("example.com"), { cookie: "sid=abc; pref=1", "user-agent": "UA/1" });
  assert.equal(await tap.secret("example.com", "authorization"), "Bearer T");
  assert.equal(seen[0].auth, "Bearer tok");
  server.close();
});

test("converts cookies for Playwright", async () => {
  const { server } = await daemon("tok");
  const tap = new SessionTap({ token: "tok", baseUrl: `http://127.0.0.1:${server.address().port}` });
  const [sid, pref] = await tap.playwrightCookies("example.com");
  assert.deepEqual(sid, { name: "sid", value: "abc", domain: ".example.com", path: "/", httpOnly: true, secure: true, expires: 2e9, sameSite: "Lax" });
  assert.equal(pref.expires, undefined);
  server.close();
});

test("reports a wrong token clearly", async () => {
  const { server } = await daemon("tok");
  const tap = new SessionTap({ token: "nope", baseUrl: `http://127.0.0.1:${server.address().port}` });
  await assert.rejects(tap.session("example.com"), (e) => e instanceof SessionTapError && /401/.test(e.message));
  server.close();
});

test("refuses non-local daemons so the token never leaves the machine", () => {
  assert.throws(() => new SessionTap({ token: "t", baseUrl: "https://evil.example" }), SessionTapError);
});

test("explains a missing token", () => {
  const home = mkdtempSync(join(tmpdir(), "st-"));
  assert.throws(() => new SessionTap({ home }), /No SessionTap token/);
});
