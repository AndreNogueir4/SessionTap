// SessionTap SDK for Node.js. Talks to the local daemon on 127.0.0.1 only.

import { readFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

export interface Cookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  secure: boolean;
  http_only: boolean;
  same_site: string | null;
  expires: number | null;
}

export interface Session {
  domain: string;
  cookies: Cookie[];
  user_agent: string | null;
  storage: Record<string, { local: Record<string, string>; session: Record<string, string> }>;
  fingerprint: Record<string, unknown> | null;
}

export interface PlaywrightCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires?: number;
  httpOnly: boolean;
  secure: boolean;
  sameSite?: "Strict" | "Lax" | "None";
}

export interface Options {
  /** Defaults to http://127.0.0.1:<port from config.toml or SESSIONTAP_PORT, else 8711>. */
  baseUrl?: string;
  /** Defaults to the token file in the SessionTap home directory. */
  token?: string;
  /** Defaults to SESSIONTAP_HOME or the platform data directory. */
  home?: string;
}

export class SessionTapError extends Error {}

/** Same location as the Python package (platformdirs.user_data_path("sessiontap")). */
export function defaultHome(): string {
  if (process.env.SESSIONTAP_HOME) return process.env.SESSIONTAP_HOME;
  const os = platform();
  if (os === "win32") return join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "sessiontap");
  if (os === "darwin") return join(homedir(), "Library", "Application Support", "sessiontap");
  return join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "sessiontap");
}

function readPort(home: string): number {
  if (process.env.SESSIONTAP_PORT) return Number(process.env.SESSIONTAP_PORT);
  try {
    const toml = readFileSync(join(home, "config.toml"), "utf8");
    const section = toml.split(/^\[server\]\s*$/m)[1]?.split(/^\[/m)[0] ?? "";
    const match = /^\s*port\s*=\s*(\d+)/m.exec(section);
    if (match?.[1]) return Number(match[1]);
  } catch {
    /* no config file */
  }
  return 8711;
}

const SAME_SITE: Record<string, PlaywrightCookie["sameSite"]> = {
  lax: "Lax",
  strict: "Strict",
  no_restriction: "None",
  none: "None",
};

export class SessionTap {
  private readonly baseUrl: string;
  private readonly token: string;

  constructor(options: Options = {}) {
    const home = options.home ?? defaultHome();
    this.baseUrl = options.baseUrl ?? `http://127.0.0.1:${readPort(home)}`;
    const url = new URL(this.baseUrl);
    if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
      throw new SessionTapError("SessionTap only talks to a daemon on this machine (127.0.0.1)");
    }
    let token = options.token;
    if (!token) {
      try {
        token = readFileSync(join(home, "token"), "utf8").trim();
      } catch {
        throw new SessionTapError(
          `No SessionTap token in ${home}. Install SessionTap and run \`sessiontap start\`.`,
        );
      }
    }
    this.token = token;
  }

  async api<T>(path: string, params: Record<string, string> = {}): Promise<T> {
    const query = new URLSearchParams(params).toString();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}${query ? `?${query}` : ""}`, {
        headers: { authorization: `Bearer ${this.token}` },
      });
    } catch (e) {
      throw new SessionTapError("SessionTap daemon is not running (`sessiontap start`)", { cause: e });
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail;
      } catch {
        /* not JSON */
      }
      throw new SessionTapError(`${response.status}: ${detail}`);
    }
    return (await response.json()) as T;
  }

  session(domain: string, subdomains = true): Promise<Session> {
    return this.api<Session>(`/v1/sessions/${encodeURIComponent(domain)}`, {
      subdomains: String(subdomains),
    });
  }

  health(domain: string): Promise<Record<string, unknown>> {
    return this.api(`/v1/sessions/${encodeURIComponent(domain)}/health`);
  }

  async secret(domain: string, name: string): Promise<string> {
    const r = await this.api<{ value: string }>(`/v1/sessions/${encodeURIComponent(domain)}/secret`, { name });
    return r.value;
  }

  async cookieHeader(domain: string): Promise<string> {
    const s = await this.session(domain, false);
    return s.cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  }

  /** `cookie` and `user-agent` headers for fetch/undici/axios. */
  async headers(domain: string): Promise<Record<string, string>> {
    const s = await this.session(domain, false);
    const headers: Record<string, string> = {
      cookie: s.cookies.map((c) => `${c.name}=${c.value}`).join("; "),
    };
    if (s.user_agent) headers["user-agent"] = s.user_agent;
    return headers;
  }

  /** For `browserContext.addCookies()`. */
  async playwrightCookies(domain: string): Promise<PlaywrightCookie[]> {
    const s = await this.session(domain);
    return s.cookies.map((c) => {
      const out: PlaywrightCookie = {
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path,
        httpOnly: c.http_only,
        secure: c.secure,
      };
      if (c.expires) out.expires = c.expires;
      const sameSite = c.same_site ? SAME_SITE[c.same_site.toLowerCase()] : undefined;
      if (sameSite) out.sameSite = sameSite;
      return out;
    });
  }

  /** For `page.setCookie(...)` (same shape Puppeteer accepts). */
  puppeteerCookies(domain: string): Promise<PlaywrightCookie[]> {
    return this.playwrightCookies(domain);
  }
}
