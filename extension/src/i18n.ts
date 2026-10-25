// UI strings live in static/_locales/<lang>/messages.json; the browser picks the
// user's language and falls back to English.

export function t(key: string, ...subs: (string | number)[]): string {
  return chrome.i18n.getMessage(key, subs.map(String)) || key;
}

export function localize(root: ParentNode): void {
  document.documentElement.lang = chrome.i18n.getUILanguage();
  for (const el of root.querySelectorAll<HTMLElement>("[data-i18n]")) el.textContent = t(el.dataset.i18n!);
}
