import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { t } from "../i18n";

const LANGS = [
  ["curl", "curl"],
  ["python", "Python"],
  ["javascript", "fetch (JavaScript)"],
] as const;

/** "Copy as" menu for a row. The code loads credentials through the SDK; it never contains them. */
export function CopyAs({ id }: { id: number }) {
  const menu = useRef<HTMLDetailsElement>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menu.current?.open && !menu.current.contains(e.target as Node)) menu.current.open = false;
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  async function copy(lang: string) {
    await navigator.clipboard.writeText(await api.code(id, lang, false));
    setCopied(lang);
    setTimeout(() => {
      setCopied(null);
      if (menu.current) menu.current.open = false;
    }, 1000);
  }

  return (
    <details
      className="menu"
      ref={menu}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Escape" && menu.current) menu.current.open = false;
      }}
    >
      <summary className="chip" title={t("copy.as")} aria-label={t("copy.as")}>
        {"</>"}
      </summary>
      <div className="menu-list" role="menu">
        <p className="muted small">{t("copy.as")}</p>
        {LANGS.map(([lang, label]) => (
          <button key={lang} role="menuitem" className="ghost" onClick={() => void copy(lang)}>
            {copied === lang ? t("common.copied") : label}
          </button>
        ))}
        <p className="muted small">{t("copy.help")}</p>
      </div>
    </details>
  );
}
