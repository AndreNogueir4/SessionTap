// Chromium capture through the DevTools protocol (chrome.debugger).
//
// The debugger is attached only to tabs showing an enabled site or being recorded, and
// the browser shows its "started debugging this browser" bar the whole time, so the
// capture is always visible. Only XHR/fetch/document requests to enabled domains are
// recorded; in a recorded tab, a top-level navigation or an API call carrying an
// Authorization header to another site asks `follow` to add that site to the recording.
// Bodies for text responses of XHR/fetch, up to the daemon's limit, and the complete HTML
// of top-level pages (capture.html in config.toml, on by default).

import { hostOf, matchAny } from "./domains";
import type { EventQueue } from "./queue";
import type { CaptureState, ExchangeEvent, Headers } from "./types";

const PROTOCOL = "1.3";
const CAPTURED_TYPES = new Set(["XHR", "Fetch", "Document", "EventSource"]);
const BODY_TYPES = new Set(["XHR", "Fetch"]);
const TEXT_MIME = /json|text|xml|javascript|x-www-form-urlencoded|graphql/i;
const MAX_PENDING = 2000;
const RESOURCE_BUFFER = 128 * 1024 * 1024;
const TOTAL_BUFFER = 512 * 1024 * 1024;

interface Pending {
  event: ExchangeEvent;
  tabId: number;
  startedMono: number;
  page: boolean;
}

type Params = Record<string, unknown>;

export type Follow = (tabId: number, url: string) => boolean;

export class CdpCapture {
  private attached = new Set<number>();
  private pending = new Map<string, Pending>();
  private mainFrame = new Map<number, string>();

  constructor(
    private queue: EventQueue,
    private enabled: () => string[],
    private settings: () => CaptureState,
    private follow: Follow,
  ) {
    chrome.debugger.onEvent.addListener((source, method, params) => {
      if (source.tabId !== undefined && this.attached.has(source.tabId)) {
        void this.onEvent(source.tabId, method, (params ?? {}) as Params);
      }
    });
    chrome.debugger.onDetach.addListener((source) => {
      if (source.tabId !== undefined) this.forget(source.tabId);
    });
  }

  isAttached(tabId: number): boolean {
    return this.attached.has(tabId);
  }

  async attach(tabId: number): Promise<void> {
    if (this.attached.has(tabId)) return;
    try {
      await chrome.debugger.attach({ tabId }, PROTOCOL);
    } catch (e) {
      // Another debugger (DevTools) may own the tab; nothing is captured then.
      console.warn("SessionTap: cannot attach to tab", tabId, e);
      return;
    }
    this.attached.add(tabId);
    await chrome.debugger.sendCommand({ tabId }, "Network.enable", {
      maxPostDataSize: this.settings().max_body_bytes,
      maxResourceBufferSize: RESOURCE_BUFFER,
      maxTotalBufferSize: TOTAL_BUFFER,
    });
    try {
      const tree = (await chrome.debugger.sendCommand({ tabId }, "Page.getFrameTree")) as {
        frameTree: { frame: { id: string } };
      };
      this.mainFrame.set(tabId, tree.frameTree.frame.id);
    } catch {
      /* not a page target */
    }
  }

  async detach(tabId: number): Promise<void> {
    if (!this.attached.has(tabId)) return;
    this.forget(tabId);
    try {
      await chrome.debugger.detach({ tabId });
    } catch {
      /* already gone */
    }
  }

  async detachAll(): Promise<void> {
    await Promise.all([...this.attached].map((t) => this.detach(t)));
  }

  private forget(tabId: number): void {
    this.attached.delete(tabId);
    this.mainFrame.delete(tabId);
    for (const [key, p] of this.pending) if (p.tabId === tabId) this.pending.delete(key);
  }

  private captured(url: string): boolean {
    const host = hostOf(url);
    return host !== null && matchAny(host, this.enabled()) !== null;
  }

