import { hostOf } from "./domains";
import { localize, t } from "./i18n";
import type { ExpiryState, HealthStatus, PopupRequest, PopupStatus, RecentRequest, SiteSummary } from "./types";

const REFRESH_MS = 2000;
const ALL_SITES = ["https://*/*", "http://*/*"];

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const CONNECTION_TEXT: Record<PopupStatus["connection"], string> = {
  connected: "connConnected",
  connecting: "connConnecting",
  daemon_offline: "connDaemonOffline",
  host_missing: "connHostMissing",
};

const HEALTH_TEXT: Record<HealthStatus, string> = {
  ok: "healthOk",
  warning: "healthWarning",
  expired: "healthExpired",
  empty: "healthEmpty",
};

interface Tab {
  id: number | null;
  host: string | null;
}

function send<T>(msg: PopupRequest): Promise<T> {
  return chrome.runtime.sendMessage(msg) as Promise<T>;
}

async function currentTab(): Promise<Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return { id: tab?.id ?? null, host: tab?.url && /^https?:/.test(tab.url) ? hostOf(tab.url) : null };
}

function ago(ts: number | null | undefined): string {
  if (!ts) return t("never");
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return t("ago", `${s}s`);
  if (s < 3600) return t("ago", `${Math.round(s / 60)}m`);
  if (s < 86400) return t("ago", `${Math.round(s / 3600)}h`);
  return t("ago", `${Math.round(s / 86400)}d`);
}

