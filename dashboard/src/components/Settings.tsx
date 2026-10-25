import { useEffect, useState } from "react";
import { api, type Domain, type Settings as SettingsData, type Status } from "../api";
import { bytes } from "../format";
import { t, tx, type MessageKey } from "../i18n";
import { Blocklist } from "./Blocklist";

const COUNT_KEYS: Record<string, MessageKey> = {
  domains: "count.domains",
  requests: "count.requests",
  cookies: "count.cookies",
  tokens: "count.tokens",
  storage: "count.storage",
};

interface Props {
  domains: Domain[];
  status: Status | null;
  onChange: () => Promise<void>;
}

export function Settings({ domains, status, onChange }: Props) {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [retention, setRetention] = useState(7);
  const [html, setHtml] = useState(true);
  const [maxBody, setMaxBody] = useState(512);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    void api.settings().then((s) => {
      setSettings(s);
      setRetention(s.retention_days);
      setHtml(s.capture_html);
      setMaxBody(s.max_body_kb);
    });
  }, []);

  async function save(section: string, patch: Partial<SettingsData>) {
    const s = await api.saveSettings(patch);
    setSettings(s);
    setSaved(section);
    setTimeout(() => setSaved(null), 1500);
    await onChange();
  }

  const captureChanged = !!settings && (html !== settings.capture_html || maxBody !== settings.max_body_kb);

  async function stop(domain: string) {
    await api.setCapture(domain, false);
    await onChange();
  }

  async function purge(domain: string) {
    if (!confirm(t("settings.confirmDelete", { domain }))) return;
    await api.purge(domain);
    await onChange();
  }

  return (
    <div className="settings">
      <header className="page-header">
        <h1>{t("settings.title")}</h1>
      </header>

      {status && (
        <section className="card">
          <h3>{t("settings.vault")}</h3>
          <p>
            {bytes(status.vault_bytes)} · {Object.entries(status.counts)
              .map(([k, v]) => `${v} ${COUNT_KEYS[k] ? t(COUNT_KEYS[k]) : k}`)
              .join(" · ")}
          </p>
          {status.key_backend === "keyring" ? (
            <p className="ok">{t("settings.keyring")}</p>
          ) : (
            <p className="warning">{tx("settings.keyFile", { cmd: <code key="cmd">sessiontap purge --all</code> })}</p>
          )}
        </section>
      )}

      <section className="card">
        <h3>{t("settings.retention")}</h3>
        <p className="muted">{t("settings.retentionHelp")}</p>
        <label className="inline">
          <input
            type="number"
            min={1}
            max={365}
            value={retention}
            onChange={(e) => setRetention(Number(e.target.value))}
          />{" "}
          {t("settings.days")}
        </label>{" "}
        <button
          onClick={() => void save("retention", { retention_days: retention })}
          disabled={!settings || retention === settings.retention_days}
        >
          {t(saved === "retention" ? "settings.saved" : "settings.save")}
        </button>
      </section>

      {settings && (
        <section className="card">
          <h3>{t("settings.capture")}</h3>
          {settings.locked && (
            <p className="warning small">
              {tx("blocklist.locked", { setting: <code key="setting">[capture] locked = true</code> })}
            </p>
          )}
          <p>
            <label className="check">
              <input
                type="checkbox"
                checked={html}
                disabled={settings.locked}
                onChange={(e) => setHtml(e.target.checked)}
              />
              {t("settings.html")}
            </label>
          </p>
          <p className="muted small">{t("settings.htmlHelp")}</p>
          <label className="inline">
            {t("settings.maxBody")}{" "}
            <input
              type="number"
              min={0}
              max={4096}
              value={maxBody}
              disabled={settings.locked}
              onChange={(e) => setMaxBody(Number(e.target.value))}
            />{" "}
            KB
          </label>{" "}
          <button
            onClick={() => void save("capture", { capture_html: html, max_body_kb: maxBody })}
            disabled={settings.locked || !captureChanged || maxBody < 0 || maxBody > 4096}
          >
            {t(saved === "capture" ? "settings.saved" : "settings.save")}
          </button>
        </section>
      )}

      <section className="card">
        <h3>{t("settings.sites")}</h3>
        <p className="muted">{t("settings.sitesHelp")}</p>
        <table className="grid">
          <tbody>
            {domains.map((d) => (
              <tr key={d.domain}>
                <td>{d.domain}</td>
                <td>{d.capture ? <span className="pill ok">{t("settings.capturing")}</span> : <span className="pill">{t("settings.off")}</span>}</td>
                <td className="actions">
                  {d.capture && <button className="ghost" onClick={() => void stop(d.domain)}>{t("settings.stop")}</button>}
                  <button className="danger" onClick={() => void purge(d.domain)}>{t("settings.delete")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <Blocklist onChange={onChange} />
    </div>
  );
}
