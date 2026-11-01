import { useEffect, useState } from "react";
import { api, type BodyDiff, type DiffChange, type RequestDiff } from "../api";
import { bytes } from "../format";
import { t } from "../i18n";

function show(value: unknown): string {
  if (value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function Changes({ a, b, changes, more }: { a: number; b: number; changes: DiffChange[]; more?: number }) {
  if (changes.length === 0) return <p className="muted small">{t("diff.none")}</p>;
  return (
    <>
      <table className="diff">
        <thead>
          <tr>
            <th>{t("diff.key")}</th>
            <th>#{a}</th>
            <th>#{b}</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.key} className={c.only_in ? `only-${c.only_in}` : ""}>
              <th>{c.key}</th>
              <td className="side-a">{show(c.a)}</td>
              <td className="side-b">{show(c.b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {more ? <p className="muted small">{t("diff.more", { n: more })}</p> : null}
    </>
  );
}

function Body({ a, b, diff }: { a: number; b: number; diff: BodyDiff }) {
  if (diff.changes) return <Changes a={a} b={b} changes={diff.changes} more={diff.more} />;
  if (diff.equal) return <p className="muted small">{t("diff.identical")}</p>;
  return (
    <p className="muted small">
      {t("diff.unstructured", { a: bytes(diff.a_size ?? 0), b: bytes(diff.b_size ?? 0) })}
    </p>
  );
}

export function DiffView({
  a,
  b,
  onOpen,
  onClose,
}: {
  a: number;
  b: number;
  onOpen: (id: number) => void;
  onClose: () => void;
}) {
  const [d, setD] = useState<RequestDiff | null>(null);

  useEffect(() => {
    setD(null);
    void api.diff(a, b).then(setD);
  }, [a, b]);

  if (!d) return <section className="detail">{t("common.loading")}</section>;

  const fields = Object.entries(d.request);

  return (
    <section className="detail">
      <div className="detail-head">
        <strong>{t("diff.title", { a, b })}</strong>
        <span className={d.same_endpoint ? "pill ok" : "pill expiring"}>
          {t(d.same_endpoint ? "diff.sameEndpoint" : "diff.otherEndpoint")}
        </span>
        <button className="ghost" onClick={onClose} aria-label={t("common.close")}>
          ✕
        </button>
      </div>
      <p className="diff-open">
        <button className="link small" onClick={() => onOpen(a)}>
          {t("diff.open", { id: a })}
        </button>
        <button className="link small" onClick={() => onOpen(b)}>
          {t("diff.open", { id: b })}
        </button>
      </p>
      <p className="muted small">{t("diff.secrets")}</p>

      <h3>{t("diff.request")}</h3>
      <Changes a={a} b={b} changes={fields.map(([key, v]) => ({ key, a: v.a, b: v.b }))} />
      <h3>{t("diff.query")}</h3>
      <Changes a={a} b={b} {...d.query} />
      <h3>{t("detail.requestHeaders")}</h3>
      <Changes a={a} b={b} {...d.request_headers} />
      <h3>{t("detail.requestBody")}</h3>
      <Body a={a} b={b} diff={d.request_body} />
      <h3>{t("detail.responseHeaders")}</h3>
      <Changes a={a} b={b} {...d.response_headers} />
      <h3>{t("detail.responseBody")}</h3>
      <Body a={a} b={b} diff={d.response_body} />
    </section>
  );
}
