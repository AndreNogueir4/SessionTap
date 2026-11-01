import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Facets, type RequestFilters, type RequestSummary } from "../api";
import { ago, statusClass } from "../format";
import { CopyAs } from "./CopyAs";
import { DiffView } from "./DiffView";
import { Filters, hasFilters, NO_FILTERS } from "./Filters";
import { RequestDetailView } from "./RequestDetail";
import { t } from "../i18n";

const PAGE = 100;

type Pane = { kind: "detail"; id: number } | { kind: "diff"; a: number; b: number } | null;

/** Adds rows that arrived since the last load on top; offset paging may repeat a row, never show it twice. */
function merge(current: RequestSummary[], page: RequestSummary[], where: "top" | "bottom"): RequestSummary[] {
  const seen = new Set(current.map((r) => r.id));
  const fresh = page.filter((r) => !seen.has(r.id));
  if (fresh.length === 0) return current;
  return where === "top" ? [...fresh, ...current] : [...current, ...fresh];
}

export function Requests({ domain }: { domain: string }) {
  const [filters, setFilters] = useState<RequestFilters>(NO_FILTERS);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [items, setItems] = useState<RequestSummary[]>([]);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pane, setPane] = useState<Pane>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const generation = useRef(0);
  const busy = useRef(false);
  const count = useRef(0);
  const sentinel = useRef<HTMLDivElement>(null);
  count.current = items.length;

  useEffect(() => {
    setPane(null);
    setPicked([]);
    setFilters(NO_FILTERS);
  }, [domain]);

  useEffect(() => {
    const gen = ++generation.current;
    const current = () => generation.current === gen;
    const refreshFacets = () =>
      api.facets(domain, filters.apiOnly).then((f) => {
        if (current()) setFacets(f);
      });
    const timer = setTimeout(() => {
      void api.requests(domain, filters, 0, PAGE).then((page) => {
        if (!current()) return;
        setItems(page);
        setDone(page.length < PAGE);
      });
      void refreshFacets();
    }, 200);
    const poll = setInterval(() => {
      void api.requests(domain, filters, 0, PAGE).then((page) => {
        if (current()) setItems((cur) => merge(cur, page, "top"));
      });
      void refreshFacets();
    }, 5000);
    return () => {
      clearTimeout(timer);
      clearInterval(poll);
    };
  }, [domain, filters]);

  const loadMore = useCallback(() => {
    if (busy.current || done) return;
    const gen = generation.current;
    busy.current = true;
    setLoading(true);
    void api
      .requests(domain, filters, count.current, PAGE)
      .then((page) => {
        if (generation.current !== gen) return;
        setItems((cur) => merge(cur, page, "bottom"));
        setDone(page.length < PAGE);
      })
      .finally(() => {
        busy.current = false;
        setLoading(false);
      });
  }, [domain, filters, done]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || done) return;
    const observer = new IntersectionObserver((entries) => entries[0]?.isIntersecting && loadMore(), {
      rootMargin: "300px",
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [loadMore, done, items.length]);

  function pick(id: number) {
    setPicked((cur) => (cur.includes(id) ? cur.filter((p) => p !== id) : [...cur, id].slice(-2)));
  }

  function compare() {
    const [a, b] = [...picked].sort((x, y) => x - y);
    if (a !== undefined && b !== undefined) setPane({ kind: "diff", a, b });
  }

  const selected = pane?.kind === "detail" ? pane.id : null;

  return (
    <div className={pane === null ? "split" : "split open"}>
      <section className="list">
        <div className="toolbar">
          <input
            type="search"
            placeholder={t("requests.filter")}
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          />
          <label className="check">
            <input
              type="checkbox"
              checked={filters.apiOnly}
              onChange={(e) => setFilters({ ...filters, apiOnly: e.target.checked })}
            />
            {t("requests.apiOnly")}
          </label>
          <button className="ghost" disabled={picked.length !== 2} onClick={compare}>
            {t("requests.compare", { n: picked.length })}
          </button>
        </div>
        <Filters filters={filters} facets={facets} onChange={setFilters} />
        {items.length === 0 ? (
          <p className="empty">{t("requests.empty", { domain })}</p>
        ) : (
          <>
            <table className="requests">
              <thead>
                <tr>
                  <th className="pick">
                    <span className="visually-hidden">{t("requests.pick")}</span>
                  </th>
                  <th>{t("col.method")}</th>
                  <th>{t("col.path")}</th>
                  <th>{t("col.status")}</th>
                  <th>{t("col.when")}</th>
                  <th>
                    <span className="visually-hidden">{t("copy.as")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    className={selected === r.id || picked.includes(r.id) ? "selected" : ""}
                    onClick={() => setPane({ kind: "detail", id: r.id })}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && setPane({ kind: "detail", id: r.id })}
                  >
                    <td className="pick" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={t("requests.pick")}
                        checked={picked.includes(r.id)}
                        onChange={() => pick(r.id)}
                      />
                    </td>
                    <td className="method">{r.method}</td>
                    <td className="path" title={`${r.host}${r.path}`}>
                      {r.host !== domain && <span className="host">{r.host}</span>}
                      {r.path}
                    </td>
                    <td>
                      <span className={statusClass(r.status)}>{r.error ? "ERR" : (r.status ?? "…")}</span>
                    </td>
                    <td className="muted">{ago(r.started_at)}</td>
                    <td className="row-actions">
                      <CopyAs id={r.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div ref={sentinel} className="list-footer muted small">
              {facets && !filters.q && !hasFilters(filters)
                ? t("requests.showing", { shown: items.length, total: facets.total })
                : t("requests.shown", { shown: items.length })}
              {!done && (
                <button className="ghost" disabled={loading} onClick={loadMore}>
                  {t(loading ? "requests.loadingMore" : "requests.loadMore")}
                </button>
              )}
            </div>
          </>
        )}
      </section>
      {pane?.kind === "detail" && <RequestDetailView id={pane.id} onClose={() => setPane(null)} />}
      {pane?.kind === "diff" && (
        <DiffView
          a={pane.a}
          b={pane.b}
          onOpen={(id) => setPane({ kind: "detail", id })}
          onClose={() => setPane(null)}
        />
      )}
    </div>
  );
}
