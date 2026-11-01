import { useEffect, useState } from "react";
import { api, download, type RequestDetail } from "../api";
import { bytes, prettyBody, statusClass } from "../format";
import { CodeView } from "./CodeView";
import { HtmlView } from "./HtmlView";
import { JsonTree, parseJson } from "./JsonTree";
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

function JsonBody({ body }: { body: string }) {
  const [raw, setRaw] = useState(false);
  const parsed = parseJson(body);
  if (!parsed.ok) return <pre className="body">{body}</pre>;
  return (
    <div className="body-view">
      <div className="code-bar">
        <button className={raw ? "chip" : "chip active"} onClick={() => setRaw(false)}>
          {t("json.tree")}
        </button>
        <button className={raw ? "chip active" : "chip"} onClick={() => setRaw(true)}>
          {t("json.raw")}
        </button>
      </div>
      {raw ? <pre className="body">{prettyBody(body)}</pre> : <JsonTree value={parsed.value} />}
    </div>
  );
}

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

  const isHtml = r.mime_type?.includes("html") ?? false;

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
          <JsonBody body={r.request_body} />
        </>
      )}

      <h3>{t("detail.responseHeaders")}</h3>
      <HeaderTable headers={r.response_headers} />
      <h3>
        {t("detail.responseBody")} {r.body_truncated && <span className="badge">{t("detail.truncated")}</span>}
      </h3>
      {r.response_body ? (
        <>
          {!isHtml && r.response_body_size > r.response_body.length && (
            <p className="muted small">
              {t("detail.preview", { shown: bytes(r.response_body.length), total: bytes(r.response_body_size) })}
            </p>
          )}
          <button
            className="ghost"
            onClick={() =>
              void download(
                `/v1/requests/${r.id}/body?part=response&reveal=${reveal}`,
                `request-${r.id}.${isHtml ? "html" : "txt"}`,
              )
            }
          >
            {t("detail.download")}
          </button>
          {isHtml ? (
            <HtmlView id={r.id} reveal={reveal} preview={r.response_body} size={r.response_body_size} />
          ) : r.response_body_size > r.response_body.length ? (
            <pre className="body">{r.response_body}</pre>
          ) : (
            <JsonBody body={r.response_body} />
          )}
        </>
      ) : (
        <p className="muted">{t("detail.noBody")}</p>
      )}
    </section>
  );
}
