import { useState } from "react";
import { t } from "../i18n";

const STEP = 100;
const OPEN_DEPTH = 2;

function Leaf({ value }: { value: unknown }) {
  if (value === null) return <span className="json-null">null</span>;
  if (typeof value === "string") return <span className="json-string">{JSON.stringify(value)}</span>;
  if (typeof value === "number") return <span className="json-number">{value}</span>;
  return <span className="json-bool">{String(value)}</span>;
}

function Node({ name, value, depth }: { name?: string; value: unknown; depth: number }) {
  const [open, setOpen] = useState(depth < OPEN_DEPTH);
  const [limit, setLimit] = useState(STEP);
  const label = name !== undefined && <span className="json-key">{name}: </span>;

  if (value === null || typeof value !== "object") {
    return (
      <li>
        {label}
        <Leaf value={value} />
      </li>
    );
  }

  const isArray = Array.isArray(value);
  const entries: [string, unknown][] = isArray
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value as Record<string, unknown>);
  const summary = isArray ? `[${entries.length}]` : `{${entries.length}}`;

  return (
    <li>
      <button className="json-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"}
      </button>
      {label}
      <span className="muted">{summary}</span>
      {open && entries.length > 0 && (
        <ul>
          {entries.slice(0, limit).map(([k, v]) => (
            <Node key={k} name={k} value={v} depth={depth + 1} />
          ))}
          {entries.length > limit && (
            <li>
              <button className="link small" onClick={() => setLimit(limit + STEP)}>
                {t("json.more", { n: Math.min(STEP, entries.length - limit), total: entries.length - limit })}
              </button>
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

export function JsonTree({ value }: { value: unknown }) {
  return (
    <ul className="json-tree body">
      <Node value={value} depth={0} />
    </ul>
  );
}

export function parseJson(body: string | null): { ok: true; value: unknown } | { ok: false } {
  if (!body) return { ok: false };
  const start = body.trimStart()[0];
  if (start !== "{" && start !== "[") return { ok: false };
  try {
    return { ok: true, value: JSON.parse(body) };
  } catch {
    return { ok: false };
  }
}
