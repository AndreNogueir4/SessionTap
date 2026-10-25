import { t } from "./i18n";

export function ago(ts: number | null | undefined): string {
  if (!ts) return t("time.never");
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 0) return until(ts);
  if (s < 60) return t("time.ago", { t: `${s}s` });
  if (s < 3600) return t("time.ago", { t: `${Math.round(s / 60)}m` });
  if (s < 86400) return t("time.ago", { t: `${Math.round(s / 3600)}h` });
  return t("time.ago", { t: `${Math.round(s / 86400)}d` });
}

export function until(ts: number | null | undefined): string {
  if (!ts) return t("time.never");
  const s = Math.round(ts - Date.now() / 1000);
  if (s <= 0) return t("time.expired");
  if (s < 3600) return t("time.in", { t: `${Math.round(s / 60)}m` });
  if (s < 86400) return t("time.in", { t: `${Math.round(s / 3600)}h` });
  return t("time.in", { t: `${Math.round(s / 86400)}d` });
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KiB`;
  return `${(n / 1024 / 1024).toFixed(1)} MiB`;
}

export function prettyBody(body: string | null): string {
  if (!body) return "";
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}

export function statusClass(status: number | null): string {
  if (status === null) return "status";
  if (status >= 500) return "status s5";
  if (status >= 400) return "status s4";
  if (status >= 300) return "status s3";
  return "status s2";
}