  private async onEvent(tabId: number, method: string, params: Params): Promise<void> {
    const key = `${tabId}:${String(params.requestId)}`;
    switch (method) {
      case "Network.requestWillBeSent": {
        const request = params.request as { url: string; method: string; headers: Headers; postData?: string };
        const type = String(params.type ?? "");
        const redirect = params.redirectResponse as { status: number; headers: Headers; mimeType: string } | undefined;
        if (redirect) {
          const previous = this.pending.get(key);
          if (previous) {
            Object.assign(previous.event, {
              status: redirect.status,
              response_headers: redirect.headers,
              mime_type: redirect.mimeType,
            });
            this.finish(key);
          }
        }
        if (!CAPTURED_TYPES.has(type)) return;
        const navigation = type === "Document" && params.frameId === this.mainFrame.get(tabId);
        if (!this.captured(request.url)) {
          const authorized = BODY_TYPES.has(type) && Object.keys(request.headers).some((h) => h.toLowerCase() === "authorization");
          if (!(navigation || authorized) || !this.follow(tabId, request.url)) return;
        }
        if (this.pending.size >= MAX_PENDING) this.pending.delete(this.pending.keys().next().value!);
        this.pending.set(key, {
          tabId,
          page: navigation,
          startedMono: performance.now(),
          event: {
            type: "exchange",
            url: request.url,
            method: request.method.toUpperCase(),
            request_headers: { ...request.headers },
            request_body: request.postData ?? null,
            response_headers: {},
            resource_type: type,
            started_at: typeof params.wallTime === "number" ? params.wallTime : Date.now() / 1000,
          },
        });
        return;
      }
      case "Network.requestWillBeSentExtraInfo": {
        // Full request headers as sent, including Cookie.
        const p = this.pending.get(key);
        if (p) Object.assign(p.event.request_headers, params.headers as Headers);
        return;
      }
      case "Network.responseReceived": {
        const p = this.pending.get(key);
        const response = params.response as { status: number; headers: Headers; mimeType: string };
        if (p) {
          p.event.status = response.status;
          p.event.mime_type = response.mimeType;
          Object.assign(p.event.response_headers, response.headers);
        }
        return;
      }
      case "Network.responseReceivedExtraInfo": {
        const p = this.pending.get(key);
        if (p) Object.assign(p.event.response_headers, params.headers as Headers);
        return;
      }
      case "Network.loadingFinished": {
        const p = this.pending.get(key);
        if (!p) return;
        const size = Number(params.encodedDataLength ?? 0);
        const settings = this.settings();
        const api = BODY_TYPES.has(p.event.resource_type ?? "") && TEXT_MIME.test(p.event.mime_type ?? "");
        const html = p.page && settings.capture_html !== false && /html/i.test(p.event.mime_type ?? "");
        if ((api && size <= settings.max_body_bytes * 4) || html) {
          const body = await this.responseBody(tabId, params.requestId);
          const limit = html ? (settings.max_html_bytes ?? Infinity) : Infinity;
          if (body !== null) p.event.response_body = body.length > limit ? body.slice(0, limit) : body;
        }
        this.finish(key);
        return;
      }
      case "Network.loadingFailed": {
        const p = this.pending.get(key);
        if (p) {
          p.event.error = String(params.errorText ?? "failed").slice(0, 500);
          this.finish(key);
        }
        return;
      }
    }
  }

  private async responseBody(tabId: number, requestId: unknown): Promise<string | null> {
    try {
      const body = (await chrome.debugger.sendCommand({ tabId }, "Network.getResponseBody", { requestId })) as {
        body: string;
        base64Encoded: boolean;
      };
      if (!body.base64Encoded) return body.body;
      const bytes = Uint8Array.from(atob(body.body), (c) => c.charCodeAt(0));
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      return null; // evicted from the buffer, or binary
    }
  }

  private finish(key: string): void {
    const p = this.pending.get(key);
    if (!p) return;
    this.pending.delete(key);
    p.event.duration_ms = Math.max(0, performance.now() - p.startedMono);
    this.queue.push(p.event);
  }
}
