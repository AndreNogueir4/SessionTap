# Security policy

SessionTap stores logged-in browser sessions, so security reports are taken seriously
and handled before any other work.

## Supported versions

Only the latest release gets security fixes. There are no backports.

| Version | Supported |
|---|---|
| 1.0.x | ✅ |
| < 1.0 | ❌ |

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a security problem.**

Report it privately through GitHub:
[**Security → Report a vulnerability**](https://github.com/AndreNogueir4/SessionTap/security/advisories/new).

Please include:

- the SessionTap version, operating system and browser;
- what an attacker can do, and from which position (a web page, another extension,
  another local user, the network…);
- steps to reproduce or a proof of concept.

**Never include real cookies, tokens, HAR files or captured requests.** Use fake values
or redact them.

## What to expect

SessionTap is maintained by one person in their spare time, so these are goals, not
guarantees:

- an acknowledgement within **7 days**;
- an assessment (accepted, needs more information, or out of scope) within **14 days**;
- a fixed release as soon as possible, aiming for **30 days** for serious issues.

Fixes ship as a new release with a GitHub security advisory. You will be credited in
the advisory unless you prefer to stay anonymous.

## Scope

In scope: anything that lets an attacker read, change or misuse captured data, or
capture data without the user recording a tab. For example:

- a web page reaching the daemon API (CORS, CSRF, DNS rebinding, token leaks);
- another extension or a web page talking to the native host;
- captured content that breaks validation, the dashboard or generated code
  (injection, XSS);
- secrets that are logged, returned unmasked or written to disk unencrypted;
- files created with permissions readable by other local users;
- weaknesses in the release pipeline or its signatures.

Out of scope (see the README's **Security** section):

- malware already running as your user;
- the file key fallback being readable by your own user, which SessionTap already warns
  about;
- bugs in the browser itself (native messaging, `chrome.debugger`, permission prompts);
- what a user chooses to do with their own session.
