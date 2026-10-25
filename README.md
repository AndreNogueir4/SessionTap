<p align="center">
  <img src="extension/static/icons/icon128.png" width="88" alt="SessionTap" />
</p>

<h1 align="center">SessionTap</h1>

<p align="center">
  <b>Hand the session you already have in your browser to your own scripts.</b><br/>
  Locally, opt-in, encrypted.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-0f766e" />
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue" />
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3776ab" />
  <img alt="Browsers" src="https://img.shields.io/badge/browsers-Chrome%20%C2%B7%20Brave%20%C2%B7%20Edge%20%C2%B7%20Firefox-555" />
  <img alt="Platforms" src="https://img.shields.io/badge/os-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-555" />
</p>

<p align="center">
  <b>English</b> · <a href="README.pt-BR.md">Português (Brasil)</a>
</p>

<p align="center">
  <a href="#-install">Install</a> ·
  <a href="#-usage">Usage</a> ·
  <a href="#-exports-for-ai-agents">AI exports</a> ·
  <a href="#%EF%B8%8F-configuration">Configuration</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#%EF%B8%8F-security">Security</a>
</p>

---

Automation tools spend most of their effort *imitating* a logged-in human: scripted
logins, CAPTCHAs, expiring tokens, guessed headers. **SessionTap skips all of that.**
You log in normally while SessionTap records that tab, and your Python, Node.js or
shell scripts reuse your real cookies, tokens and user agent. It also shows every API
call the site makes, writes code for them and exports everything an AI agent needs to
build the automation for you.

```python
import sessiontap

client = sessiontap.httpx_client("example.com")   # your real session, loaded at run time
print(client.get("https://example.com/api/me").json())
```

## ✨ Features

| | |
|---|---|
| 🔒 **Secure by default** | Loopback-only API with a token, DNS rebinding and CSRF protection, an encrypted vault (AES-256-GCM, key in your OS keyring) and secrets masked everywhere unless you ask to see them. |
| ✋ **Opt-in per tab** | Nothing is recorded until you click **Record this tab**. The recording follows logins and redirects across domains until you stop it. |
| 🚫 **Your blocklist** | Sites that can never be captured, editable from the dashboard and lockable for a whole company. |
| 🧩 **Browser extension** | Chrome, Brave, Edge and Firefox. No telemetry, no remote code, no page modification. |
| 🐍 **Python and JS SDKs** | `httpx`, `requests`, `curl_cffi`, Playwright and Puppeteer helpers. |
| 🧪 **Code generator** | curl, Python and JavaScript for any captured request. The code loads secrets at run time, so it is safe to share. |
| 🩺 **Session health** | Cookie and JWT expiry, before your script fails. |
| 📜 **OpenAPI export** | Inferred from real traffic, with real (masked) examples. |
| 📦 **AI bundle** | A .zip with every request, response and full HTML page in order, so an agent can automate complex sites. |
| 🤖 **MCP server** | AI agents study the API and write the script without ever seeing a secret. |
| 🔐 **Encrypted export/import** | Move a session to another machine with a passphrase. |
| 🌐 **English and Portuguese** | In the extension and the dashboard. |

## 🚀 Install

SessionTap runs straight from this repository. Nothing is published to PyPI or npm.

