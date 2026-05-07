import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";

type ProviderSnapshot = {
  status?: string;
  source?: string;
  quote?: {
    price?: number;
    change?: number;
    changePercent?: number;
    history?: Array<{ close: number }>;
  };
  research?: {
    profile?: Record<string, unknown>;
    holdings?: Array<{ symbol?: string; name?: string; weight?: number }>;
    [key: string]: unknown;
  };
};

type ResearchPayload = {
  symbol: string;
  name: string;
  assetClass?: string;
  assetLabel?: string;
  market?: string;
  exchange?: string;
  type?: string;
  isCrypto?: boolean;
  provider?: ProviderSnapshot | null;
  providerContext?: {
    status?: string;
    changePercent?: number;
    historyAvailable?: boolean;
    researchAvailable?: boolean;
  };
  quote?: ProviderSnapshot["quote"];
  research?: ProviderSnapshot["research"];
  fundamentals?: {
    sector?: string;
    industry?: string;
    marketCap?: number;
    dividendYield?: number;
    fiftyTwoWeekHigh?: number;
    fiftyTwoWeekLow?: number;
    trailingPE?: number;
    forwardPE?: number;
    priceToBook?: number;
  };
  news?: {
    items?: Array<{
      title?: string;
      summary?: string;
      score?: number;
      label?: string;
      timestamp?: string;
      url?: string;
      source?: string;
    }>;
    aggregateScore?: number;
    aggregateLabel?: string;
  };
};

export function AnalysisPage() {
  const { symbol = "" } = useParams();
  const decoded = decodeURIComponent(symbol);
  const query = useQuery({
    queryKey: ["research", decoded],
    queryFn: () =>
      apiFetch<ResearchPayload>(`/api/research/${encodeURIComponent(decoded)}`),
    enabled: !!decoded,
  });

  if (!decoded) {
    return (
      <p className="text-sm text-slate-400">
        No symbol selected. Pick one from the{" "}
        <Link to="/scanner" className="text-bergt-green hover:underline">
          scanner
        </Link>
        .
      </p>
    );
  }
  if (query.isLoading) {
    return <p className="text-sm text-slate-400">Loading research…</p>;
  }
  if (query.error) {
    return (
      <p className="text-sm text-red-300">
        Failed to load research: {(query.error as ApiError).message}
      </p>
    );
  }
  const data = query.data;
  if (!data) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {data.symbol}
            {data.assetLabel ? (
              <span className="ml-2 rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                {data.assetLabel}
              </span>
            ) : null}
          </h1>
          {data.name ? <p className="text-sm text-slate-400">{data.name}</p> : null}
          {data.exchange || data.market ? (
            <p className="text-xs text-slate-500">
              {[data.exchange, data.market].filter(Boolean).join(" · ")}
            </p>
          ) : null}
        </div>
        {data.quote?.price ? (
          <div className="text-right">
            <p className="text-3xl font-semibold tabular-nums">
              {data.quote.price.toFixed(2)}
            </p>
            <p className={`text-sm tabular-nums ${changeClass(data.quote.changePercent)}`}>
              {data.quote.changePercent?.toFixed(2) ?? "0.00"}%
            </p>
          </div>
        ) : null}
      </header>

      <ProviderSection data={data} />
      <FundamentalsSection fundamentals={data.fundamentals} />
      <HoldingsSection research={data.research} />
      <NewsSection news={data.news} />
    </div>
  );
}

function ProviderSection({ data }: { data: ResearchPayload }) {
  const status = data.providerContext?.status ?? data.provider?.status ?? "unavailable";
  const source = data.provider?.source;
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Provider research</h2>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Stat label="Status" value={status} accent={statusClass(status)} />
        <Stat label="Source" value={source ?? "—"} />
        <Stat
          label="History"
          value={data.providerContext?.historyAvailable ? "available" : "—"}
        />
        <Stat
          label="Research"
          value={data.providerContext?.researchAvailable ? "available" : "—"}
        />
      </div>
    </section>
  );
}

