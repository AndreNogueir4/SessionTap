import type { Facets, FacetCount, RequestFilters, StatusClass } from "../api";
import { t } from "../i18n";

const STATUS_ORDER: StatusClass[] = ["2xx", "3xx", "4xx", "5xx", "error"];
const STATUS_STYLE: Record<StatusClass, string> = { "2xx": "s2", "3xx": "s3", "4xx": "s4", "5xx": "s5", error: "s5" };

export const NO_FILTERS: RequestFilters = { q: "", methods: [], statuses: [], host: "", mime: "", apiOnly: true };

export function hasFilters(f: RequestFilters): boolean {
  return f.methods.length > 0 || f.statuses.length > 0 || f.host !== "" || f.mime !== "";
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Facet values plus any selected value that has no matches right now, so it can be unselected. */
function withSelected<T extends string>(facets: FacetCount<T>[], selected: T[]): FacetCount<T>[] {
  const missing = selected.filter((s) => !facets.some((f) => f.value === s));
  return [...facets, ...missing.map((value) => ({ value, count: 0 }))];
}

function Select({
  label,
  all,
  value,
  options,
  onChange,
}: {
  label: string;
  all: string;
  value: string;
  options: FacetCount[];
  onChange: (value: string) => void;
}) {
  const shown = withSelected(options, value ? [value] : []);
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{all}</option>
      {shown.map((o) => (
        <option key={o.value} value={o.value}>
          {o.value} ({o.count})
        </option>
      ))}
    </select>
  );
}

export function Filters({
  filters,
  facets,
  onChange,
}: {
  filters: RequestFilters;
  facets: Facets | null;
  onChange: (f: RequestFilters) => void;
}) {
  const statuses = withSelected(facets?.statuses ?? [], filters.statuses).sort(
    (a, b) => STATUS_ORDER.indexOf(a.value) - STATUS_ORDER.indexOf(b.value),
  );
  return (
    <div className="filters">
      <div className="chips" role="group" aria-label={t("filters.method")}>
        {withSelected(facets?.methods ?? [], filters.methods).map((m) => (
          <button
            key={m.value}
            className={filters.methods.includes(m.value) ? "chip active" : "chip"}
            aria-pressed={filters.methods.includes(m.value)}
            onClick={() => onChange({ ...filters, methods: toggle(filters.methods, m.value) })}
          >
            <span className="method">{m.value}</span> <span className="muted">{m.count}</span>
          </button>
        ))}
      </div>
      <div className="chips" role="group" aria-label={t("filters.status")}>
        {statuses.map((s) => (
          <button
            key={s.value}
            className={filters.statuses.includes(s.value) ? "chip active" : "chip"}
            aria-pressed={filters.statuses.includes(s.value)}
            onClick={() => onChange({ ...filters, statuses: toggle(filters.statuses, s.value) })}
          >
            <span className={`status ${STATUS_STYLE[s.value]}`}>{s.value === "error" ? "ERR" : s.value}</span>{" "}
            <span className="muted">{s.count}</span>
          </button>
        ))}
      </div>
      <Select
        label={t("filters.host")}
        all={t("filters.allHosts")}
        value={filters.host}
        options={facets?.hosts ?? []}
        onChange={(host) => onChange({ ...filters, host })}
      />
      <Select
        label={t("filters.type")}
        all={t("filters.allTypes")}
        value={filters.mime}
        options={facets?.mime_types ?? []}
        onChange={(mime) => onChange({ ...filters, mime })}
      />
      {hasFilters(filters) && (
        <button
          className="link small"
          onClick={() => onChange({ ...NO_FILTERS, q: filters.q, apiOnly: filters.apiOnly })}
        >
          {t("filters.clear")}
        </button>
      )}
    </div>
  );
}
