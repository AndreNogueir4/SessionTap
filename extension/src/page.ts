// Cookies, Web Storage and the browser profile (user agent, languages, screen…)
// for enabled sites. Nothing is spoofed or modified: SessionTap only observes.

import { matchAny } from "./domains";
import type { EventQueue } from "./queue";
import type { CookieData } from "./types";

const COLLECT_EVERY_MS = 3_000;

export function toCookie(c: chrome.cookies.Cookie): CookieData {
  return {
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    secure: c.secure,
    http_only: c.httpOnly,
    same_site: c.sameSite ?? null,
    expires: c.session ? null : (c.expirationDate ?? null),
  };
}

/** Runs inside the page (isolated world). Must be self-contained. */
function collect(maxValue: number) {
  const read = (s: Storage) => {
    const out: Record<string, string> = {};
    for (let i = 0; i < Math.min(s.length, 500); i++) {
      const key = s.key(i);
      if (key === null) continue;
      const value = s.getItem(key) ?? "";
      if (key.length <= 1024 && value.length <= maxValue) out[key] = value;
    }
    return out;
  };
  let local: Record<string, string> = {};
  let session: Record<string, string> = {};
  try {
    local = read(localStorage);
    session = read(sessionStorage);
  } catch {
    /* storage disabled for this origin */
  }
  const nav = navigator as Navigator & { deviceMemory?: number };
  return {
    origin: location.origin,
    local,
    session,
    fingerprint: {
      userAgent: nav.userAgent,
      language: nav.language,
      languages: nav.languages.join(","),
      platform: nav.platform,
      hardwareConcurrency: nav.hardwareConcurrency,
      deviceMemory: nav.deviceMemory ?? null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      screenWidth: screen.width,
      screenHeight: screen.height,
      colorDepth: screen.colorDepth,
      devicePixelRatio: devicePixelRatio,
    },
  };
}

export class PageCollector {
  private lastRun = new Map<string, number>();

  constructor(
    private queue: EventQueue,
    private enabled: () => string[],
  ) {
    chrome.cookies.onChanged.addListener(({ removed, cookie }) => {
      const host = cookie.domain.replace(/^\./, "").toLowerCase();
      const domains = this.enabled();
      // Cookie for an enabled domain/subdomain, or a parent cookie sent to one.
      if (!matchAny(host, domains) && !domains.some((d) => d.endsWith("." + host))) return;
      this.queue.push({ type: "cookie", removed, cookie: toCookie(cookie) });
    });
  }

  async snapshotCookies(domain: string): Promise<void> {
    const [own, sent] = await Promise.all([
      chrome.cookies.getAll({ domain }),
      chrome.cookies.getAll({ url: `https://${domain}/` }),
    ]);
    const unique = new Map<string, chrome.cookies.Cookie>();
    for (const c of [...own, ...sent]) unique.set(`${c.domain}|${c.name}|${c.path}`, c);
    this.queue.push({ type: "cookies", domain, cookies: [...unique.values()].map(toCookie) });
  }

  async collectTab(tabId: number, url: string | undefined, maxValue: number): Promise<void> {
    const key = `${tabId}|${url ? new URL(url).origin : ""}`;
    const now = Date.now();
    if (now - (this.lastRun.get(key) ?? 0) < COLLECT_EVERY_MS) return;
    this.lastRun.set(key, now);
    try {
      const [result] = await chrome.scripting.executeScript({
        target: { tabId },
        func: collect,
        args: [Math.min(maxValue, 64 * 1024)],
      });
      const data = result?.result as ReturnType<typeof collect> | undefined;
      if (!data) return;
      this.queue.push({ type: "storage", origin: data.origin, local: data.local, session: data.session });
      this.queue.push({ type: "fingerprint", origin: data.origin, data: data.fingerprint });
    } catch {
      /* no permission for this frame or the tab is gone */
    }
  }

  forget(tabId: number): void {
    for (const key of this.lastRun.keys()) if (key.startsWith(`${tabId}|`)) this.lastRun.delete(key);
  }
}
