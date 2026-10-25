// Shapes shared by the background worker, the popup and the daemon's /v1/ingest schema.

export type Headers = Record<string, string>;

export interface ExchangeEvent {
  type: "exchange";
  url: string;
  method: string;
  request_headers: Headers;
  request_body?: string | null;
  status?: number | null;
  response_headers: Headers;
  response_body?: string | null;
  mime_type?: string | null;
  resource_type?: string | null;
  started_at?: number;
  duration_ms?: number;
  error?: string | null;
}

export interface CookieData {
  name: string;
  value: string;
  domain: string;
  path: string;
  secure: boolean;
  http_only: boolean;
  same_site: string | null;
  expires: number | null;
}

export type CaptureEvent =
  | ExchangeEvent
  | { type: "cookie"; removed: boolean; cookie: CookieData }
  | { type: "cookies"; domain: string; cookies: CookieData[] }
  | { type: "storage"; origin: string; local: Record<string, string>; session: Record<string, string> }
  | { type: "fingerprint"; origin: string; data: Record<string, string | number | boolean | null> };

export interface CaptureState {
  domains: string[];
  blocklist: string[];
  max_body_bytes: number;
  capture_html?: boolean;
  max_html_bytes?: number;
  port?: number;
}

export type Connection = "connected" | "daemon_offline" | "host_missing" | "connecting";

// popup -> background
export type PopupRequest =
  | { type: "status"; tabId: number | null; host: string | null }
  | { type: "record"; tabId: number; host: string }
  | { type: "stop"; tabId: number; host: string | null }
  | { type: "remove_domain"; domain: string }
  | { type: "open_dashboard" };

export interface RecentRequest {
  id: number;
  host: string;
  method: string;
  path: string;
  status: number | null;
  error: string | null;
  started_at: number;
}

export type HealthStatus = "ok" | "warning" | "expired" | "empty";

export type ExpiryState = "ok" | "expiring" | "expired" | "session" | "unknown";

export interface Counts {
  requests: number;
  cookies: number;
  tokens: number;
  storage: number;
}

export interface SiteSummary {
  domain: string;
  known: boolean;
  capture?: boolean;
  last_seen?: number | null;
  counts?: Counts;
  health?: { status: HealthStatus; next_expiry: number | null };
  cookies?: { name: string; domain: string; expires: number | null; state: ExpiryState }[];
  tokens?: { kind: string; jwt: boolean; expires: number | null; state: ExpiryState }[];
  recent?: RecentRequest[];
}

export interface PopupStatus {
  connection: Connection;
  error: string | null;
  domain: string | null;
  captured: boolean;
  blocked: boolean;
  recording: boolean;
  flow: string[];
  flowCounts: Counts | null;
  permission: boolean;
  capturedDomains: string[];
  sent: number;
  summary: SiteSummary | null;
}