function FundamentalsSection({
  fundamentals,
}: {
  fundamentals: ResearchPayload["fundamentals"];
}) {
  if (!fundamentals || Object.values(fundamentals).every((v) => v == null)) {
    return null;
  }
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Fundamentals</h2>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
        {fundamentals.sector ? <Stat label="Sector" value={fundamentals.sector} /> : null}
        {fundamentals.industry ? <Stat label="Industry" value={fundamentals.industry} /> : null}
        {fundamentals.marketCap ? (
          <Stat label="Market cap" value={formatLarge(fundamentals.marketCap)} />
        ) : null}
        {fundamentals.dividendYield ? (
          <Stat
            label="Dividend yield"
            value={`${(fundamentals.dividendYield * 100).toFixed(2)}%`}
          />
        ) : null}
        {fundamentals.trailingPE ? (
          <Stat label="Trailing P/E" value={fundamentals.trailingPE.toFixed(1)} />
        ) : null}
        {fundamentals.forwardPE ? (
          <Stat label="Forward P/E" value={fundamentals.forwardPE.toFixed(1)} />
        ) : null}
        {fundamentals.priceToBook ? (
          <Stat label="P/B" value={fundamentals.priceToBook.toFixed(2)} />
        ) : null}
        {fundamentals.fiftyTwoWeekHigh ? (
          <Stat label="52W high" value={fundamentals.fiftyTwoWeekHigh.toFixed(2)} />
        ) : null}
        {fundamentals.fiftyTwoWeekLow ? (
          <Stat label="52W low" value={fundamentals.fiftyTwoWeekLow.toFixed(2)} />
        ) : null}
      </div>
    </section>
  );
}

function HoldingsSection({ research }: { research: ResearchPayload["research"] }) {
  const holdings = (research?.holdings ?? []) as Array<{
    symbol?: string;
    name?: string;
    weight?: number;
  }>;
  if (holdings.length === 0) {
    return null;
  }
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Top holdings</h2>
      <ul className="mt-2 space-y-1 text-sm">
        {holdings.slice(0, 10).map((holding, idx) => (
          <li
            key={`${holding.symbol ?? idx}-${idx}`}
            className="flex items-center justify-between"
          >
            <span>
              {holding.symbol ? (
                <Link
                  to={`/analysis/${encodeURIComponent(holding.symbol)}`}
                  className="font-medium hover:text-bergt-green"
                >
                  {holding.symbol}
                </Link>
              ) : null}
              {holding.name ? (
                <span className="ml-2 text-slate-400">{holding.name}</span>
              ) : null}
            </span>
            {holding.weight !== undefined ? (
              <span className="tabular-nums text-slate-300">
                {(holding.weight * 100).toFixed(2)}%
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function NewsSection({ news }: { news: ResearchPayload["news"] }) {
  if (!news || !news.items?.length) {
    return null;
  }
  return (
    <section className="card">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">News</h2>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs ${sentimentClass(
            news.aggregateLabel,
          )}`}
        >
          aggregate: {news.aggregateLabel ?? "neutral"} (
          {news.aggregateScore?.toFixed(2) ?? "0.00"})
        </span>
      </header>
      <ul className="mt-3 space-y-2">
        {news.items.slice(0, 5).map((item, idx) => (
          <li key={`${item.url ?? idx}-${idx}`} className="border-b border-slate-800 pb-2 last:border-b-0">
            <p className="text-sm font-medium">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="hover:text-bergt-green"
                >
                  {item.title}
                </a>
              ) : (
                item.title
              )}
            </p>
            {item.summary ? (
              <p className="mt-1 text-xs text-slate-400">{item.summary}</p>
            ) : null}
            <p className="mt-1 text-xs text-slate-500">
              {[item.source, item.label, formatTimestamp(item.timestamp)]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-sm ${accent ?? "text-slate-200"}`}>{value}</p>
    </div>
  );
}

function statusClass(status?: string): string | undefined {
  switch (status) {
    case "live":
      return "text-bergt-green";
    case "partial":
      return "text-amber-300";
    case "unavailable":
      return "text-slate-500";
    default:
      return undefined;
  }
}

function changeClass(value?: number): string {
  if (!value) return "text-slate-400";
  return value > 0 ? "text-bergt-green" : "text-red-400";
}

function sentimentClass(label?: string): string {
  switch (label) {
    case "bullish":
      return "border-bergt-green/40 bg-bergt-green/10 text-bergt-green";
    case "bearish":
      return "border-red-700/50 bg-red-900/40 text-red-300";
    default:
      return "border-slate-700 bg-slate-900 text-slate-300";
  }
}

function formatLarge(value: number): string {
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return value.toLocaleString();
}

function formatTimestamp(value?: string): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}
