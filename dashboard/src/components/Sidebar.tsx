import type { Domain, Status } from "../api";
import { ago } from "../format";
import { LanguagePicker } from "./LanguagePicker";
import { t } from "../i18n";

interface Props {
  domains: Domain[];
  status: Status | null;
  selected: string | null;
  view: "domain" | "live" | "settings";
  onSelect: (domain: string) => void;
  onLive: () => void;
  onSettings: () => void;
}

export function Sidebar({ domains, status, selected, view, onSelect, onLive, onSettings }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/favicon.svg" alt="" width="22" height="22" />
        <span>SessionTap</span>
        {status && <small>v{status.version}</small>}
      </div>
      <nav>
        <button className={view === "live" ? "nav active" : "nav"} onClick={onLive}>
          {t("nav.live")}
        </button>
        <button className={view === "settings" ? "nav active" : "nav"} onClick={onSettings}>
          {t("nav.settings")}
        </button>
      </nav>
      <h2>{t("nav.sites")}</h2>
      {domains.length === 0 && (
        <p className="muted small">{t("sidebar.empty")}</p>
      )}
      <ul className="domains">
        {domains.map((d) => (
          <li key={d.domain}>
            <button
              className={selected === d.domain ? "domain active" : "domain"}
              onClick={() => onSelect(d.domain)}
              title={t(d.capture ? "sidebar.capturing" : "sidebar.notCapturing")}
            >
              <span className={d.capture ? "dot on" : "dot"} aria-hidden />
              <span className="name">{d.domain}</span>
              <span className="meta">
                {t("sidebar.meta", { n: d.requests, when: ago(d.last_seen) })}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {status && status.key_backend !== "keyring" && (
        <p className="warning small">{t("sidebar.keyFile")}</p>
      )}
      <LanguagePicker />
    </aside>
  );
}
