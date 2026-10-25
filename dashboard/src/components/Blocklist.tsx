import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type BlocklistView } from "../api";
import { t, tx } from "../i18n";

/** Accepts what people paste: a URL, "*.example.com" or a bare domain. */
function toDomain(input: string): string {
  const value = input.trim().toLowerCase();
  try {
    if (value.includes("://")) return new URL(value).hostname;
  } catch {
    /* not a URL; let the daemon validate it */
  }
  return value.replace(/^\*\./, "").split("/")[0]!;
}

export function Blocklist({ onChange }: { onChange: () => Promise<void> }) {
  const [view, setView] = useState<BlocklistView | null>(null);
  const [value, setValue] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.blocklist().then(setView);
  }, []);

  async function apply(action: () => Promise<BlocklistView>) {
    setError(null);
    try {
      setView(await action());
      await onChange();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? t("blocklist.invalid") : String((e as Error).message));
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    const domain = toDomain(value);
    if (!domain) return;
    await apply(() => api.block(domain));
    setValue("");
  }

  function reset() {
    if (confirm(t("blocklist.confirmReset"))) void apply(() => api.resetBlocklist());
  }

  if (!view) return null;
  const shown = view.domains
    .filter((d) => d.domain.includes(filter.trim().toLowerCase()))
    .sort((a, b) => Number(a.default) - Number(b.default) || a.domain.localeCompare(b.domain));

  return (
    <section className="card blocklist">
      <h3>
        {t("settings.blocklist")} <span className="muted small">({view.domains.length})</span>
      </h3>
      <p className="muted">{t("blocklist.help")}</p>
      {view.locked ? (
        <p className="warning small">
          {tx("blocklist.locked", { setting: <code key="setting">[capture] locked = true</code> })}
        </p>
      ) : (
        <form className="toolbar" onSubmit={(e) => void add(e)}>
          <input
            type="text"
            placeholder={t("blocklist.placeholder")}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label={t("blocklist.placeholder")}
          />
          <button type="submit" disabled={!value.trim()}>
            {t("blocklist.add")}
          </button>
        </form>
      )}
      {error && <p className="error small">{error}</p>}
      <div className="toolbar">
        <input
          type="search"
          placeholder={t("blocklist.filter")}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {!view.locked && view.customized && (
          <button className="ghost" onClick={reset}>
            {t("blocklist.reset")}
          </button>
        )}
      </div>
      <ul className="blocked">
        {shown.map((d) => (
          <li key={d.domain}>
            <span className="mono">{d.domain}</span>
            <span className={d.default ? "pill" : "pill ok"}>{t(d.default ? "blocklist.default" : "blocklist.custom")}</span>
            {!view.locked && (
              <button
                className="ghost icon"
                title={t("blocklist.remove", { domain: d.domain })}
                aria-label={t("blocklist.remove", { domain: d.domain })}
                onClick={() => void apply(() => api.unblock(d.domain))}
              >
                ×
              </button>
            )}
          </li>
        ))}
      </ul>
      {!view.locked && view.removed_defaults.length > 0 && (
        <p className="muted small">
          {t("blocklist.removedDefaults")}{" "}
          {view.removed_defaults.map((d) => (
            <button key={d} className="chip" title={t("blocklist.addBack")} onClick={() => void apply(() => api.block(d))}>
              + {d}
            </button>
          ))}
        </p>
      )}
    </section>
  );
}
