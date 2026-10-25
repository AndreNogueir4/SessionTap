import { useEffect, useState } from "react";
import { subscribe, type LiveEvent } from "../api";
import { statusClass } from "../format";
import { t } from "../i18n";

const MAX = 300;

function describe(e: LiveEvent): string {
  switch (e.type) {
    case "request":
      return `${e.method} ${e.path}`;
    case "cookie":
      return t(e.removed ? "live.cookieRemoved" : "live.cookieUpdated", { name: String(e.name) });
    case "cookies":
      return t("live.cookieSnapshot", { n: String(e.count) });
    case "storage":
      return t("live.storage", { origin: String(e.origin) });
    case "fingerprint":
      return t("live.fingerprint");
    case "capture":
      return t(e.capture ? "live.captureOn" : "live.captureOff");
    case "purged":
      return t("live.purged");
    default:
      return e.type;
  }
}

export function LiveFeed({ onOpen }: { onOpen: (domain: string) => void }) {
  const [events, setEvents] = useState<(LiveEvent & { at: number })[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    subscribe((e) => setEvents((prev) => [{ ...e, at: Date.now() }, ...prev].slice(0, MAX)), controller.signal);
    return () => controller.abort();
  }, []);

  return (
    <div>
      <header className="page-header">
        <h1>{t("live.title")}</h1>
        <p className="muted">{t("live.subtitle")}</p>
      </header>
      {events.length === 0 ? (
        <p className="empty">{t("live.waiting")}</p>
      ) : (
        <ul className="feed">
          {events.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <time>{new Date(e.at).toLocaleTimeString()}</time>
              {e.domain ? (
                <button className="link" onClick={() => onOpen(e.domain!)}>
                  {e.domain}
                </button>
              ) : (
                <span />
              )}
              <span className="mono">{describe(e)}</span>
              {e.type === "request" && <span className={statusClass(e.status ?? null)}>{e.status ?? ""}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
