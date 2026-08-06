import { createContext, useContext, useId, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { formatSourceStamp } from "../format/numbers";

/**
 * Herkunftshinweis an einer Kennzahlen-Sektion (Zielkatalog TBV2-Z06 b).
 *
 * Zeigt sichtbar — nicht hinter einem Icon versteckt, die UX-Direktive
 * verbietet versteckte Pfade — wer die Zahlen geliefert hat und auf welchen
 * Zeitpunkt sie sich beziehen. Der Zeitpunkt nennt immer seine Bedeutung:
 * ein Abrufzeitpunkt ist kein Datenstand, und ein Modell-Trainingsdatum ist
 * beides nicht. Liefert eine Quelle keinen Zeitpunkt, steht das da — statt
 * einer plausibel aussehenden Zahl, die niemand gemessen hat.
 *
 * Alle Werte kommen aus `app/metric_sources.py`. Im Frontend wird kein
 * Provider-Name von Hand geschrieben; zwei Stellen fuer dieselbe Tatsache
 * laufen frueher oder spaeter auseinander.
 */
export type MetricSource = {
  key: string;
  provider: string | null;
  available: boolean;
  asOf: string | null;
  asOfKind: "data" | "fetch" | "trained" | "unknown";
};

const SourceMapContext = createContext<Record<string, MetricSource>>({});

export function SourceMapProvider({
  sources,
  children,
}: {
  sources: MetricSource[] | undefined;
  children: ReactNode;
}) {
  const map: Record<string, MetricSource> = {};
  for (const entry of sources ?? []) {
    if (entry && entry.key) map[entry.key] = entry;
  }
  return <SourceMapContext.Provider value={map}>{children}</SourceMapContext.Provider>;
}

export function useMetricSource(key: string): MetricSource | undefined {
  return useContext(SourceMapContext)[key];
}

type Props = {
  /** Schluessel aus `DISPLAY_SOURCE_KEYS` — die Regel ist der Normalfall. */
  sourceKey?: string;
  /**
   * Direkt uebergebene Herkunft fuer die zwei Sektionen, deren Daten aus
   * einem eigenen Endpunkt kommen und die die Herkunftskarte deshalb nicht
   * kennt (Termine, Modellguete).
   */
  source?: MetricSource | null;
};

export function SourceTip({ sourceKey, source }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  const fromMap = useMetricSource(sourceKey ?? "");
  const entry = source ?? fromMap;

  const provider = entry?.available ? entry.provider : null;
  const kind = entry?.asOfKind ?? "unknown";
  const stamp = entry?.asOf ? formatSourceStamp(entry.asOf) : null;

  const summary = provider
    ? `${t("sources.label")}: ${provider} · ${
        stamp ? `${t(`sources.kind.${kind}`)} ${stamp}` : t("sources.kind.unknown")
      }`
    : `${t("sources.label")}: ${t("sources.none")}`;

  const explanation = provider
    ? t(stamp ? `sources.explain.${kind}` : "sources.explain.unknown")
    : t("sources.explain.none");

  return (
    <span
      className="relative inline-flex align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        data-testid="source-tip"
        data-source-key={sourceKey ?? entry?.key ?? "inline"}
        data-source-summary={summary}
        aria-describedby={open ? id : undefined}
        className="rounded border border-slate-700/70 px-1.5 py-0.5 text-[10px] font-normal normal-case tracking-normal text-slate-400 hover:border-slate-500 hover:text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
      >
        {summary}
      </button>
      {open ? (
        <span
          role="tooltip"
          id={id}
          className="absolute right-0 top-full z-50 mt-1 w-64 rounded border border-slate-700 bg-slate-800 p-2 text-left text-xs font-normal normal-case tracking-normal text-slate-200 shadow-lg"
        >
          {explanation}
        </span>
      ) : null}
    </span>
  );
}
