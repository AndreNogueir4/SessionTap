# Changelog

All notable changes to SessionTap are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-24

First release. SessionTap is a from-scratch rewrite inspired by
[SCRAPY / SCRAPPER](https://github.com/BunElysiaReact/SCRAPY) by Ernest Pease,
rebuilt around security and opt-in capture. It is installed from a clone of the
repository; nothing is published to PyPI or npm.

### Added

#### Capture

- Browser extension for Chrome, Brave, Edge and Firefox (Manifest V3, TypeScript),
  with no telemetry, no remote code and no page modification.
- Per-tab recording: nothing is captured until you click **Record this tab**. The
  recording follows the flow across domains (subdomains, SSO/OAuth redirects, API
  hosts called with an `Authorization` header) and stops when you press **Stop
  recording** or close the tab. Ads and trackers in iframes are ignored.
- Captures cookies, request/response headers, text bodies of API calls,
  localStorage/sessionStorage and the browser profile (user agent, languages, screen).
- Full HTML of top-level pages on Chromium (up to 100 MiB each), sent in chunks over
  native messaging.
- Popup with live counts for the recording: requests, cookies, tokens, storage
  values and every site the recording added.
- User-managed blocklist, editable from the dashboard, the CLI and the API. It ships
  with only an example (`example.block.com`): add the sites you never want captured.
- `[capture] locked = true` in `config.toml` freezes the blocklist and capture
  settings for company-managed machines.

#### Security

- Local daemon bound to `127.0.0.1` only, protected by a 256-bit bearer token
  stored with `0600` permissions and compared in constant time.
- Host allowlist (DNS rebinding), Origin and `Sec-Fetch-Site` checks and JSON-only
  writes (CSRF), size limits, failed-auth throttling and strict security headers.
- Encrypted vault: SQLite with per-field AES-256-GCM, key in the OS keyring (file
  fallback, reported in `status`), retention policy and `sessiontap purge`.
- Native host `sessiontap-host` with strict framing, message validation and size
  limits; extension ID pinned through the manifest `key`.
- Credentials masked everywhere unless you explicitly reveal them.
- Threat model in the README covering websites, the local network, other
  extensions, captured pages and other users on the same computer.

#### Using a session

- `sessiontap` CLI: daemon lifecycle, native host registration, capture list,
  blocklist, purge, encrypted export/import, OpenAPI and AI bundle exports.
- Python SDK with `httpx`, `requests`, `curl_cffi` and Playwright helpers.
- JavaScript SDK with `fetch` headers and Playwright/Puppeteer cookies.
- Code generator for curl, Python and JavaScript that loads secrets at run time.
- Session health: cookie and JWT expiry warnings.
- Read-only MCP server for AI agents that never returns raw cookies or tokens.

#### Dashboard

- React dashboard served by the daemon and opened with `sessiontap open` through a
  one-time login code.
- Sites, requests, request detail with body download, session (cookies, tokens,
  storage) with reveal and copy, live feed and settings.
- Settings for retention, HTML capture, largest stored body and the blocklist.

#### Exports

- OpenAPI 3.1 inferred from real traffic: path templating, schema inference and
  masked examples.
- AI bundle (.zip): timeline, every request and response in order, full HTML pages
  and a README that explains the bundle to an agent.
- Encrypted, passphrase-protected session export/import (scrypt + AES-256-GCM).

#### Project

- English and Portuguese (Brazil) in the extension, the dashboard and the README.
- README in English and Portuguese: install, usage, AI exports, configuration,
  architecture, security and extension permissions.
- CI with lint, type checks, tests and builds, CodeQL, Dependabot, gitleaks and
  GitHub Actions pinned to commit SHAs.
- Release workflow that attaches the extension zips to a GitHub release with
  SHA-256 checksums, Sigstore signatures and an SBOM.

### Removed (compared to the original project)

- API on `0.0.0.0` with `Access-Control-Allow-Origin: *` and no authentication.
- Always-on capture of every site.
- Plaintext `.jsonl` storage.
- `stealth.js` fingerprint spoofing.
- `rust_finder`.
- The manual "register extension ID" step.

[Unreleased]: https://github.com/AndreNogueir4/SessionTap/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/AndreNogueir4/SessionTap/releases/tag/v1.0.0
