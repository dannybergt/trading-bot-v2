import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";
import {
  StockChart,
  type ChartCandle,
  type ChartPattern,
  type ChartZones,
} from "../components/StockChart";

type FeatureContribution = {
  feature: string;
  contribution: number;
  value: number;
  direction: "up" | "down";
};

type Prediction = {
  direction?: "UP" | "DOWN" | "HOLD";
  confidence?: number;
  reason?: string;
  explanation?: {
    baseline: number;
    method: string;
    topFeatures: FeatureContribution[];
  } | null;
  zones?: ChartZones | null;
};

type StockResponse = {
  symbol: string;
  name?: string;
  assetClass?: string;
  assetLabel?: string;
  market?: string;
  exchange?: string;
  type?: string;
  isCrypto?: boolean;
  info?: {
    sector?: string;
    industry?: string;
    marketCap?: number;
    dividendYield?: number;
    trailingPE?: number;
    forwardPE?: number;
    priceToBook?: number;
    "52WeekHigh"?: number;
    "52WeekLow"?: number;
  };
  provider?: { status?: string; source?: string } | null;
  chart_data: ChartCandle[];
  patterns: ChartPattern[];
  prediction: Prediction | null;
};

type ResearchPayload = {
  symbol: string;
  name: string;
  research?: {
    holdings?: Array<{ symbol?: string; name?: string; weight?: number }>;
  };
  news?: {
    items?: Array<{
      title?: string;
      summary?: string;
      label?: string;
      timestamp?: string;
      url?: string;
      source?: string;
    }>;
    aggregateScore?: number;
    aggregateLabel?: string;
  };
};

type EventsPayload = {
  symbol: string;
  events: {
    dividends: Array<{
      date?: string;
      amount?: number | null;
      adjAmount?: number | null;
      paymentDate?: string;
      label?: string;
    }>;
    splits: Array<{
      date?: string;
      numerator?: number | null;
      denominator?: number | null;
      label?: string;
    }>;
    earnings: Array<{
      date?: string;
      epsEstimate?: number | null;
      epsActual?: number | null;
      revenueEstimate?: number | null;
      revenueActual?: number | null;
      time?: string;
    }>;
  };
  provider?: { status?: string; source?: string | null };
};

const TIMEFRAMES = [
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "1Y", label: "1Y" },
  { value: "MAX", label: "Max" },
];

