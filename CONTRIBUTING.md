# Contributing to SessionTap

Thanks for helping! This project lives or dies by its security, so a few rules
are stricter than usual. Everything else is meant to be easy.

## Ground rules

1. **Never commit real cookies, tokens, HAR files or captured data**, not even
   in tests. Use obviously fake values (`test-token`, `example.com`).
   `pre-commit` runs gitleaks to catch mistakes.
2. **Security-relevant changes need a note in the PR**: new endpoints, new
   extension permissions, anything that stores, logs or returns secrets.
3. **Secure by default**: new features ship disabled or masked when they touch
   secrets; the user opts in.
4. Be respectful: no harassment, no personal attacks.

## Repository layout

| Path | What | Stack |
|---|---|---|
| `core/` | daemon, CLI, native host, Python SDK, MCP server | Python 3.11+, FastAPI, SQLite |
| `extension/` | browser extension (Chromium + Firefox) | TypeScript, MV3, esbuild |
| `dashboard/` | web UI served by the daemon | React, Vite, TypeScript |
| `sdk/js/` | JavaScript SDK | TypeScript |

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Python
cd core
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy

# TypeScript (extension, dashboard, JS SDK)
cd ..
npm install
npm run typecheck
npm run build

# pre-commit hooks (gitleaks, ruff, whitespace)
uvx pre-commit install
```

Run the whole thing locally:

```bash
cd core
uv run sessiontap install-host       # registers the native host for your browsers
uv run sessiontap start              # daemon on http://127.0.0.1:8711
uv run sessiontap open               # dashboard, already authenticated
```

Then load `extension/dist/chromium` as an unpacked extension (or
`extension/dist/firefox/manifest.json` as a temporary add-on in Firefox).

Dashboard with hot reload: `npm run dev -w dashboard` (proxies `/v1` to the daemon).

## Translations

English is the base language; every other language falls back to it. Portuguese
(Brazil) ships today. When you change a user-facing text, update both:

| Part | English | Portuguese |
|---|---|---|
| Extension | `extension/static/_locales/en/messages.json` | `extension/static/_locales/pt_BR/messages.json` |
| Dashboard | `dashboard/src/i18n/en.ts` | `dashboard/src/i18n/pt-BR.ts` (the type check fails if a key is missing) |
| README | `README.md` | `README.pt-BR.md` |

To add a language, add a `_locales/<code>/` folder, a dashboard dictionary
registered in `dashboard/src/i18n/index.ts`, and a `README.<code>.md` linked from both READMEs.
The CLI, the API and log messages stay in English.

## Python code style

- No `from __future__ import annotations` (use `typing.Self` or a quoted annotation when needed).
- No comments or docstrings; names should explain the code. Only `# noqa` / `# type: ignore`
  directives are allowed.
- No blank lines inside function bodies (except after a local import).
- Imports at the top of the file, as a "staircase": first every `import x`, then every
  `from x import y`, each group sorted by line length. The only imports inside functions are
  optional or platform-specific ones (`winreg`, `requests`, `curl_cffi`, server-only modules
  used by the CLI) so the SDK installs without the server extras.
- Files are `lowercase.py`; classes are `CapWords` (PEP 8).

## Pull requests

- Keep PRs focused; one topic per PR.
- Add or update tests. Security checks (auth, Host/Origin, masking) must stay covered.
- CI must be green: lint, types, tests, builds, CodeQL.
- Describe **why**, not only what.

## Good first contributions

- Docs and tutorials for specific tools (Playwright, Scrapy, Go…)
- More code generator targets (`core/src/sessiontap/server/codegen.py`)
- Better path templating heuristics for the OpenAPI export
- Dashboard UX polish
