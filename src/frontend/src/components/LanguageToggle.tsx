import { useTranslation } from "react-i18next";

import { SUPPORTED_LANGUAGES, setLanguage, type SupportedLanguage } from "../i18n";

const LABEL_KEY: Record<SupportedLanguage, string> = {
  en: "app.languageEnglish",
  de: "app.languageGerman",
};

export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { t, i18n } = useTranslation();
  const current = (SUPPORTED_LANGUAGES.includes(i18n.language as SupportedLanguage)
    ? i18n.language
    : "en") as SupportedLanguage;

  return (
    <label className={`text-xs ${compact ? "" : "block"}`}>
      <span className="sr-only">{t("app.language")}</span>
      <select
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 hover:border-bergt-green/50 focus:border-bergt-green focus:outline-none"
        value={current}
        onChange={(event) => setLanguage(event.target.value as SupportedLanguage)}
        aria-label={t("app.language")}
      >
        {SUPPORTED_LANGUAGES.map((code) => (
          <option key={code} value={code}>
            {t(LABEL_KEY[code])}
          </option>
        ))}
      </select>
    </label>
  );
}