function until(ts: number): string {
  const s = Math.round(ts - Date.now() / 1000);
  if (s <= 0) return t("expired");
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

function expiryLabel(expires: number | null, state: ExpiryState): string {
  if (state === "session") return t("browserSession");
  if (state === "unknown") return "—";
  return expires ? until(expires) : state;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function statusClass(r: RecentRequest): string {
  if (r.error || r.status === null) return "code err";
  if (r.status >= 500) return "code s5";
  if (r.status >= 400) return "code s4";
  if (r.status >= 300) return "code s3";
  return "code s2";
}

function recentItem(r: RecentRequest, domain: string): HTMLLIElement {
  const li = document.createElement("li");
  const path = el("span", "path", r.host === domain ? r.path : `${r.host}${r.path}`);
  path.title = `${r.host}${r.path}`;
  li.append(el("span", "method", r.method), path, el("span", statusClass(r), r.error ? "ERR" : String(r.status ?? "…")));
  return li;
}

function credentialItem(name: string, where: string, expires: number | null, state: ExpiryState): HTMLLIElement {
  const li = document.createElement("li");
  const label = el("span", "name", name);
  label.title = where ? `${name} (${where})` : name;
  if (where) label.append(el("span", "where", where));
  li.append(label, el("span", `exp-${state}`, expiryLabel(expires, state)));
  return li;
}

function renderSummary(s: SiteSummary | null): void {
  const section = $("summary");
  if (!s?.known || !s.counts || !s.health) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  $("count-requests").textContent = String(s.counts.requests);
  $("count-cookies").textContent = String(s.counts.cookies);
  $("count-tokens").textContent = String(s.counts.tokens);
  $("count-storage").textContent = String(s.counts.storage);
  $("health").dataset.status = s.health.status;
  const expiry = s.health.next_expiry ? ` · ${t("nextExpiry", until(s.health.next_expiry))}` : "";
  $("health-text").textContent = t(HEALTH_TEXT[s.health.status]) + expiry;
  $("last-seen").textContent = t("lastActivity", ago(s.last_seen));
  const cookies = s.cookies ?? [];
  const tokens = s.tokens ?? [];
  $("cookies-n").textContent = `(${cookies.length})`;
  $("cookies").replaceChildren(...cookies.map((c) => credentialItem(c.name, c.domain, c.expires, c.state)));
  $("cookies-box").hidden = cookies.length === 0;
  $("tokens-n").textContent = `(${tokens.length})`;
  $("tokens").replaceChildren(
    ...tokens.map((t) => credentialItem(t.kind, t.jwt ? "JWT" : "", t.expires, t.jwt ? t.state : "unknown")),
  );
  $("tokens-box").hidden = tokens.length === 0;
  const recent = s.recent ?? [];
  $("recent").replaceChildren(...recent.map((r) => recentItem(r, s.domain)));
  $("recent-empty").hidden = recent.length > 0;
}

function domainItem(domain: string): HTMLLIElement {
  const li = document.createElement("li");
  const remove = el("button", "", "×");
  remove.type = "button";
  remove.title = t("removeDomain", domain);
  remove.addEventListener("click", async () => {
    await send({ type: "remove_domain", domain });
    await refresh();
  });
  li.append(el("span", "", domain), remove);
  return li;
}

function render(s: PopupStatus): void {
  $("connection").textContent = t(CONNECTION_TEXT[s.connection]);
  $("connection").dataset.state = s.connection;
  $("sent").textContent = String(s.sent);
  $("domains").replaceChildren(...s.capturedDomains.map(domainItem));
  $("none").hidden = s.capturedDomains.length > 0;
  $("permission").hidden = s.permission;

  const toggle = $<HTMLButtonElement>("toggle");
  const note = $("note");
  const active = s.recording || s.captured;
  $("rec").hidden = !active;
  $("flow").hidden = !s.recording || s.flow.length === 0;
  $("flow").replaceChildren(...s.flow.map((d) => el("span", "chip", d)));
  const total = s.flowCounts;
  $("flow-total").hidden = !s.recording || !total;
  if (total) {
    $("flow-total").textContent = t("flowTotal", s.flow.length, total.requests, total.cookies, total.tokens, total.storage);
  }
  if (!s.domain) {
    $("site").textContent = t(s.recording ? "recordingThisTab" : "cannotCapture");
    toggle.hidden = !s.recording;
    toggle.textContent = t("stopRecording");
    toggle.dataset.captured = "true";
    note.textContent = "";
    renderSummary(null);
    return;
  }
  $("site").textContent = s.domain;
  toggle.hidden = false;
  toggle.disabled = s.connection !== "connected" || !s.permission || (s.blocked && !active);
  toggle.textContent = t(s.recording ? "stopRecording" : s.captured ? "stopCapturing" : "recordTab");
  toggle.dataset.captured = String(active);
  if (s.blocked) note.textContent = t("noteBlocked");
  else if (s.recording) note.textContent = t("noteRecording");
  else if (s.captured) note.textContent = t("noteCaptured");
  else if (s.summary?.known) note.textContent = t("noteKept");
  else note.textContent = "";
  renderSummary(s.summary);
}

async function refresh(): Promise<PopupStatus> {
  const tab = await currentTab();
  const s = await send<PopupStatus>({ type: "status", tabId: tab.id, host: tab.host });
  render(s);
  return s;
}

$("permission").addEventListener("click", async () => {
  // Asked once; after that recording never prompts again.
  await chrome.permissions.request({ origins: ALL_SITES });
  await refresh();
});

$("toggle").addEventListener("click", async () => {
  const tab = await currentTab();
  const s = await refresh();
  if (tab.id === null) return;
  const result =
    s.recording || s.captured
      ? await send<{ ok: boolean; error?: string }>({ type: "stop", tabId: tab.id, host: tab.host })
      : tab.host
        ? await send<{ ok: boolean; error?: string }>({ type: "record", tabId: tab.id, host: tab.host })
        : { ok: true };
  await refresh();
  if (!result.ok) $("note").textContent = result.error ?? t("failed");
});

$("dashboard").addEventListener("click", async () => {
  const result = await send<{ ok: boolean }>({ type: "open_dashboard" });
  if (result.ok) window.close();
  else $("note").textContent = t("daemonUnreachable");
});

localize(document);
void refresh();
setInterval(() => void refresh(), REFRESH_MS);
