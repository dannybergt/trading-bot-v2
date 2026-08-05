/**
 * Zentrale Zahlenformatierung.
 *
 * Die UX-Direktive verlangt Werte "immer mit Einheit, Vorzeichen,
 * Vergleichswert". Tatsaechlich fand sich im Frontend kein einziger Aufruf von
 * `Intl.NumberFormat`, dafuer 116 verstreute `toFixed(...)`, fuenf leicht
 * voneinander abweichende Prozent-Helfer (mal `-`, mal `−` U+2212) und ein
 * `formatCurrency`, das nie eine Waehrung ausgab. Kurse in den Zonen standen
 * als nackte Zahl da, obwohl die Kopfzeile darueber die Waehrung nennt.
 *
 * Dazu kam ein zweiter, unsichtbarer Fehler: 19 `toLocaleString()`-Aufrufe
 * ohne Locale-Argument folgen der **Browser**-Sprache, nicht der im Toggle
 * gewaehlten. Ein deutscher Browser mit englischer Oberflaeche lieferte
 * `1.234,56` mitten im englischen Satz.
 *
 * Diese Datei bindet die Formatierung deshalb an `i18n.language`.
 */
import i18n from "i18next";

/** BCP-47-Kennung der aktuell gewaehlten Oberflaechensprache. */
export function currentLocale(): string {
  return i18n.language === "de" ? "de-DE" : "en-US";
}

type MoneyOptions = {
  /** Vorzeichen auch bei positiven Betraegen zeigen (Differenzen). */
  signed?: boolean;
  digits?: number;
};

/**
 * Geldbetrag mit Waehrung. Faellt auf reine Zahlenformatierung zurueck, wenn
 * die Waehrung unbekannt ist — lieber ohne Einheit als mit einer falschen.
 */
export function formatMoney(
  value: number | null | undefined,
  currency?: string | null,
  options: MoneyOptions = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const { signed = false, digits = 2 } = options;

  const base: Intl.NumberFormatOptions = {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  };

  if (currency) {
    try {
      return new Intl.NumberFormat(currentLocale(), {
        ...base,
        style: "currency",
        currency,
      }).format(value);
    } catch {
      // Unbekannter Waehrungscode (etwa ein Krypto-Ticker) — Intl wirft dann.
      return `${new Intl.NumberFormat(currentLocale(), base).format(value)} ${currency}`;
    }
  }
  return new Intl.NumberFormat(currentLocale(), base).format(value);
}

/**
 * Prozentwert. Erwartet den Wert bereits in Prozent (12.5 → "12,5 %"),
 * nicht als Anteil — so liegen die Werte im gesamten Backend vor.
 */
export function formatPercent(
  value: number | null | undefined,
  options: { signed?: boolean; digits?: number } = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const { signed = false, digits = 2 } = options;
  return new Intl.NumberFormat(currentLocale(), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value / 100);
}

/** Reine Zahl, lokalisiert. Fuer Stueckzahlen, Volumina, Zaehler. */
export function formatNumber(
  value: number | null | undefined,
  options: { digits?: number; signed?: boolean } = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const { digits = 0, signed = false } = options;
  return new Intl.NumberFormat(currentLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value);
}

/** Datum/Zeit in der gewaehlten Oberflaechensprache, nicht der des Browsers. */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(currentLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
