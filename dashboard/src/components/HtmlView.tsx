import { useEffect, useState } from "react";
import { api } from "../api";
import { bytes } from "../format";
import { t } from "../i18n";

type Mode = "page" | "source" | "text";

const PAGE_LIMIT = 5 * 1024 * 1024;
const TEXT_LIMIT = 200_000;

// Inside the sandbox the page has no scripts, no forms and an opaque origin. The frame also
// inherits the dashboard's CSP, which blocks the page's own styles; this policy adds that
// nothing loads from the network, so viewing a capture never pings the site or its trackers.
const FRAME_CSP = "default-src 'none'; img-src data:; form-action 'none'";

function sandboxed(html: string): string {
  return `<meta http-equiv="Content-Security-Policy" content="${FRAME_CSP}">${html}`;
}

export function HtmlView({
  id,
  reveal,
  preview,
  size,
}: {
  id: number;
  reveal: boolean;
  preview: string;
  size: number;
}) {
  const [mode, setMode] = useState<Mode>("page");
  const [html, setHtml] = useState(preview);
  const [text, setText] = useState<{ content: string; total: number } | null>(null);

  useEffect(() => {
    setHtml(preview);
    if (size <= preview.length) return;
    let cancelled = false;
    void api.request(id, reveal, PAGE_LIMIT).then((r) => {
      if (!cancelled && r.response_body) setHtml(r.response_body);
    });
    return () => {
      cancelled = true;
    };
  }, [id, reveal, preview, size]);

  useEffect(() => {
    setText(null);
  }, [id]);

  useEffect(() => {
    if (mode !== "text" || text) return;
    void api.chunk(id, { text: true, length: TEXT_LIMIT }).then((c) => setText(c));
  }, [id, mode, text]);

  return (
    <div className="html-view body-view">
      <div className="code-bar">
        {(["page", "source", "text"] as Mode[]).map((m) => (
          <button key={m} className={mode === m ? "chip active" : "chip"} onClick={() => setMode(m)}>
            {t(`html.${m}`)}
          </button>
        ))}
      </div>
      {size > html.length && mode !== "text" && (
        <p className="muted small">{t("detail.preview", { shown: bytes(html.length), total: bytes(size) })}</p>
      )}
      {mode === "page" && (
        <>
          <p className="muted small">{t("html.sandboxed")}</p>
          <iframe
            className="html-frame"
            title={t("html.frameTitle", { id })}
            sandbox=""
            referrerPolicy="no-referrer"
            srcDoc={sandboxed(html)}
          />
        </>
      )}
      {mode === "source" && <pre className="body">{html}</pre>}
      {mode === "text" &&
        (text === null ? (
          <p className="muted">{t("common.loading")}</p>
        ) : (
          <>
            {text.total > text.content.length && (
              <p className="muted small">
                {t("html.textPreview", { shown: text.content.length, total: text.total })}
              </p>
            )}
            <pre className="body">{text.content || t("common.empty")}</pre>
          </>
        ))}
    </div>
  );
}
