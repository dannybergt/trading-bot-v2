/**
 * Symbolsuche mit ISIN-/WKN-Aufloesung.
 *
 * `GET /api/search/{query}` gibt es seit langem und es loest ueber OpenFIGI
 * auch ISIN und WKN auf — aufgerufen hat es bis 2026-08-06 **keine einzige
 * Seite**. Ein Symbol, das noch in keiner Watchlist stand, war damit nur
 * erreichbar, indem man `/analysis/<SYM>` von Hand in die Adresszeile tippte.
 * Fuer eine deutsche Zielgruppe, die WKN und ISIN aus dem Depotauszug kennt,
 * war das die groesste Einstiegshuerde ueberhaupt — bei fertiger Loesung im
 * Backend.
 *
 * Die Komponente wird an zwei Stellen benutzt: in der Kopfzeile und im
 * Watchlist-Formular. Dort war das Feld reiner Freitext, und weil das Backend
 * das Symbol beim Anlegen nicht prueft, erzeugte ein Tippfehler einen dauerhaft
 * toten Eintrag. Freitext bleibt trotzdem moeglich (`onInputChange`) — kennt
 * der Asset-Cache ein Symbol nicht, waere eine Sperre schlimmer als das
 * Risiko eines Tippfehlers.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { apiFetch } from "../api/client";

export type SymbolSearchResult = {
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  assetLabel?: string | null;
};

type Props = {
  onSelect: (result: SymbolSearchResult) => void;
  /**
   * Jede Eingabe, nicht nur die Auswahl. Damit bleibt Freitext moeglich, wenn
   * der Asset-Cache ein Symbol nicht kennt — sonst waere die Suche eine
   * Sperre statt einer Hilfe.
   */
  onInputChange?: (value: string) => void;
  placeholder?: string;
  /** Eingabe nach der Auswahl leeren (Kopfzeile) oder stehen lassen (Formular). */
  clearOnSelect?: boolean;
  testId?: string;
  autoFocus?: boolean;
};

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 300;

export function SymbolSearch({
  onSelect,
  onInputChange,
  placeholder,
  clearOnSelect = true,
  testId = "symbol-search",
  autoFocus = false,
}: Props) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  // Ohne Entprellung feuert jede Taste eine Anfrage. Der Endpunkt laedt den
  // kompletten Alpaca-Asset-Cache und filtert darueber — das ist nichts, was
  // man pro Anschlag machen will.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(input.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  const query = useQuery({
    queryKey: ["symbol-search", debounced],
    queryFn: () =>
      apiFetch<SymbolSearchResult[]>(`/api/search/${encodeURIComponent(debounced)}`),
    enabled: debounced.length >= MIN_QUERY_LENGTH,
    staleTime: 5 * 60_000,
  });

  const results = useMemo(
    () => (Array.isArray(query.data) ? query.data.slice(0, 8) : []),
    [query.data],
  );

  useEffect(() => setActiveIndex(0), [results]);

  // Klick daneben schliesst die Liste.
  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function choose(result: SymbolSearchResult) {
    onSelect(result);
    setOpen(false);
    if (clearOnSelect) {
      setInput("");
      setDebounced("");
      onInputChange?.("");
    } else {
      setInput(result.symbol);
      onInputChange?.(result.symbol);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => (prev - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showHint = debounced.length >= MIN_QUERY_LENGTH && !query.isLoading;

  return (
    <div className="relative" ref={containerRef}>
      <input
        type="search"
        className="input w-full"
        value={input}
        autoFocus={autoFocus}
        onChange={(event) => {
          setInput(event.target.value);
          onInputChange?.(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder ?? t("search.placeholder")}
        aria-label={t("search.label")}
        aria-autocomplete="list"
        aria-expanded={open && results.length > 0}
        aria-controls={listboxId}
        data-testid={testId}
      />

      {open && debounced.length >= MIN_QUERY_LENGTH ? (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg"
          data-testid={`${testId}-results`}
        >
          {query.isLoading ? (
            <li className="px-3 py-2 text-xs text-slate-400">{t("search.loading")}</li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-xs text-slate-400" data-testid={`${testId}-empty`}>
              {showHint ? t("search.empty", { query: debounced }) : null}
            </li>
          ) : (
            results.map((result, index) => (
              <li key={result.symbol} role="option" aria-selected={index === activeIndex}>
                <button
                  type="button"
                  className={`flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm ${
                    index === activeIndex ? "bg-slate-800" : "hover:bg-slate-800/70"
                  }`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => choose(result)}
                  data-testid={`${testId}-option-${result.symbol}`}
                >
                  <span className="font-medium">{result.symbol}</span>
                  <span className="truncate text-xs text-slate-400">
                    {[result.name, result.exchange].filter(Boolean).join(" · ")}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
