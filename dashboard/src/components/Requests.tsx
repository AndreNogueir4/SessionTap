import { useEffect, useState } from "react";
import { api, type RequestSummary } from "../api";
import { ago, statusClass } from "../format";
import { RequestDetailView } from "./RequestDetail";
import { t } from "../i18n";

export function Requests({ domain }: { domain: string }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<RequestSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [apiOnly, setApiOnly] = useState(true);

  useEffect(() => {
    setSelected(null);
  }, [domain]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api.requests(domain, q).then((r) => {
        if (!cancelled) setItems(r);
      });
    const timer = setTimeout(() => void load(), 200);
    const poll = setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(poll);
    };
  }, [domain, q]);

  const shown = apiOnly ? items.filter((r) => r.resource_type !== "Document") : items;

  return (
    <div className={selected === null ? "split" : "split open"}>
      <section className="list">
        <div className="toolbar">
          <input
            type="search"
            placeholder={t("requests.filter")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <label className="check">
            <input type="checkbox" checked={apiOnly} onChange={(e) => setApiOnly(e.target.checked)} />
            {t("requests.apiOnly")}
          </label>
        </div>
        {shown.length === 0 ? (
          <p className="empty">{t("requests.empty", { domain })}</p>
        ) : (
          <table className="requests">
            <thead>
              <tr>
                <th>{t("col.method")}</th>
                <th>{t("col.path")}</th>
                <th>{t("col.status")}</th>
                <th>{t("col.when")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={r.id}
                  className={selected === r.id ? "selected" : ""}
                  onClick={() => setSelected(r.id)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setSelected(r.id)}
                >
                  <td className="method">{r.method}</td>
                  <td className="path" title={`${r.host}${r.path}`}>
                    {r.host !== domain && <span className="host">{r.host}</span>}
                    {r.path}
                  </td>
                  <td>
                    <span className={statusClass(r.status)}>{r.error ? "ERR" : (r.status ?? "…")}</span>
                  </td>
                  <td className="muted">{ago(r.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {selected !== null && <RequestDetailView id={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
