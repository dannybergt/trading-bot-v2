/**
 * i18n bootstrap. Loads English + German resources at startup; default
 * language is detected from localStorage, falling back to navigator.language,
 * falling back to English. Toggling persists the choice immediately.
 *
 * Resources are kept inline rather than fetched via a backend so the
 * translations land in the same Vite chunk as the rest of the app — no
 * extra round-trip on first paint, no flash of untranslated text.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import de from "./de.json";

export const SUPPORTED_LANGUAGES = ["en", "de"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const STORAGE_KEY = "language";

function detectInitialLanguage(): SupportedLanguage {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && (SUPPORTED_LANGUAGES as readonly string[]).includes(stored)) {
      return stored as SupportedLanguage;
    }
    const navigatorLang = window.navigator.language?.toLowerCase() ?? "";
    if (navigatorLang.startsWith("de")) return "de";
  }
  return "en";
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    de: { translation: de },
  },
  lng: detectInitialLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

export function setLanguage(language: SupportedLanguage) {
  void i18n.changeLanguage(language);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, language);
  }
}

export default i18n;
