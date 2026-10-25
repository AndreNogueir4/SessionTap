import { LANGUAGES, setLang, t, useLang, type Lang } from "../i18n";

export function LanguagePicker() {
  const lang = useLang();
  return (
    <label className="language">
      <span>{t("nav.language")}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
        {(Object.keys(LANGUAGES) as Lang[]).map((l) => (
          <option key={l} value={l}>
            {LANGUAGES[l]["lang.name"]}
          </option>
        ))}
      </select>
    </label>
  );
}