export function AnalysisPage() {
  const { symbol = "" } = useParams();
  const decoded = decodeURIComponent(symbol);
  const [timeframe, setTimeframe] = useState("6M");

  const stockQuery = useQuery({
    queryKey: ["stock", decoded, timeframe],
    queryFn: () =>
      apiFetch<StockResponse>(
        `/api/stock/${encodeURIComponent(decoded)}?timeframe=${timeframe}`,
      ),
    enabled: !!decoded,
  });

  const researchQuery = useQuery({
    queryKey: ["research", decoded],
    queryFn: () =>
      apiFetch<ResearchPayload>(`/api/research/${encodeURIComponent(decoded)}`),
    enabled: !!decoded,
  });

  const eventsQuery = useQuery({
    queryKey: ["events", decoded],
    queryFn: () =>
      apiFetch<EventsPayload>(`/api/events/${encodeURIComponent(decoded)}`),
    enabled: !!decoded,
    staleTime: 5 * 60_000,
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

  if (stockQuery.error) {
    return (
      <p className="text-sm text-red-300">
        Failed to load stock data: {(stockQuery.error as ApiError).message}
      </p>
    );
  }

  const stock = stockQuery.data;
  const research = researchQuery.data;
  const candles = stock?.chart_data ?? [];
  const patterns = stock?.patterns ?? [];
  const lastClose = candles.at(-1)?.close ?? null;
  const firstClose = candles[0]?.close ?? null;
  const periodChangePct =
    lastClose != null && firstClose != null && firstClose !== 0
      ? ((lastClose - firstClose) / firstClose) * 100
      : null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {decoded}
            {stock?.assetLabel ? (
              <span className="ml-2 rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                {stock.assetLabel}
              </span>
            ) : null}
          </h1>
          {stock?.name ? <p className="text-sm text-slate-400">{stock.name}</p> : null}
          {stock?.exchange || stock?.market ? (
            <p className="text-xs text-slate-500">
              {[stock.exchange, stock.market].filter(Boolean).join(" · ")}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {lastClose != null ? (
            <div className="text-right">
              <p className="text-3xl font-semibold tabular-nums">
                {lastClose.toFixed(2)}
              </p>
              {periodChangePct != null ? (
                <p
                  className={`text-sm tabular-nums ${
                    periodChangePct >= 0 ? "text-bergt-green" : "text-red-400"
                  }`}
                >
                  {periodChangePct >= 0 ? "+" : ""}
                  {periodChangePct.toFixed(2)}% ({timeframe})
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="flex items-center gap-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                type="button"
                onClick={() => setTimeframe(tf.value)}
                className={`rounded-md px-2.5 py-1 text-xs transition ${
                  timeframe === tf.value
                    ? "bg-bergt-green/20 text-bergt-green"
                    : "bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <PredictionCard prediction={stock?.prediction} />
      <PatternsCard patterns={patterns} />

      {stockQuery.isLoading ? (
        <p className="text-sm text-slate-400">Loading chart…</p>
      ) : candles.length === 0 ? (
        <p className="text-sm text-slate-500">No chart data available.</p>
      ) : (
        <StockChart
          candles={candles}
          patterns={patterns}
          zones={stock?.prediction?.zones ?? null}
        />
      )}

      <FundamentalsSection info={stock?.info} provider={stock?.provider} />
      <EventsSection events={eventsQuery.data?.events} provider={eventsQuery.data?.provider} />
      <HoldingsSection research={research?.research} />
      <NewsSection news={research?.news} />
    </div>
  );
}

function PredictionCard({ prediction }: { prediction?: Prediction | null }) {
  if (!prediction || !prediction.direction) return null;
  const dir = prediction.direction;
  const confidence = prediction.confidence ?? 0;
  const baseCls =
    dir === "UP"
      ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
      : dir === "DOWN"
      ? "border-red-700/50 bg-red-900/40 text-red-200"
      : "border-slate-700 bg-slate-900 text-slate-300";

  return (
    <section className={`rounded-lg border p-3 text-sm ${baseCls}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">
          ML signal: {dir} ({(confidence * 100).toFixed(1)}% confidence)
        </p>
        {prediction.zones?.riskReward != null ? (
          <p className="text-xs opacity-80">
            R:R = {prediction.zones.riskReward.toFixed(2)}
          </p>
        ) : null}
      </header>

      {prediction.zones ? (
        <div className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
          <ZoneCell
            label="Entry"
            value={`${prediction.zones.entryLow.toFixed(2)} – ${prediction.zones.entryHigh.toFixed(2)}`}
          />
          <ZoneCell label="Stop" value={prediction.zones.stopLoss.toFixed(2)} accent="red" />
          <ZoneCell label="Target" value={prediction.zones.target.toFixed(2)} accent="green" />
          <ZoneCell label="ATR" value={prediction.zones.atr.toFixed(3)} />
        </div>
      ) : null}

      {prediction.explanation && prediction.explanation.topFeatures.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs uppercase tracking-wide opacity-70">
            Top contributing features
          </p>
          <ul className="mt-1 space-y-1">
            {prediction.explanation.topFeatures.map((f) => (
              <li
                key={f.feature}
                className="flex items-center justify-between text-xs tabular-nums"
              >
                <span className="font-mono">{f.feature}</span>
                <span className="flex items-center gap-2">
                  <span className="opacity-70">val {fmtFeatureValue(f.value)}</span>
                  <span
                    className={
                      f.direction === "up" ? "text-bergt-green" : "text-red-400"
                    }
                  >
                    {f.contribution >= 0 ? "+" : ""}
                    {f.contribution.toFixed(3)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] uppercase tracking-wide opacity-50">
            method: {prediction.explanation.method}
          </p>
        </div>
      ) : null}

      {prediction.reason ? (
        <p className="mt-2 text-xs opacity-80">{prediction.reason}</p>
      ) : null}
    </section>
  );
}

function ZoneCell({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "red" | "green";
}) {
  const cls =
    accent === "red"
      ? "text-red-300"
      : accent === "green"
      ? "text-bergt-green"
      : "";
  return (
    <div className="rounded-md border border-slate-700/40 bg-slate-950/40 px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wide opacity-60">{label}</p>
      <p className={`mt-0.5 text-sm font-medium tabular-nums ${cls}`}>{value}</p>
    </div>
  );
}

function fmtFeatureValue(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(3);
  return value.toFixed(4);
}

function PatternsCard({ patterns }: { patterns: ChartPattern[] }) {
  if (!patterns.length) return null;
  return (
    <section className="card">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Detected patterns
      </h2>
      <ul className="mt-2 flex flex-wrap gap-2">
        {patterns.map((p, idx) => (
          <li
            key={`${p.name}-${idx}`}
            className={`rounded-full border px-2 py-0.5 text-xs ${
              p.signal === "buy"
                ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
                : p.signal === "sell"
                ? "border-red-700/50 bg-red-900/40 text-red-200"
                : "border-slate-700 bg-slate-900 text-slate-300"
            }`}
          >
            {p.name} · {p.signal}
          </li>
        ))}
      </ul>
    </section>
  );
}

function FundamentalsSection({
  info,
  provider,
}: {
  info: StockResponse["info"];
  provider: StockResponse["provider"];
}) {
  if (!info) return null;
  const entries: Array<[string, string]> = [];
  if (info.sector) entries.push(["Sector", info.sector]);
  if (info.industry) entries.push(["Industry", info.industry]);
  if (info.marketCap) entries.push(["Market cap", formatLarge(info.marketCap)]);
  if (info.dividendYield)
    entries.push(["Dividend yield", `${(info.dividendYield * 100).toFixed(2)}%`]);
  if (info.trailingPE) entries.push(["Trailing P/E", info.trailingPE.toFixed(1)]);
  if (info.forwardPE) entries.push(["Forward P/E", info.forwardPE.toFixed(1)]);
  if (info.priceToBook) entries.push(["P/B", info.priceToBook.toFixed(2)]);
  if (info["52WeekHigh"]) entries.push(["52W high", info["52WeekHigh"].toFixed(2)]);
  if (info["52WeekLow"]) entries.push(["52W low", info["52WeekLow"].toFixed(2)]);
  if (entries.length === 0) return null;
  return (
    <section className="card">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Fundamentals</h2>
        {provider?.status ? (
          <span
            className={`rounded-full border px-2 py-0.5 text-xs ${providerClass(
              provider.status,
            )}`}
          >
            {provider.status}
            {provider.source ? ` · ${provider.source}` : ""}
          </span>
        ) : null}
      </header>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
        {entries.map(([label, value]) => (
          <div key={label}>
            <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
            <p className="mt-0.5 text-sm">{value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function EventsSection({
  events,
  provider,
}: {
  events: EventsPayload["events"] | undefined;
  provider: EventsPayload["provider"] | undefined;
}) {
  if (!events) return null;
  const { earnings, dividends, splits } = events;
  if (earnings.length === 0 && dividends.length === 0 && splits.length === 0) {
    if (provider?.status === "unavailable") {
      return (
        <section className="card">
          <h2 className="text-lg font-semibold">Events</h2>
          <p className="mt-2 text-xs text-slate-500">
            No earnings/dividend/split history available for this symbol
            (provider returned nothing or FMP_API_KEY is unset).
          </p>
        </section>
      );
    }
    return null;
  }
  return (
    <section className="card">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Events</h2>
        {provider?.source ? (
          <span className="text-xs text-slate-500">via {provider.source}</span>
        ) : null}
      </header>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        <EarningsTable rows={earnings} />
        <DividendsTable rows={dividends} />
        <SplitsTable rows={splits} />
      </div>
    </section>
  );
}

function EarningsTable({ rows }: { rows: EventsPayload["events"]["earnings"] }) {
  if (rows.length === 0) {
    return <EmptyEvents label="Earnings" />;
  }
  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Earnings</p>
      <ul className="space-y-1 text-sm">
        {rows.slice(0, 8).map((row, idx) => {
          const beat =
            row.epsActual != null && row.epsEstimate != null
              ? row.epsActual - row.epsEstimate
              : null;
          return (
            <li
              key={`${row.date ?? idx}-${idx}`}
              className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
            >
              <div>
                <p className="font-medium tabular-nums">{row.date ?? "—"}</p>
                {row.time ? (
                  <p className="text-xs uppercase text-slate-500">{row.time}</p>
                ) : null}
              </div>
              <div className="text-right text-xs tabular-nums">
                <p>
                  EPS:{" "}
                  {row.epsActual != null ? row.epsActual.toFixed(2) : "—"}
                  {row.epsEstimate != null ? (
                    <span className="ml-1 text-slate-500">
                      (est {row.epsEstimate.toFixed(2)})
                    </span>
                  ) : null}
                </p>
                {beat != null ? (
                  <p
                    className={
                      beat >= 0 ? "text-bergt-green" : "text-red-400"
                    }
                  >
                    {beat >= 0 ? "beat" : "miss"} {Math.abs(beat).toFixed(2)}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DividendsTable({
  rows,
}: {
  rows: EventsPayload["events"]["dividends"];
}) {
  if (rows.length === 0) {
    return <EmptyEvents label="Dividends" />;
  }
  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Dividends</p>
      <ul className="space-y-1 text-sm">
        {rows.slice(0, 8).map((row, idx) => (
          <li
            key={`${row.date ?? idx}-${idx}`}
            className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          >
            <div>
              <p className="font-medium tabular-nums">{row.date ?? "—"}</p>
              {row.label ? (
                <p className="text-xs text-slate-500">{row.label}</p>
              ) : null}
            </div>
            <div className="text-right text-xs tabular-nums">
              <p className="font-medium">
                ${row.amount != null ? row.amount.toFixed(4) : "—"}
              </p>
              {row.paymentDate ? (
                <p className="text-slate-500">paid {row.paymentDate}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SplitsTable({
  rows,
}: {
  rows: EventsPayload["events"]["splits"];
}) {
  if (rows.length === 0) {
    return <EmptyEvents label="Splits" />;
  }
  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Splits</p>
      <ul className="space-y-1 text-sm">
        {rows.slice(0, 6).map((row, idx) => (
          <li
            key={`${row.date ?? idx}-${idx}`}
            className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          >
            <p className="font-medium tabular-nums">{row.date ?? "—"}</p>
            <p className="text-sm tabular-nums">
              {row.numerator != null && row.denominator != null
                ? `${row.numerator}-for-${row.denominator}`
                : row.label ?? "—"}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyEvents({ label }: { label: string }) {
  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-xs text-slate-600">No data.</p>
    </div>
  );
}

function HoldingsSection({
  research,
}: {
  research: ResearchPayload["research"];
}) {
  const holdings = (research?.holdings ?? []) as Array<{
    symbol?: string;
    name?: string;
    weight?: number;
  }>;
  if (holdings.length === 0) return null;
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
  if (!news || !news.items?.length) return null;
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
          <li
            key={`${item.url ?? idx}-${idx}`}
            className="border-b border-slate-800 pb-2 last:border-b-0"
          >
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

function providerClass(status?: string): string {
  switch (status) {
    case "live":
      return "border-bergt-green/40 bg-bergt-green/10 text-bergt-green";
    case "partial":
      return "border-amber-700/50 bg-amber-900/40 text-amber-200";
    case "unavailable":
      return "border-slate-700 bg-slate-800 text-slate-300";
    default:
      return "border-slate-700 bg-slate-900 text-slate-400";
  }
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
