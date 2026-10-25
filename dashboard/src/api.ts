// Talks to the daemon on the same origin. The token is kept in memory only:
// reloading the page signs you out (run `sessiontap open` again).

export interface Domain {
  domain: string;
  capture: boolean;
  requests: number;
  cookies: number;
  tokens: number;
  last_seen: number | null;
}

export interface RequestSummary {
  id: number;
  domain: string;
  host: string;
  method: string;
  path: string;
  status: number | null;
  mime_type: string | null;
  resource_type: string | null;
  started_at: number;
  duration_ms: number | null;
  error: string | null;
}

export interface RequestDetail extends RequestSummary {
  url: string;
  request_headers: Record<string, string>;
  response_headers: Record<string, string>;
  request_body: string | null;
  response_body: string | null;
  request_body_size: number;
  response_body_size: number;
  body_truncated: boolean;
}

export type ExpiryState = "ok" | "expiring" | "expired" | "session" | "unknown";

export interface Health {
  domain: string;
  status: "ok" | "warning" | "expired" | "empty";
  next_expiry: number | null;
  last_activity: number | null;
  cookies: { name: string; domain: string; expires: number | null; state: ExpiryState }[];
  tokens: {
    id: number;
    kind: string;
    jwt: boolean;
    subject: string | null;
    issuer: string | null;
    expires: number | null;
    state: ExpiryState;
    last_seen: number;
  }[];
}

export interface Session {
  domain: string;
  cookies: { name: string; value: string; domain: string; path: string }[];
}

export interface Status {
  version: string;
  key_backend: string;
  vault_bytes: number;
  retention_days: number;
  capture_domains: string[];
  counts: Record<string, number>;
}

export interface Settings {
  retention_days: number;
  blocklist: string[];
  capture_html: boolean;
  max_body_kb: number;
  locked: boolean;
  port: number;
}

export interface BlocklistView {
  domains: { domain: string; default: boolean }[];
  removed_defaults: string[];
  customized: boolean;
  locked: boolean;
}

export interface LiveEvent {
  type: string;
  domain?: string;
  method?: string;
  path?: string;
  status?: number | null;
  id?: number;
  name?: string;
  [key: string]: unknown;
}

let token: string | null = null;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function signedIn(): boolean {
  return token !== null;
}

export function signOut(): void {
  token = null;
}

let urlSignIn: Promise<boolean> | null = null;

/** Exchange the single-use code from `sessiontap open` (#code=...) for the token. */
export function signInFromUrl(): Promise<boolean> {
  urlSignIn ??= exchangeCode(); // once, even if React runs effects twice
  return urlSignIn;
}

async function exchangeCode(): Promise<boolean> {
  const code = new URLSearchParams(location.hash.slice(1)).get("code");
  // Remove the code from the address bar and history right away.
  history.replaceState(null, "", location.pathname);
  if (!code) return false;
  const r = await fetch("/v1/auth/exchange", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!r.ok) return false;
  token = ((await r.json()) as { token: string }).token;
  return true;
}

export async function signInWithToken(value: string): Promise<boolean> {
  token = value.trim();
  try {
    await get("/v1/status");
    return true;
  } catch {
    token = null;
    return false;
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { authorization: `Bearer ${token ?? ""}` };
  if (body !== undefined) headers["content-type"] = "application/json";
  const r = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 401) token = null;
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = ((await r.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail);
  }
  const type = r.headers.get("content-type") ?? "";
  return (type.includes("json") ? r.json() : r.text()) as Promise<T>;
}

export const get = <T>(path: string) => call<T>("GET", path);

/** Fetches with the token (a plain link cannot send it) and saves the response as a file. */
export async function download(path: string, filename: string): Promise<void> {
  const r = await fetch(path, { headers: { authorization: `Bearer ${token ?? ""}` }, cache: "no-store" });
  if (r.status === 401) token = null;
  if (!r.ok) throw new ApiError(r.status, r.statusText);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const api = {
  status: () => get<Status>("/v1/status"),
  settings: () => get<Settings>("/v1/settings"),
  saveSettings: (patch: Partial<Settings>) => call<Settings>("PATCH", "/v1/settings", patch),
  domains: () => get<Domain[]>("/v1/domains"),
  blocklist: () => get<BlocklistView>("/v1/blocklist"),
  block: (domain: string) => call<BlocklistView>("POST", "/v1/blocklist", { domain }),
  unblock: (domain: string) => call<BlocklistView>("DELETE", `/v1/blocklist/${encodeURIComponent(domain)}`),
  resetBlocklist: () => call<BlocklistView>("POST", "/v1/blocklist/reset", {}),
  setCapture: (domain: string, capture: boolean) =>
    call("PUT", `/v1/domains/${encodeURIComponent(domain)}`, { capture }),
  purge: (domain: string) => call("DELETE", `/v1/domains/${encodeURIComponent(domain)}`),
  requests: (domain: string, q: string, limit = 200) =>
    get<RequestSummary[]>(
      `/v1/requests?${new URLSearchParams({ domain, limit: String(limit), ...(q ? { q } : {}) })}`,
    ),
  request: (id: number, reveal: boolean, bodyLimit: number) =>
    get<RequestDetail>(`/v1/requests/${id}?reveal=${reveal}&body_limit=${bodyLimit}`),
  code: (id: number, lang: string, includeSecrets: boolean) =>
    get<string>(`/v1/requests/${id}/code?lang=${lang}&include_secrets=${includeSecrets}`),
  health: (domain: string) => get<Health>(`/v1/sessions/${encodeURIComponent(domain)}/health`),
  session: (domain: string) => get<Session>(`/v1/sessions/${encodeURIComponent(domain)}`),
  secret: (domain: string, name: string) =>
    get<{ name: string; value: string }>(
      `/v1/sessions/${encodeURIComponent(domain)}/secret?${new URLSearchParams({ name })}`,
    ),
  openapi: (domain: string) => get<Record<string, unknown>>(`/v1/openapi/${encodeURIComponent(domain)}`),
};

/** Server-sent events over fetch, because EventSource cannot send the Authorization header. */
export function subscribe(onEvent: (e: LiveEvent) => void, signal: AbortSignal): void {
  void (async () => {
    while (!signal.aborted) {
      try {
        const r = await fetch("/v1/events", {
          headers: { authorization: `Bearer ${token ?? ""}` },
          signal,
        });
        if (!r.ok || !r.body) throw new Error(String(r.status));
        const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          let i: number;
          while ((i = buffer.indexOf("\n\n")) >= 0) {
            const chunk = buffer.slice(0, i);
            buffer = buffer.slice(i + 2);
            for (const line of chunk.split("\n")) {
              if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as LiveEvent);
            }
          }
        }
      } catch {
        if (signal.aborted) return;
      }
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
  })();
}
