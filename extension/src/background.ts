// Background worker: decides which tabs are observed and relays events to the daemon.
//
// The list of enabled domains lives in the daemon (so the CLI, dashboard and extension
// agree). Recording a tab enables its site and then follows the flow: every site the tab
// navigates to, or calls with an Authorization header, is added to the recording until the
// user stops it or closes the tab. Blocklisted sites are never added.

import { CdpCapture } from "./cdp";
import { hostOf, matchAny, siteKey, siteOf } from "./domains";
import { t } from "./i18n";
import { NativeBridge } from "./native";
import { PageCollector } from "./page";
import { EventQueue } from "./queue";
import type { CaptureState, Counts, PopupRequest, PopupStatus } from "./types";
import { WebRequestCapture } from "./webrequest";

declare const __BROWSER__: "chromium" | "firefox";

const ALL_SITES = ["https://*/*", "http://*/*"];
const STORE_KEY = "recordings";

const bridge = new NativeBridge();
const queue = new EventQueue(bridge);
let state: CaptureState = { domains: [], blocklist: [], max_body_bytes: 512 * 1024 };
const enabled = () => state.domains;
const snapshotted = new Set<string>();

// tabId -> sites this recording enabled (and turns off again when it stops)
const recordings = new Map<number, string[]>();
const loaded = chrome.storage.session
  .get(STORE_KEY)
  .then((stored) => {
    for (const [tabId, sites] of (stored[STORE_KEY] ?? []) as [number, string[]][]) recordings.set(tabId, sites);
  })
  .catch(() => undefined);

function persist(): void {
  void chrome.storage.session.set({ [STORE_KEY]: [...recordings] }).catch(() => undefined);
}

const isBlocked = (host: string) => matchAny(host, state.blocklist) !== null;

/** Called by the capture layers for a request to a site that is not enabled yet. */
function follow(tabId: number, url: string): boolean {
  const added = recordings.get(tabId);
  const host = hostOf(url);
  if (!added || !host || !/^https?:/.test(url) || isBlocked(host)) return false;
  if (matchAny(host, state.domains)) return true;
  const site = siteKey(host);
  state.domains = [...state.domains, site];
  added.push(site);
  persist();
  void bridge.setCapture(site, true);
  return true;
}

const cdp = __BROWSER__ === "chromium" ? new CdpCapture(queue, enabled, () => state, follow) : null;
if (__BROWSER__ === "firefox") new WebRequestCapture(queue, enabled, follow);
const pages = new PageCollector(queue, enabled);

function isCaptured(url: string | undefined): boolean {
  const host = url ? hostOf(url) : null;
  return host !== null && matchAny(host, state.domains) !== null && !isBlocked(host);
}

async function setBadge(tabId: number, on: boolean): Promise<void> {
  try {
    await chrome.action.setBadgeText({ tabId, text: on ? "REC" : "" });
    if (on) await chrome.action.setBadgeBackgroundColor({ tabId, color: "#c62828" });
  } catch {
    /* tab closed */
  }
}

async function syncTab(tab: chrome.tabs.Tab): Promise<void> {
  if (tab.id === undefined) return;
  const web = /^https?:/.test(tab.url ?? "");
  const captured = isCaptured(tab.url);
  if ((recordings.has(tab.id) && web) || captured) {
    await cdp?.attach(tab.id);
    await setBadge(tab.id, true);
    if (captured && tab.status === "complete") await pages.collectTab(tab.id, tab.url, state.max_body_bytes);
  } else {
    await cdp?.detach(tab.id);
    await setBadge(tab.id, false);
  }
}

async function syncAllTabs(): Promise<void> {
  for (const tab of await chrome.tabs.query({})) await syncTab(tab);
}

bridge.onState = (next) => {
  state = next;
  void (async () => {
    await loaded;
    await syncAllTabs();
    for (const d of state.domains) {
      if (snapshotted.has(d)) continue;
      snapshotted.add(d);
      await pages.snapshotCookies(d);
    }
    for (const d of [...snapshotted]) if (!state.domains.includes(d)) snapshotted.delete(d);
  })();
};

chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if (info.url !== undefined || info.status !== undefined) void syncTab(tab);
});
chrome.tabs.onRemoved.addListener((tabId) => {
  void cdp?.detach(tabId);
  pages.forget(tabId);
  if (recordings.has(tabId)) void stop(tabId, null);
});

async function record(tabId: number, host: string): Promise<{ ok: boolean; error?: string }> {
  await loaded;
  if (isBlocked(host)) return { ok: false, error: t("blocklisted") };
  const added: string[] = [];
  if (!matchAny(host, state.domains)) {
    const site = siteKey(host);
    const result = await bridge.setCapture(site, true);
    if (!result.ok) return result;
    added.push(site);
  }
  recordings.set(tabId, [...(recordings.get(tabId) ?? []), ...added]);
  persist();
  await syncAllTabs();
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (tab?.status === "complete") await pages.collectTab(tabId, tab.url, state.max_body_bytes);
  return { ok: true };
}

async function stop(tabId: number, host: string | null): Promise<{ ok: boolean; error?: string }> {
  await loaded;
  const targets = new Set(recordings.get(tabId) ?? []);
  const current = host ? matchAny(host, state.domains) : null;
  if (current) targets.add(current);
  recordings.delete(tabId);
  persist();
  return disable([...targets]);
}

async function disable(domains: string[]): Promise<{ ok: boolean; error?: string }> {
  let error: string | undefined;
  for (const d of domains) {
    const result = await bridge.setCapture(d, false);
    if (!result.ok) error = result.error;
    for (const [tabId, added] of recordings) recordings.set(tabId, added.filter((s) => s !== d));
  }
  persist();
  await bridge.refresh();
  await syncAllTabs();
  return error ? { ok: false, error } : { ok: true };
}

async function flowCounts(sites: string[]): Promise<Counts> {
  const total: Counts = { requests: 0, cookies: 0, tokens: 0, storage: 0 };
  for (const site of sites) {
    const counts = (await bridge.siteSummary(site))?.counts;
    if (!counts) continue;
    for (const k of Object.keys(total) as (keyof Counts)[]) total[k] += counts[k];
  }
  return total;
}

async function status(tabId: number | null, host: string | null): Promise<PopupStatus> {
  await loaded;
  await bridge.refresh();
  const domain = host ? (siteOf(`https://${host}/`) ?? null) : null;
  await queue.flush();
  const summary = domain && bridge.connection === "connected" ? await bridge.siteSummary(domain) : null;
  const flow = tabId === null ? undefined : recordings.get(tabId);
  return {
    flowCounts: flow && flow.length > 1 ? await flowCounts(flow) : null,
    connection: bridge.connection,
    error: bridge.lastError,
    domain,
    captured: domain !== null && matchAny(domain, state.domains) !== null,
    blocked: domain !== null && isBlocked(domain),
    recording: flow !== undefined,
    flow: flow ?? [],
    permission: await chrome.permissions.contains({ origins: ALL_SITES }),
    capturedDomains: state.domains,
    sent: queue.sent,
    summary,
  };
}

chrome.runtime.onMessage.addListener((msg: PopupRequest, sender, sendResponse) => {
  // Only our own extension pages (the popup) may drive the worker. The extension has no
  // content scripts and no externally_connectable, so web pages cannot reach this anyway.
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(""))) {
    return false;
  }
  const work = async () => {
    switch (msg.type) {
      case "status":
        return status(msg.tabId, msg.host);
      case "record":
        return record(msg.tabId, msg.host);
      case "stop":
        return stop(msg.tabId, msg.host);
      case "remove_domain":
        return disable([msg.domain]);
      case "open_dashboard": {
        const login = await bridge.loginCode();
        if (!login) return { ok: false };
        await chrome.tabs.create({ url: `http://127.0.0.1:${login.port}/#code=${login.code}` });
        return { ok: true };
      }
    }
  };
  void work().then(sendResponse);
  return true;
});

bridge.start();
// Pick up changes made from the CLI or the dashboard.
setInterval(() => void bridge.refresh(), 30_000);
