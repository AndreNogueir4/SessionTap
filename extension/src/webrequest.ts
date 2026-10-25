// Firefox capture through webRequest: URLs, methods, headers and status codes.
// Firefox has no chrome.debugger, so response bodies are not captured there.
// In a recorded tab, top-level navigations and API calls with an Authorization header
// to other sites ask `follow` to add that site, like the Chromium capture.

import { hostOf, matchAny } from "./domains";
import type { Follow } from "./cdp";
import type { EventQueue } from "./queue";
import type { ExchangeEvent, Headers } from "./types";

const TYPES = ["xmlhttprequest", "main_frame"] as chrome.webRequest.ResourceType[];
const MAX_PENDING = 2000;

function toHeaders(list?: chrome.webRequest.HttpHeader[]): Headers {
  const out: Headers = {};
  for (const h of list ?? []) {
    if (h.value === undefined) continue;
    const name = h.name.toLowerCase();
    out[name] = name in out ? `${out[name]}\n${h.value}` : h.value;
  }
  return out;
}

type RequestBody = chrome.webRequest.OnBeforeRequestDetails["requestBody"];

function decodeBody(body: RequestBody): string | null {
  if (!body) return null;
  if (body.formData) {
    const params = new URLSearchParams();
    for (const [k, values] of Object.entries(body.formData)) {
      for (const v of values) if (typeof v === "string") params.append(k, v);
    }
    return params.toString();
  }
  const raw = body.raw?.[0]?.bytes;
  if (!raw) return null;
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(raw);
  } catch {
    return null; // binary upload
  }
}

export class WebRequestCapture {
  private pending = new Map<string, { event: ExchangeEvent; started: number }>();
  private bodies = new Map<string, string | null>();

  constructor(
    private queue: EventQueue,
    private enabled: () => string[],
    private follow: Follow,
  ) {
    const filter = { urls: ["<all_urls>"], types: TYPES };
    const wr = chrome.webRequest;

    wr.onBeforeRequest.addListener(
      (d) => {
        if (!this.captured(d.url) && !(d.type === "main_frame" && this.follow(d.tabId, d.url))) {
          if (d.type === "xmlhttprequest" && d.requestBody) {
            if (this.bodies.size >= MAX_PENDING) this.bodies.delete(this.bodies.keys().next().value!);
            this.bodies.set(d.requestId, decodeBody(d.requestBody));
          }
          return undefined;
        }
        this.track(d, decodeBody(d.requestBody));
        return undefined;
      },
      filter,
      ["requestBody"],
    );
    wr.onSendHeaders.addListener(
      (d) => {
        const headers = toHeaders(d.requestHeaders);
        const body = this.bodies.get(d.requestId) ?? null;
        this.bodies.delete(d.requestId);
        if (!this.pending.has(d.requestId) && "authorization" in headers && this.follow(d.tabId, d.url)) {
          this.track(d, body);
        }
        const p = this.pending.get(d.requestId);
        if (p) p.event.request_headers = headers;
      },
      filter,
      ["requestHeaders"],
    );
    wr.onCompleted.addListener(
      (d) => {
        const p = this.pending.get(d.requestId);
        if (!p) return;
        p.event.status = d.statusCode;
        p.event.response_headers = toHeaders(d.responseHeaders);
        p.event.mime_type = p.event.response_headers["content-type"]?.split(";")[0] ?? null;
        this.finish(d.requestId);
      },
      filter,
      ["responseHeaders"],
    );
    wr.onErrorOccurred.addListener((d) => {
      this.bodies.delete(d.requestId);
      const p = this.pending.get(d.requestId);
      if (!p) return;
      p.event.error = d.error.slice(0, 500);
      this.finish(d.requestId);
    }, filter);
  }

  private captured(url: string): boolean {
    const host = hostOf(url);
    return host !== null && matchAny(host, this.enabled()) !== null;
  }

  private track(d: { requestId: string; url: string; method: string; type: string; timeStamp: number }, body: string | null): void {
    if (this.pending.size >= MAX_PENDING) this.pending.delete(this.pending.keys().next().value!);
    this.pending.set(d.requestId, {
      started: performance.now(),
      event: {
        type: "exchange",
        url: d.url,
        method: d.method.toUpperCase(),
        request_headers: {},
        request_body: body,
        response_headers: {},
        resource_type: d.type === "xmlhttprequest" ? "XHR" : "Document",
        started_at: d.timeStamp / 1000,
      },
    });
  }

  private finish(id: string): void {
    const p = this.pending.get(id);
    if (!p) return;
    this.pending.delete(id);
    p.event.duration_ms = Math.max(0, performance.now() - p.started);
    this.queue.push(p.event);
  }
}
