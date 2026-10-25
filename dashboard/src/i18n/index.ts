import { useSyncExternalStore, type ReactNode } from "react";
import { en, type MessageKey } from "./en";
import { ptBR } from "./pt-BR";

// English is the base language; a missing translation falls back to it.
export const LANGUAGES = { en, "pt-BR": ptBR } as const;
export type Lang = keyof typeof LANGUAGES;

const STORE_KEY = "sessiontap.lang";
const listeners = new Set<() => void>();

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved && saved in LANGUAGES) return saved as Lang;
  } catch {
    /* storage blocked */
  }
  return navigator.languages.some((l) => l.toLowerCase().startsWith("pt")) ? "pt-BR" : "en";
}

let current: Lang = detect();
document.documentElement.lang = current;

export function setLang(lang: Lang): void {
  current = lang;
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORE_KEY, lang);
  } catch {
    /* storage blocked */
  }
  for (const l of listeners) l();
}

export function useLang(): Lang {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
  );
}

export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  const template: string = LANGUAGES[current][key] ?? en[key];
  return template.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

/** Like t(), but placeholders can be elements (e.g. <code>). */
export function tx(key: MessageKey, vars: Record<string, ReactNode>): ReactNode[] {
  const template: string = LANGUAGES[current][key] ?? en[key];
  return template.split(/(\{\w+\})/).map((part) => {
    const name = /^\{(\w+)\}$/.exec(part)?.[1];
    return name && name in vars ? vars[name] : part;
  });
}

export type { MessageKey };
