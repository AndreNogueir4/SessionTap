import { useEffect, useState } from "react";
import { api, download, type RequestDetail } from "../api";
import { bytes, prettyBody, statusClass } from "../format";
import { CodeView } from "./CodeView";
import { t } from "../i18n";

function HeaderTable({ headers }: { headers: Record<string, string> }) {
  const entries = Object.entries(headers);
  if (entries.length === 0) return <p className="muted">{t("common.none")}</p>;
  return (
    <table className="kv">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const BODY_PREVIEW = 200_000;

export function RequestDetailView({ id, onClose }: { id: number; onClose: () => void }) {
  const [reveal, setReveal] = useState(false);
  const [r, setR] = useState<RequestDetail | null>(null);

  useEffect(() => {
    setReveal(false);
  }, [id]);

  useEffect(() => {
    void api.request(id, reveal, BODY_PREVIEW).then(setR);
  }, [id, reveal]);

  if (!r) return <section className="detail">{t("common.loading")}</section>;

  return (
    <section className="detail">
      <div className="detail-head">
        <span className="method">{r.method}</span>
        <span className={statusClass(r.status)}>{r.status ?? "…"}</span>
        <button className="ghost" onClick={onClose} aria-label={t("common.close")}>
          ✕
        </button>
      </div>
      <p className="url">{r.url}</p>
      {r.error && <p className="error">{t("detail.failed", { error: r.error })}</p>}

      <label className="check reveal">
        <input type="checkbox" checked={reveal} onChange={(e) => setReveal(e.target.checked)} />
        {t("detail.reveal")}
      </label>

      <h3>{t("detail.code")}</h3>
      <CodeView id={r.id} />

      <h3>{t("detail.requestHeaders")}</h3>
      <HeaderTable headers={r.request_headers} />
      {r.request_body && (
        <>
          <h3>{t("detail.requestBody")}</h3>
          <pre className="body">{prettyBody(r.request_body)}</pre>
        </>
      )}

      <h3>{t("detail.responseHeaders")}</h3>
      <HeaderTable headers={r.response_headers} />
      <h3>
        {t("detail.responseBody")} {r.body_truncated && <span className="badge">{t("detail.truncated")}</span>}
      </h3>
      {r.response_body ? (
        <>
          {r.response_body_size > r.response_body.length && (
            <p className="muted small">
              {t("detail.preview", { shown: bytes(r.response_body.length), total: bytes(r.response_body_size) })}
            </p>
          )}
          <button
            className="ghost"
            onClick={() =>
              void download(
                `/v1/requests/${r.id}/body?part=response&reveal=${reveal}`,
                `request-${r.id}.${r.mime_type?.includes("html") ? "html" : "txt"}`,
              )
            }
          >
            {t("detail.download")}
          </button>
          <pre className="body">
            {r.response_body_size > r.response_body.length ? r.response_body : prettyBody(r.response_body)}
          </pre>
        </>
      ) : (
        <p className="muted">{t("detail.noBody")}</p>
      )}
    </section>
  );
}
