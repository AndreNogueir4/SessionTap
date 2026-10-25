import { useEffect, useState } from "react";
import { api, download } from "../api";
import { t } from "../i18n";

interface Operation {
  summary: string;
  "x-sessiontap-observed": number;
  parameters?: { name: string; in: string }[];
  responses: Record<string, unknown>;
  requestBody?: unknown;
}

export function ApiView({ domain }: { domain: string }) {
  const [spec, setSpec] = useState<Record<string, unknown> | null>(null);
  const [bundling, setBundling] = useState(false);

  useEffect(() => {
    void api.openapi(domain).then(setSpec);
  }, [domain]);

  if (!spec) return <p className="empty">{t("api.inferring")}</p>;
  const exportBundle = async () => {
    setBundling(true);
    try {
      await download(`/v1/export/${encodeURIComponent(domain)}/bundle`, `${domain}-sessiontap.zip`);
    } finally {
      setBundling(false);
    }
  };
  const paths = (spec.paths ?? {}) as Record<string, Record<string, Operation>>;
  const ops = Object.entries(paths).flatMap(([path, methods]) =>
    Object.entries(methods).map(([method, op]) => ({ path, method, op })),
  );

  function downloadSpec() {
    const blob = new Blob([JSON.stringify(spec, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${domain}.openapi.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="api">
      <div className="toolbar">
        <p className="muted">{t("api.summary", { n: ops.length })}</p>
        <div className="actions">
          <button onClick={downloadSpec} disabled={ops.length === 0}>
            {t("api.download")}
          </button>
          <button className="ghost" onClick={() => void exportBundle()} disabled={bundling}>
            {t(bundling ? "api.bundling" : "api.bundle")}
          </button>
        </div>
      </div>
      <p className="muted small">{t("api.bundleHelp")}</p>
      {ops.length === 0 ? (
        <p className="empty">{t("api.empty")}</p>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th>{t("col.method")}</th>
              <th>{t("col.path")}</th>
              <th>{t("col.parameters")}</th>
              <th>{t("col.responses")}</th>
              <th>{t("col.seen")}</th>
            </tr>
          </thead>
          <tbody>
            {ops.map(({ path, method, op }) => (
              <tr key={`${method} ${path}`}>
                <td className="method">{method.toUpperCase()}</td>
                <td className="mono">{path}</td>
                <td className="small">
                  {(op.parameters ?? []).map((p) => `${p.name} (${p.in})`).join(", ") || "—"}
                </td>
                <td className="small">{Object.keys(op.responses).join(", ")}</td>
                <td>{op["x-sessiontap-observed"]}×</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
