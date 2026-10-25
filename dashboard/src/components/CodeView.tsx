import { useEffect, useState } from "react";
import { api } from "../api";
import { t } from "../i18n";

const LANGS = [
  ["python", "Python"],
  ["curl", "curl"],
  ["javascript", "JavaScript"],
] as const;

export function CodeView({ id }: { id: number }) {
  const [lang, setLang] = useState<string>("python");
  const [withSecrets, setWithSecrets] = useState(false);
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    void api.code(id, lang, withSecrets).then(setCode);
  }, [id, lang, withSecrets]);

  async function copy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="code">
      <div className="code-bar">
        {LANGS.map(([value, label]) => (
          <button key={value} className={lang === value ? "chip active" : "chip"} onClick={() => setLang(value)}>
            {label}
          </button>
        ))}
        <label className="check">
          <input type="checkbox" checked={withSecrets} onChange={(e) => setWithSecrets(e.target.checked)} />
          {t("code.inline")}
        </label>
        <button className="chip" onClick={() => void copy()}>
          {t(copied ? "common.copied" : "common.copy")}
        </button>
      </div>
      {withSecrets && (
        <p className="warning small">{t("code.warning")}</p>
      )}
      <pre>{code}</pre>
    </div>
  );
}
