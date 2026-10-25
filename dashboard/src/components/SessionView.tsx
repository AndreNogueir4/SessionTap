import { useEffect, useState } from "react";
import { api, type ExpiryState, type Health } from "../api";
import { ago, until } from "../format";
import { t, tx, type MessageKey } from "../i18n";

const STATE_LABEL: Record<ExpiryState, MessageKey> = {
  ok: "state.ok",
  expiring: "state.expiring",
  expired: "state.expired",
  session: "state.session",
  unknown: "state.unknown",
};

const SUMMARY: Record<Health["status"], [MessageKey, MessageKey]> = {
  ok: ["session.healthy", "session.ok"],
  warning: ["session.attention", "session.warning"],
  expired: ["session.expiredTitle", "session.expired"],
  empty: ["session.emptyTitle", "session.empty"],
};

function Secret({ value }: { value: string | undefined }) {
  const [copied, setCopied] = useState(false);
  if (value === undefined) return <span className="muted">••••••</span>;
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <span className="secret">
      <code title={value}>{value || t("common.empty")}</code>
      <button className="ghost" onClick={() => void copy()}>
        {t(copied ? "common.copied" : "common.copy")}
      </button>
    </span>
  );
}

export function SessionView({ domain }: { domain: string }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [reveal, setReveal] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    setReveal(false);
    setValues({});
    void api.health(domain).then(setHealth);
  }, [domain]);

  useEffect(() => {
    if (!reveal || !health) {
      setValues({});
      return;
    }
    void (async () => {
      const out: Record<string, string> = {};
      const session = await api.session(domain);
      for (const c of session.cookies) out[`cookie|${c.domain}|${c.name}`] = c.value;
      for (const token of health.tokens) {
        try {
          out[`token|${token.kind}`] = (await api.secret(domain, token.kind)).value;
        } catch {
          /* rotated away since the health check */
        }
      }
      setValues(out);
    })();
  }, [reveal, health, domain]);

  if (!health) return <p className="empty">{t("common.loading")}</p>;

  return (
    <div className="session">
      <div className={`health ${health.status}`}>
        <strong>{t(SUMMARY[health.status][0])}</strong>
        <span>{t(SUMMARY[health.status][1])}</span>
        <span className="muted small">
          {t("session.timing", { next: until(health.next_expiry), last: ago(health.last_activity) })}
        </span>
      </div>

      <h3>{t("session.useIt")}</h3>
      <pre className="cmd">{`import sessiontap

client = sessiontap.httpx_client("${domain}")
print(client.get("https://${domain}/").status_code)`}</pre>

      <label className="check reveal">
        <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />
        {t("session.reveal")}
      </label>

      <h3>{t("session.cookies", { n: health.cookies.length })}</h3>
      <table className="grid">
        <thead>
          <tr>
            <th>{t("col.name")}</th>
            <th>{t("col.value")}</th>
            <th>{t("col.domain")}</th>
            <th>{t("col.expires")}</th>
            <th>{t("col.state")}</th>
          </tr>
        </thead>
        <tbody>
          {health.cookies.map((c) => (
            <tr key={`${c.domain}|${c.name}`}>
              <td className="mono">{c.name}</td>
              <td>
                <Secret value={reveal ? values[`cookie|${c.domain}|${c.name}`] : undefined} />
              </td>
              <td>{c.domain}</td>
              <td>{c.expires ? until(c.expires) : "—"}</td>
              <td>
                <span className={`pill ${c.state}`}>{t(STATE_LABEL[c.state])}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>{t("session.tokens", { n: health.tokens.length })}</h3>
      <p className="muted small">
        {tx("session.tokensHelp", { code: <code key="code">sessiontap.secret("authorization")</code> })}
      </p>
      <table className="grid">
        <thead>
          <tr>
            <th>{t("col.kind")}</th>
            <th>{t("col.value")}</th>
            <th>{t("col.subject")}</th>
            <th>{t("col.expires")}</th>
            <th>{t("col.lastSeen")}</th>
          </tr>
        </thead>
        <tbody>
          {health.tokens.map((token) => (
            <tr key={token.id}>
              <td className="mono">{token.kind}</td>
              <td>
                <Secret value={reveal ? values[`token|${token.kind}`] : undefined} />
              </td>
              <td>{token.jwt ? (token.subject ?? "—") : <span className="muted">{t("session.notJwt")}</span>}</td>
              <td>
                {token.jwt ? (
                  <span className={`pill ${token.state}`}>
                    {token.expires ? until(token.expires) : t(STATE_LABEL[token.state])}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="muted">{ago(token.last_seen)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
