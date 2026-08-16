import { useTranslation } from "react-i18next";
import { setLanguage, LANGUAGES } from "../i18n";

export function LanguageSwitcher() {
  const { t } = useTranslation();

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-500 hidden sm:inline">{t("app.lang")}:</span>
      <select
        className="border border-surface-border rounded-md px-2 py-1 text-sm bg-white"
        defaultValue={document.documentElement.lang || "en"}
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
