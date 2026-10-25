// The only way out of the extension: the native messaging port to `sessiontap-host`.
// No network requests are ever made from the extension itself.

import type { CaptureEvent, CaptureState, Connection, SiteSummary } from "./types";

const HOST = "com.sessiontap.host";
const TIMEOUT_MS = 15_000;
const INGEST_TIMEOUT_MS = 150_000;
// Chrome caps one message to the native host at 64 MiB; large payloads (full HTML pages)
// go in parts the host reassembles. Parts are measured in UTF-16 units, so even fully
// escaped JSON stays far below the host's 16 MiB frame limit.
const PART_CHARS = 2 * 1024 * 1024;

interface Reply {
  id: number;
  ok: boolean;
  data?: unknown;
  error?: string;
  detail?: string;
}

export class NativeBridge {
  private port: chrome.runtime.Port | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: (r: Reply) => void; timer: ReturnType<typeof setTimeout> }>();
  private retryMs = 1000;
  connection: Connection = "connecting";
  lastError: string | null = null;
  onState: (state: CaptureState) => void = () => {};

  start(): void {
    this.connect();
  }

  private connect(): void {
    try {
      this.port = chrome.runtime.connectNative(HOST);
    } catch (e) {
      this.fail("host_missing", String(e));
      return;
    }
    this.port.onMessage.addListener((msg: Reply) => this.receive(msg));
    this.port.onDisconnect.addListener(() => {
      const err = chrome.runtime.lastError?.message ?? "disconnected";
      this.port = null;
      for (const [, p] of this.pending) {
        clearTimeout(p.timer);
        p.resolve({ id: -1, ok: false, error: "disconnected" });
      }
      this.pending.clear();
      this.fail(/not found|not allowed|forbidden/i.test(err) ? "host_missing" : "daemon_offline", err);
    });
    void this.refresh();
  }

  private fail(connection: Connection, error: string): void {
    this.connection = connection;
    this.lastError = error;
    setTimeout(() => this.port ?? this.connect(), this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, 30_000);
  }

  private receive(msg: Reply): void {
    const p = this.pending.get(msg.id);
    if (!p) return;
    clearTimeout(p.timer);
    this.pending.delete(msg.id);
    p.resolve(msg);
  }

  private request(type: string, extra: Record<string, unknown> = {}, timeoutMs = TIMEOUT_MS): Promise<Reply> {
    return new Promise((resolve) => {
      if (!this.port) {
        resolve({ id: -1, ok: false, error: "not_connected" });
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve({ id, ok: false, error: "timeout" });
      }, timeoutMs);
      this.pending.set(id, { resolve, timer });
      this.port.postMessage({ id, type, ...extra });
    });
  }

  /** Ask the daemon which domains are enabled; updates `connection`. */
  async refresh(): Promise<CaptureState | null> {
    const reply = await this.request("state");
    if (reply.ok) {
      this.connection = "connected";
      this.lastError = null;
      this.retryMs = 1000;
      const state = reply.data as CaptureState;
      this.onState(state);
      return state;
    }
    if (reply.error === "daemon_unreachable" || reply.error === "no_token") {
      this.connection = "daemon_offline";
      this.lastError = reply.error;
    }
    return null;
  }

  async setCapture(domain: string, enabled: boolean): Promise<{ ok: boolean; error?: string }> {
    const reply = await this.request("set_capture", { domain, enabled });
    if (!reply.ok) return { ok: false, error: reply.detail ?? reply.error ?? "failed" };
    await this.refresh();
    return { ok: true };
  }

  async siteSummary(domain: string): Promise<SiteSummary | null> {
    const reply = await this.request("site_summary", { domain });
    return reply.ok ? (reply.data as SiteSummary) : null;
  }

  async loginCode(): Promise<{ code: string; port: number } | null> {
    const reply = await this.request("login_code");
    return reply.ok ? (reply.data as { code: string; port: number }) : null;
  }

  /** "retry" for transport problems; "rejected" when the daemon refused the batch itself. */
  async ingest(events: CaptureEvent[]): Promise<"ok" | "retry" | "rejected"> {
    const payload = JSON.stringify({ events });
    if (payload.length > PART_CHARS) return this.ingestInParts(payload);
    const reply = await this.request("ingest", { events }, INGEST_TIMEOUT_MS);
    if (reply.ok) return "ok";
    return reply.error === "rejected" ? "rejected" : "retry";
  }

  private async ingestInParts(payload: string): Promise<"ok" | "retry" | "rejected"> {
    const upload = crypto.randomUUID();
    let start = 0;
    for (let seq = 0; start < payload.length; seq++) {
      let end = Math.min(start + PART_CHARS, payload.length);
      // Never split a surrogate pair between two parts.
      if (end < payload.length && /[\uD800-\uDBFF]/.test(payload[end - 1]!)) end--;
      const last = end >= payload.length;
      const reply = await this.request(
        "ingest_part",
        { upload, seq, last, data: payload.slice(start, end) },
        last ? INGEST_TIMEOUT_MS : TIMEOUT_MS,
      );
      if (!reply.ok) return reply.error === "rejected" ? "rejected" : "retry";
      start = end;
    }
    return "ok";
  }
}
