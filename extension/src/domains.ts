// Mirrors core/src/sessiontap/domains.py. The daemon re-checks everything; this copy
// only avoids sending events that would be dropped anyway.

export function siteOf(url: string | undefined): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
  const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
  return host.startsWith("www.") ? host.slice(4) : host;
}

export function hostOf(url: string): string | null {
  try {
    return new URL(url).hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return null;
  }
}

export function matches(host: string, domain: string): boolean {
  return host === domain || host.endsWith("." + domain);
}

export function matchAny(host: string, domains: Iterable<string>): string | null {
  let best: string | null = null;
  for (const d of domains) {
    if (matches(host, d) && (best === null || d.length > best.length)) best = d;
  }
  return best;
}

/** Host-permission patterns for a domain and its subdomains. */
export function originPatterns(domain: string): string[] {
  return [`https://${domain}/*`, `https://*.${domain}/*`, `http://${domain}/*`, `http://*.${domain}/*`];
}

const SECOND_LEVEL = /^(com|net|org|gov|edu|co|ac|ne|or|go|mil|nom|gob|gv|ltd|plc|sch)$/;
const SHARED_HOSTING = new Set([
  "github.io",
  "gitlab.io",
  "vercel.app",
  "netlify.app",
  "pages.dev",
  "workers.dev",
  "herokuapp.com",
  "web.app",
  "firebaseapp.com",
  "appspot.com",
  "blogspot.com",
  "azurewebsites.net",
  "cloudfront.net",
  "amazonaws.com",
  "onrender.com",
  "fly.dev",
  "ngrok.io",
  "ngrok-free.app",
  "trycloudflare.com",
]);

/**
 * The site a host belongs to (app.example.com -> example.com, www.globo.com.br -> globo.com.br),
 * so a recording follows a login across subdomains. A heuristic, not the full public suffix list:
 * on shared hosting (github.io, vercel.app…) and for IPs it keeps the exact host.
 */
export function siteKey(host: string): string {
  const h = host.toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
  const labels = h.split(".");
  if (labels.length <= 2 || /^[\d.]+$/.test(h) || h.includes(":")) return h;
  const last2 = labels.slice(-2).join(".");
  if (SHARED_HOSTING.has(last2)) return h;
  if (labels.at(-1)!.length === 2 && SECOND_LEVEL.test(labels.at(-2)!)) return labels.slice(-3).join(".");
  return last2;
}
