import { useTranslation } from "react-i18next";
import { setLanguage, LANGUAGES } from "../i18n";

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const current = LANGUAGES.some((l) => l.code === i18n.language)
    ? i18n.language
    : "en";

  return (
    <label className="flex items-center gap-1.5 text-sm">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="text-slate-400" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
      </svg>
      <span className="sr-only">{t("app.lang")}:</span>
      <select
        className="border border-surface-border rounded-full bg-white px-2.5 py-1 text-sm text-slate-600 hover:bg-surface-alt focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        value={current}
        onChange={(e) => {
          setLanguage(e.target.value);
          document.documentElement.lang = e.target.value;
        }}
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