**Requirements:** Git, [Node.js](https://nodejs.org) 20+ and [uv](https://docs.astral.sh/uv/)
(uv installs Python 3.11+ for you if needed).

**1. Clone and build**

```bash
git clone https://github.com/AndreNogueir4/SessionTap.git
cd SessionTap
npm ci && npm run build            # extension, dashboard and JS SDK
uv tool install "./core[server]"   # puts `sessiontap` and `sessiontap-host` on your PATH
```

If the shell can't find `sessiontap`, run `uv tool update-shell` and open a new terminal.

**2. Start the daemon**

```bash
sessiontap install-host      # lets the extension talk to SessionTap (Chrome, Chromium, Brave, Edge, Firefox)
sessiontap start --detach    # http://127.0.0.1:8711, loopback only
```

Use `sessiontap install-host --browser brave` to register a single browser.

**3. Load the extension**

- **Chrome / Brave / Edge:** `chrome://extensions` → *Developer mode* → **Load unpacked** →
  `extension/dist/chromium`
- **Firefox:** `about:debugging` → *This Firefox* → **Load Temporary Add-on** →
  `extension/dist/firefox/manifest.json`

The popup should say **Connected**. The extension follows your browser's language.

**4. Block the sites you never want captured**

> [!WARNING]
> The blocklist ships with only an example (`example.block.com`). SessionTap does **not**
> block mail, banks, identity providers or password managers on its own: if a recorded tab
> passes through one of them (a "Sign in with Google" redirect, for example), it is
> captured. Add them before your first recording:
>
> ```bash
> sessiontap blocklist add mail.google.com
> sessiontap blocklist add accounts.google.com
> sessiontap blocklist add login.microsoftonline.com
> ```
>
> Or use dashboard → **Settings** → **Blocklist**, where you can also paste a URL. Add your
> bank, payment providers and your company's internal tools too.

## 🧭 Usage

### Record a tab

Open the site, click the SessionTap icon → **Record this tab**, then log in and browse as
usual. The icon shows **REC** and the popup shows live counts: requests, cookies, tokens,
storage values and every site the recording added.

The recording follows the tab: subdomains, a login on another domain (SSO, OAuth
redirects) and API calls that carry an `Authorization` header are added automatically,
so a whole flow lands in the vault. Ads and trackers in iframes are not. Press **Stop
recording** on any page of that tab, or close the tab, to stop.

### Use the session

**Python**: install the SDK into the project where your scripts live, pointing at your clone:

```bash
uv add /path/to/SessionTap/core        # or: pip install /path/to/SessionTap/core
```

```python
import sessiontap

client = sessiontap.httpx_client("example.com")                  # cookies + user agent
session = sessiontap.requests_session("example.com")             # needs `requests`
session = sessiontap.curl_cffi_session("example.com", "chrome")  # also matches browser TLS

s = sessiontap.session("example.com")
s.cookies, s.user_agent, s.local_storage(), s.cookie_header()
token = sessiontap.secret("example.com", "authorization")        # latest captured header value

context.add_cookies(sessiontap.playwright_cookies("example.com"))  # Playwright
```

**Node.js**: after `npm run build` in the clone, install the SDK into your project:

```bash
npm install /path/to/SessionTap/sdk/js
```

```js
import { SessionTap } from "sessiontap";

const tap = new SessionTap();   // reads the local token, no configuration needed
const res = await fetch("https://example.com/api/me", { headers: await tap.headers("example.com") });

await context.addCookies(await tap.playwrightCookies("example.com"));   // Playwright
await page.setCookie(...(await tap.puppeteerCookies("example.com")));   // Puppeteer
const auth = await tap.secret("example.com", "authorization");
```

**Shell**

```bash
curl -H "Cookie: $(sessiontap cookie-header example.com)" https://example.com/api/me
curl -H "Authorization: $(sessiontap secret example.com authorization)" https://api.example.com/me
```

Both SDKs read the token from the SessionTap home directory and refuse to talk to anything
other than `127.0.0.1`.

### Dashboard

```bash
sessiontap open
```

It opens already signed in and shows the captured sites, every request with headers and
bodies, the session (cookies, tokens, storage) with reveal and copy, a live feed, session
health, the API view with exports, and settings. Every request has a **Code** panel that
writes curl, Python or JavaScript for it. By default the code has no secrets and loads them
through the SDK at run time.

<details>
<summary><b>All CLI commands</b></summary>

| Command | What it does |
|---|---|
| `sessiontap start [--detach]` · `stop` · `status` | Run, stop and inspect the daemon |
| `sessiontap open` | Open the dashboard, already signed in |
| `sessiontap token` | Print the token file path, the token, or rotate it |
| `sessiontap install-host` · `uninstall-host` | Register or remove the native host for your browsers |
| `sessiontap capture list\|allow\|deny` | List captured sites, or turn capture on or off for one |
| `sessiontap blocklist list\|add\|remove\|reset` | Manage the sites that can never be captured |
| `sessiontap cookie-header <domain>` | Print the `Cookie` header for a site |
| `sessiontap secret <domain> <header>` | Print the latest captured value of a credential header |
| `sessiontap openapi <domain>` | Write the inferred OpenAPI description |
| `sessiontap bundle <domain>` | Write the AI bundle (.zip) |
| `sessiontap export` · `import` | Encrypted, passphrase-protected session file |
| `sessiontap purge --domain <d>` · `--all` | Delete a site's data, or the whole vault and its key |
| `sessiontap mcp` | Run the MCP server (stdio) for AI agents |

</details>

## 🤖 Exports for AI agents

Two exports are made for writing automation, usually with an AI agent. Both mask
credentials: the code the agent writes loads them at run time through the SDK.

| | OpenAPI | AI bundle (.zip) |
|---|---|---|
| **Best for** | Simple sites with a JSON API | Complex sites, server-rendered HTML, multi-step flows |
| **Contains** | Endpoints, parameters, schemas and a real example per response | Everything in OpenAPI, plus every request and response in order and the full HTML of each page |
| **Dashboard** | Site → **API** → **Download OpenAPI** | Site → **API** → **Download AI bundle (.zip)** |
| **CLI** | `sessiontap openapi example.com` | `sessiontap bundle example.com` |

**OpenAPI 3.1**: URLs are grouped into templates (`/users/123/orders` →
`/users/{userId}/orders`), schemas are merged from every observed call, and examples come
from real responses (lists cut to 3 items, long strings to 300 characters, credentials
replaced by `****`). It opens in Swagger UI, Redoc, Postman, Insomnia and Bruno.

**AI bundle**

```
example.com-sessiontap.zip
├── README.md        instructions for the agent: files, how to authenticate, rules
├── openapi.json     the OpenAPI above
├── timeline.json    every request in order, with links to its files
├── session.json     cookie names, token kinds, storage keys, browser profile (no values)
└── endpoints/
    └── GET_api.example.com_users_{userId}_orders/
        ├── 0007.json              URL, headers (masked), status, timing
        ├── 0007.request.json      request body, if any
        └── 0007.response.json     full response body (.html for pages)
```

`0007` is the position in `timeline.json`, so an agent can follow a flow: which response
set a cookie or returned a CSRF token, and which later request used it.

**Full HTML pages**: on Chromium, SessionTap stores the complete HTML of every top-level
page a recorded tab loads, up to a 100 MiB safety ceiling per page. Iframes (ads,
widgets) are skipped. Turn it off in **Settings** → **Capture**.

> [!CAUTION]
> Credentials are masked, but response bodies and especially HTML pages can contain
> personal data and embedded tokens (a CSRF token in a `<meta>` tag, for example). Review
> a bundle before sharing it.

**Prompt example**

> Read the attached SessionTap bundle. Write a Python script that lists my open orders
> (id, date, total) as CSV. Use `sessiontap.httpx_client("example.com")` for the session
> and never hardcode cookies or tokens. Follow `timeline.json` to see how the site loads
> the orders page.

### MCP server

Let an agent explore what you captured through the
[Model Context Protocol](https://modelcontextprotocol.io):

```bash
uv tool install --reinstall "./core[server,mcp]"   # from your clone
```

```json
{
  "mcpServers": {
    "sessiontap": { "command": "sessiontap", "args": ["mcp"] }
  }
}
```

Tools: `list_domains`, `session_health`, `list_requests`, `get_request`, `generate_code`
and `openapi_spec`. The server is **read-only** and **never returns raw cookies or
tokens**. The agent can write working code, but credentials only exist when *you* run it.

## ⚙️ Configuration

Everything lives in the SessionTap home directory (override it with `SESSIONTAP_HOME`):

| OS | Default |
|---|---|
| Linux | `~/.local/share/sessiontap` |
| macOS | `~/Library/Application Support/sessiontap` |
| Windows | `%LOCALAPPDATA%\sessiontap` |

Optional `config.toml` in that directory:

```toml
[server]
port = 8711              # the daemon always binds to 127.0.0.1

[vault]
key_backend = "auto"     # auto | keyring | file

[capture]
max_body_kb = 512        # largest API request/response body stored (0–4096)
html = true              # keep the full HTML of pages (up to 100 MiB each)
blocklist = ["mail.google.com", "accounts.google.com", "paypal.com"]   # starting blocklist
locked = false           # true: the [capture] settings can't be changed at runtime
```

Environment overrides: `SESSIONTAP_PORT`, `SESSIONTAP_KEY_BACKEND`, `SESSIONTAP_HOME`.

The dashboard (**Settings**), the CLI and the API change retention, HTML capture, the
largest stored body and the blocklist without a restart. Adding a site to the blocklist
stops its capture right away. Data captured earlier is kept; delete it in **Settings** →
**Sites**.

**Company-managed machines**: with `locked = true`, `config.toml` is the only source of
truth. The dashboard, CLI and API refuse to edit the blocklist and capture settings (403).
Protect the file itself with your usual tooling (file permissions, MDM).

## 🧩 How it works

```
 Browser                                    Your machine (user account)
┌──────────────────────────────┐          ┌───────────────────────────────────────────────┐
│ SessionTap extension (MV3)   │  stdio   │ sessiontap-host          sessiontap daemon    │
│  • popup: opt-in per tab     │◄────────►│  (started by the   HTTP   (FastAPI, 127.0.0.1) │
│  • CDP / webRequest capture  │  native  │   browser)        ──────►  • security gate     │
│  • cookies, storage, profile │ messaging│                   token    • ingest + vault    │
└──────────────────────────────┘          │                            • API, live feed, UI│
                                          │                                  │             │
       Your scripts ── SDK (token) ──────►│                                  ▼             │
       AI agents ───── MCP (token) ──────►│                         vault.db (SQLite,      │
       Dashboard ───── browser (token) ──►│                         AES-GCM per field)     │
                                          └───────────────────────────────────────────────┘
```

1. You press **Record this tab**. The extension enables that site in the daemon and
   attaches to the tab (Chromium: DevTools protocol, for headers, bodies and HTML;
   Firefox: `webRequest`, for headers).
2. When the tab navigates to another site, or calls one with an `Authorization` header,
   that site joins the recording. Stopping (or closing the tab) disables every site it added.
3. Finished requests are batched every second through native messaging to
   `sessiontap-host`, which validates them and forwards them to the daemon with the token.
4. The daemon re-checks every event against the enabled sites and the blocklist, cuts
   oversized bodies, encrypts secret fields, extracts tokens and updates the live feed.
5. Your script calls `sessiontap.httpx_client("example.com")`. The SDK reads the token
   file and asks the daemon for the session.

## 🛡️ Security

SessionTap stores the most valuable thing your browser has: logged-in sessions. The
original project answered `fetch("http://localhost:8080/api/v1/session/all")` from any
web page. SessionTap is built so that can't happen.

| Who could attack | Defense |
|---|---|
| **A website you visit** | No CORS headers. Every route needs a 256-bit token pages can't know. Writes must be JSON, and a foreign `Origin` or `Sec-Fetch-Site: cross-site` is refused (CSRF). The `Host` must be loopback (DNS rebinding). Failed auth is throttled. The dashboard can't be framed and has a strict CSP. |
| **A device on your network** | The daemon only listens on `127.0.0.1`, and this can't be configured. |
| **Another extension** | Only SessionTap's pinned extension ID can start the native host; messages from pages and other extensions are ignored. |
| **A page you are capturing** | Size limits per message, strict validation of every event, bodies cut at `max_body_kb`, and generated code escapes every value. |
| **Accidental capture** | Nothing is captured until you record a tab, the daemon re-checks every event, and the blocklist always wins. Chromium shows its "started debugging this browser" bar and the icon shows **REC**. |
| **Convenience features** | Credentials masked unless you reveal them, generated code without secrets, a read-only MCP server, summaries only in the live feed, a one-time 60-second login code for `sessiontap open`, no access log. |
| **Another user on the computer** | Home directory `0700`; token, key and vault `0600`. |
| **Supply chain** | Lockfiles, Dependabot, CodeQL, gitleaks in pre-commit and CI, GitHub Actions pinned to commit SHAs, and an unminified extension you can read. |

<details>
<summary><b>What is stored, and what is not protected</b></summary>

**Stored:** cookies, auth headers, tokens, Web Storage values, URLs, headers and bodies
are encrypted per field in `vault.db`. The vault key is in your OS keyring (fallback
`vault.key`, `0600`). Domains, URL paths, status codes and cookie *names* stay in clear
text so they can be listed and searched.

**Out of scope:**

- **Malware running as your user.** It can read the browser's own cookie database just as
  easily. With the **file key** fallback (no keyring, e.g. headless Linux) it can decrypt
  the vault directly; `sessiontap status` and the dashboard warn about this.
- **What you do with a session.** Undocumented APIs, rate limits and terms of service are
  your responsibility.
- **Browser bugs** in native messaging, `chrome.debugger` or permission prompts.

</details>

<details>
<summary><b>Extension permissions</b></summary>

| Permission | Why |
|---|---|
| `nativeMessaging` | Talk to `sessiontap-host`, the only way data leaves the extension. |
| `activeTab` | Read the current tab's address when you open the popup. |
| `debugger` (Chromium) | Read headers, API bodies and full HTML through DevTools, only in recorded tabs. |
| `webRequest` (Firefox) | Read request and response headers on enabled sites. |
| `cookies` | Snapshot and follow cookie changes for enabled sites. |
| `scripting` | Read localStorage/sessionStorage and the browser profile on enabled sites. |
| `storage` | Remember which tabs are recorded (cleared when the browser closes). |
| Host access (all sites) | Granted once at install so a recording can follow a flow across domains without a prompt per site. Nothing is read from a site until you record it. |

The extension makes no network requests (no analytics, no telemetry, no remote code) and
never changes pages.

</details>

## 🔄 Update and uninstall

```bash
# update
git pull
npm ci && npm run build
uv tool install --reinstall "./core[server]"
sessiontap stop && sessiontap start --detach   # then reload the extension

# uninstall
sessiontap stop
sessiontap purge --all          # deletes the vault and its key
sessiontap uninstall-host
uv tool uninstall sessiontap
```

## 🩹 Troubleshooting

| Message | Fix |
|---|---|
| Popup: "Run `sessiontap install-host`" | `sessiontap install-host`, then reload the extension |
| Popup: "Daemon off" | `sessiontap start --detach` |
| Popup: record button disabled on a site | The site is on your blocklist. Remove it in **Settings** → **Blocklist** if you really need it. |
| Dashboard: "Vault key is stored in a file" | No OS keyring found. Install GNOME Keyring or KWallet, then run `sessiontap purge --all`. |

## 📁 Repository

| Path | What |
|---|---|
| [`core/`](core) | Python package: daemon, CLI, native host, SDK, MCP server |
| [`extension/`](extension) | Browser extension (TypeScript, Manifest V3) |
| [`dashboard/`](dashboard) | Web UI (React + Vite), built into the Python package |
| [`sdk/js/`](sdk/js) | JavaScript SDK |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed in each version |

## ⚖️ Responsible use

SessionTap is for **your own accounts and data**. Respect websites' terms of service and
rate limits. Do not use it to access other people's accounts or to get around access
controls. Undocumented APIs change without notice.

## 🤝 Contributing and security

Contributions are welcome, translations included. Start with
[CONTRIBUTING.md](CONTRIBUTING.md). Please **don't open a public issue for security problems**:
report them privately in the repository's **Security** tab → **Report a vulnerability**.

## 📄 Credits and license

SessionTap is a from-scratch rewrite inspired by
[SCRAPY / SCRAPPER](https://github.com/BunElysiaReact/SCRAPY) by Ernest Pease.

Licensed under the [Apache License 2.0](LICENSE).
