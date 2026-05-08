import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";
import {
  StockChart,
  type ChartCandle,
  type ChartLevel,
  type ChartPattern,
  type ChartTradeMarker,
  type ChartZones,
} from "../components/StockChart";
import { VolumeProfile, type VolumeProfilePayload } from "../components/VolumeProfile";

type FeatureContribution = {
  feature: string;
  category: string;
  contribution: number;
  value: number;
  direction: "up" | "down";
};

type CategoryContribution = {
  category: string;
  label: string;
  contribution: number;
  direction: "up" | "down";
};

type Prediction = {
  direction?: "UP" | "DOWN" | "HOLD";
  confidence?: number;
  probabilityUp?: number;
  probabilityDown?: number;
  reason?: string;
  reasoning?: string;
  explanation?: {
    baseline: number;
    method: string;
    topFeatures: FeatureContribution[];
    categories?: CategoryContribution[];
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
  volume_profile?: VolumeProfilePayload | null;
  support_resistance?: ChartLevel[] | null;
};

type InsiderTrade = {
  date?: string | null;
  type?: string;
  isBuy?: boolean;
  name?: string | null;
  title?: string | null;
  shares?: number | null;
  price?: number | null;
  value?: number | null;
};

type InstitutionalHolding = {
  holder?: string | null;
  shares?: number | null;
  weightPct?: number | null;
  changeShares?: number | null;
  dateReported?: string | null;
};

type EarningsSurprise = {
  date?: string | null;
  actual?: number | null;
  estimated?: number | null;
  beat?: boolean | null;
  surprisePct?: number | null;
};

type UpcomingEarnings = {
  date?: string | null;
  epsEstimated?: number | null;
  revenueEstimated?: number | null;
  time?: string | null;
  fiscalDateEnding?: string | null;
};

type ResearchSignals = {
  insiderTrades?: InsiderTrade[];
  insiderSummary?: {
    buys90dShares?: number;
    sells90dShares?: number;
    netValue90d?: number;
  };
  institutionalHoldings?: InstitutionalHolding[];
  earningsSurprises?: EarningsSurprise[];
  earningsBeatRate?: number | null;
  upcomingEarnings?: UpcomingEarnings | null;
  daysUntilEarnings?: number | null;
};

type MacroInstrument = {
  symbol?: string;
  label?: string;
  value?: number | null;
  changePct?: number | null;
  asOf?: string | null;
};

type MacroContext = {
  vix?: MacroInstrument;
  yield10y?: MacroInstrument;
  dxy?: MacroInstrument;
};

type CryptoMetrics = {
  coinId?: string;
  symbol?: string;
  name?: string;
  marketCapRank?: number | null;
  marketCapUsd?: number | null;
  totalVolumeUsd?: number | null;
  currentPriceUsd?: number | null;
  priceChange24hPct?: number | null;
  priceChange7dPct?: number | null;
  priceChange30dPct?: number | null;
  ath?: { valueUsd?: number | null; changePct?: number | null; date?: string | null } | null;
  atl?: { valueUsd?: number | null; changePct?: number | null; date?: string | null } | null;
  community?: {
    twitterFollowers?: number | null;
    redditSubscribers?: number | null;
    redditActive48h?: number | null;
  } | null;
  developer?: {
    stars?: number | null;
    forks?: number | null;
    subscribers?: number | null;
    commitCount4Weeks?: number | null;
  } | null;
  sentimentVotesUpPct?: number | null;
  sentimentVotesDownPct?: number | null;
};

type FearGreedIndex = {
  value?: number | null;
  classification?: string | null;
  timestamp?: string | null;
};

type StockTwitsBlock = {
  symbol?: string;
  messageCount?: number | null;
  bullishCount?: number | null;
  bearishCount?: number | null;
  neutralCount?: number | null;
  avgVaderScore?: number | null;
  topPosts?: Array<{
    body?: string;
    created?: string | null;
    tag?: string | null;
    vader?: number | null;
    url?: string | null;
  }>;
};

type RedditBlock = {
  query?: string;
  subreddits?: string[];
  mentionCount24h?: number | null;
  mentionCount7d?: number | null;
  mentionTrendPct?: number | null;
  avgSentiment?: number | null;
  topPosts?: Array<{
    title?: string;
    score?: number | null;
    comments?: number | null;
    subreddit?: string | null;
    permalink?: string | null;
    vader?: number | null;
  }>;
};

type SocialSentiment = {
  stocktwits?: StockTwitsBlock;
  reddit?: RedditBlock;
  combined?: {
    totalMessages?: number | null;
    avgSentiment?: number | null;
  };
};

type ResearchPayload = {
  symbol: string;
  name: string;
  research?: {
    holdings?: Array<{ symbol?: string; name?: string; weight?: number }>;
  };
  researchDepth?: {
    cashflow?: Array<{
      date?: string;
      operatingCashFlow?: number | null;
      capitalExpenditure?: number | null;
      freeCashFlow?: number | null;
    }>;
    debt?: Array<{
      date?: string;
      totalDebt?: number | null;
      longTermDebt?: number | null;
      shortTermDebt?: number | null;
      totalEquity?: number | null;
      netDebt?: number | null;
    }>;
    rating?: {
      date?: string;
      rating?: string;
      ratingScore?: number;
      ratingRecommendation?: string;
    } | null;
    estimates?: Array<{
      date?: string;
      estimatedRevenueAvg?: number | null;
      estimatedRevenueLow?: number | null;
      estimatedRevenueHigh?: number | null;
      estimatedEpsAvg?: number | null;
      estimatedEpsLow?: number | null;
      estimatedEpsHigh?: number | null;
      numberAnalystsEstimatedEps?: number;
    }>;
  };
  researchSignals?: ResearchSignals;
  macroContext?: MacroContext;
  cryptoMetrics?: CryptoMetrics | null;
  fearGreedIndex?: FearGreedIndex | null;
  socialSentiment?: SocialSentiment | null;
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

  const transactionsQuery = useQuery({
    queryKey: ["paper-transactions", "for-analysis"],
    queryFn: () =>
      apiFetch<{ transactions: Array<{ symbol: string; side: "buy" | "sell"; qty: number; price: number; executedAt: string | null }> }>(
        "/api/paper-trading/transactions",
      ),
    enabled: !!decoded,
    refetchInterval: 60_000,
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
  const tradeMarkersForSymbol: ChartTradeMarker[] = (
    transactionsQuery.data?.transactions ?? []
  )
    .filter((tx) => tx.symbol === decoded.toUpperCase() && tx.executedAt)
    .map((tx) => ({
      time: tx.executedAt!,
      side: tx.side,
      qty: tx.qty,
      price: tx.price,
    }));
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

      <PredictionCard prediction={stock?.prediction} symbol={decoded} />
      <PatternsCard patterns={patterns} />

      {stockQuery.isLoading ? (
        <p className="text-sm text-slate-400">Loading chart…</p>
      ) : candles.length === 0 ? (
        <p className="text-sm text-slate-500">No chart data available.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
          <StockChart
            candles={candles}
            patterns={patterns}
            zones={stock?.prediction?.zones ?? null}
            levels={stock?.support_resistance ?? null}
            trades={tradeMarkersForSymbol}
          />
          <VolumeProfile profile={stock?.volume_profile ?? null} />
        </div>
      )}

      <FundamentalsSection info={stock?.info} provider={stock?.provider} />
      <ResearchDepthSection depth={research?.researchDepth} />
      <ResearchSignalsSection signals={research?.researchSignals} />
      <CryptoMetricsSection metrics={research?.cryptoMetrics} />
      <SocialSentimentSection social={research?.socialSentiment} />
      <MacroContextSection
        macro={research?.macroContext}
        fearGreed={research?.fearGreedIndex}
      />
      <EventsSection events={eventsQuery.data?.events} provider={eventsQuery.data?.provider} />
      <HoldingsSection research={research?.research} />
      <NewsSection news={research?.news} />
    </div>
  );
}

function PredictionCard({
  prediction,
  symbol,
}: {
  prediction?: Prediction | null;
  symbol?: string;
}) {
  if (!prediction || !prediction.direction) return null;
  const dir = prediction.direction;
  const confidence = prediction.confidence ?? 0;
  const pUp = prediction.probabilityUp ?? (dir === "UP" ? confidence : 1 - confidence);
  const pDown = prediction.probabilityDown ?? (dir === "DOWN" ? confidence : 1 - confidence);
  const baseCls =
    dir === "UP"
      ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
      : dir === "DOWN"
      ? "border-red-700/50 bg-red-900/40 text-red-200"
      : "border-slate-700 bg-slate-900 text-slate-300";

  const categories = prediction.explanation?.categories ?? [];

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

      <ProbabilityBars probabilityUp={pUp} probabilityDown={pDown} />

      {prediction.reasoning ? (
        <p className="mt-2 text-xs opacity-90">{prediction.reasoning}</p>
      ) : null}

      {prediction.zones ? (
        <>
          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
            <ZoneCell
              label="Entry"
              value={`${prediction.zones.entryLow.toFixed(2)} – ${prediction.zones.entryHigh.toFixed(2)}`}
            />
            <ZoneCell label="Stop" value={prediction.zones.stopLoss.toFixed(2)} accent="red" />
            <ZoneCell label="Target" value={prediction.zones.target.toFixed(2)} accent="green" />
            <ZoneCell label="ATR" value={prediction.zones.atr.toFixed(3)} />
          </div>
          <YieldBreakdown zones={prediction.zones} />
          {symbol ? (
            <PlacePaperOrderLink
              symbol={symbol}
              direction={dir}
              targetPrice={prediction.zones.target}
              entryHint={prediction.zones.entryLow}
            />
          ) : null}
        </>
      ) : null}

      {categories.length > 0 ? (
        <div className="mt-3">
          <p className="text-xs uppercase tracking-wide opacity-70">
            Where the signal comes from
          </p>
          <ul className="mt-1 space-y-1">
            {categories.map((c) => (
              <li
                key={c.category}
                className="flex items-center justify-between text-xs tabular-nums"
              >
                <span>{c.label}</span>
                <CategoryBar contribution={c.contribution} />
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] uppercase tracking-wide opacity-50">
            Categories: Fundamentals · News · Trend · Technical · Volume — combined via {prediction.explanation?.method}
          </p>
        </div>
      ) : null}

      {prediction.explanation && prediction.explanation.topFeatures.length > 0 ? (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer opacity-70 hover:opacity-100">
            Top contributing features ({prediction.explanation.topFeatures.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {prediction.explanation.topFeatures.map((f) => (
              <li
                key={f.feature}
                className="flex items-center justify-between tabular-nums"
              >
                <span className="font-mono">
                  <span className="mr-2 rounded-full border border-slate-600/40 bg-slate-900/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wide opacity-70">
                    {f.category}
                  </span>
                  {f.feature}
                </span>
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
        </details>
      ) : null}

      {prediction.reason ? (
        <p className="mt-2 text-xs opacity-80">{prediction.reason}</p>
      ) : null}
    </section>
  );
}

function PlacePaperOrderLink({
  symbol,
  direction,
  targetPrice,
  entryHint,
}: {
  symbol: string;
  direction: "UP" | "DOWN" | "HOLD";
  targetPrice: number;
  entryHint: number;
}) {
  if (direction === "HOLD") return null;
  const side = direction === "UP" ? "buy" : "sell";
  const params = new URLSearchParams({
    symbol,
    side,
    targetPrice: targetPrice.toFixed(2),
    limitPrice: entryHint.toFixed(2),
    source: "auto-recommendation",
  });
  return (
    <div className="mt-3">
      <Link to={`/paper-trading?${params.toString()}`} className="btn">
        Place paper order at this target
      </Link>
    </div>
  );
}

function ProbabilityBars({
  probabilityUp,
  probabilityDown,
}: {
  probabilityUp: number;
  probabilityDown: number;
}) {
  const upPct = Math.max(0, Math.min(100, probabilityUp * 100));
  const downPct = Math.max(0, Math.min(100, probabilityDown * 100));
  return (
    <div className="mt-3 space-y-2 text-xs">
      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-bergt-green">P(UP)</span>
          <span className="tabular-nums">{upPct.toFixed(1)}%</span>
        </div>
        <div className="mt-1 h-1.5 w-full rounded-full bg-slate-800/80">
          <div
            className="h-full rounded-full bg-bergt-green/70"
            style={{ width: `${upPct}%` }}
          />
        </div>
      </div>
      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-red-300">P(DOWN)</span>
          <span className="tabular-nums">{downPct.toFixed(1)}%</span>
        </div>
        <div className="mt-1 h-1.5 w-full rounded-full bg-slate-800/80">
          <div
            className="h-full rounded-full bg-red-500/70"
            style={{ width: `${downPct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function CategoryBar({ contribution }: { contribution: number }) {
  const magnitude = Math.min(1, Math.abs(contribution));
  const widthPct = magnitude * 100;
  const positive = contribution >= 0;
  return (
    <span className="flex items-center gap-2">
      <span
        className={positive ? "text-bergt-green" : "text-red-400"}
      >
        {positive ? "+" : ""}
        {contribution.toFixed(2)}
      </span>
      <span className="relative inline-block h-1.5 w-24 rounded-full bg-slate-800/80">
        <span
          className={`absolute top-0 h-full rounded-full ${
            positive ? "left-1/2 bg-bergt-green/70" : "right-1/2 bg-red-500/70"
          }`}
          style={{ width: `${widthPct / 2}%` }}
        />
        <span className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
      </span>
    </span>
  );
}

function YieldBreakdown({ zones }: { zones: ChartZones }) {
  const gross = zones.grossTargetPct;
  const fee = zones.feeRoundTripPct;
  const tax = zones.taxDragPct;
  const net = zones.netTargetPct;
  if (gross == null || net == null) return null;
  const meets = zones.meetsMinimum;
  const minYield = zones.minTargetYieldPct;
  const taxRate = zones.effectiveTaxRatePct ?? 0;
  return (
    <div className="mt-3 rounded-md border border-slate-700/40 bg-slate-950/40 p-3 text-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[10px] uppercase tracking-wide opacity-70">
          Net-yield projection
        </p>
        {meets === true ? (
          <span className="rounded-full border border-bergt-green/40 bg-bergt-green/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-bergt-green">
            Meets {minYield?.toFixed(1)}% minimum
          </span>
        ) : meets === false ? (
          <span className="rounded-full border border-amber-700/40 bg-amber-900/30 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-200">
            Below {minYield?.toFixed(1)}% minimum
          </span>
        ) : null}
      </div>
      <ul className="mt-2 space-y-1 tabular-nums">
        <YieldRow label="Gross target" value={gross} positive />
        {fee != null ? <YieldRow label="Round-trip fees" value={-Math.abs(fee)} /> : null}
        {tax != null && tax > 0 ? (
          <YieldRow
            label={`Tax @ ${taxRate.toFixed(2)}%`}
            value={-Math.abs(tax)}
          />
        ) : null}
        <li className="mt-1 flex items-baseline justify-between border-t border-slate-700/40 pt-1">
          <span className="font-medium">Net target</span>
          <span
            className={
              net >= 0 ? "font-semibold text-bergt-green" : "font-semibold text-red-400"
            }
          >
            {net >= 0 ? "+" : ""}
            {net.toFixed(2)}%
          </span>
        </li>
      </ul>
    </div>
  );
}

function YieldRow({
  label,
  value,
  positive,
}: {
  label: string;
  value: number;
  positive?: boolean;
}) {
  const cls = positive
    ? "text-bergt-green"
    : value <= 0
    ? "text-red-300"
    : "text-slate-300";
  return (
    <li className="flex items-baseline justify-between">
      <span className="opacity-80">{label}</span>
      <span className={cls}>
        {value >= 0 && positive ? "+" : ""}
        {value.toFixed(2)}%
      </span>
    </li>
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

function ResearchDepthSection({
  depth,
}: {
  depth: ResearchPayload["researchDepth"];
}) {
  if (!depth) return null;
  const cashflow = depth.cashflow ?? [];
  const debt = depth.debt ?? [];
  const rating = depth.rating;
  const estimates = depth.estimates ?? [];
  const hasAnything =
    cashflow.length > 0 || debt.length > 0 || estimates.length > 0 || !!rating;
  if (!hasAnything) return null;

  return (
    <section className="card">
      <header className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Research depth</h2>
        <span className="text-xs text-slate-500">via FMP</span>
      </header>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {rating ? <RatingCard rating={rating} /> : null}
        {estimates.length > 0 ? <EstimatesTable rows={estimates} /> : null}
        {cashflow.length > 0 ? <CashflowTable rows={cashflow} /> : null}
        {debt.length > 0 ? <DebtTable rows={debt} /> : null}
      </div>
    </section>
  );
}

function RatingCard({
  rating,
}: {
  rating: NonNullable<NonNullable<ResearchPayload["researchDepth"]>["rating"]>;
}) {
  const recommendation = rating.ratingRecommendation || rating.rating || "—";
  const tone = recommendation.toLowerCase();
  const cls = tone.includes("buy")
    ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
    : tone.includes("sell")
    ? "border-red-700/50 bg-red-900/40 text-red-200"
    : "border-slate-700 bg-slate-900 text-slate-300";
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">Analyst rating</p>
      <div className={`mt-1 rounded-md border px-3 py-2 text-sm ${cls}`}>
        <p className="font-semibold">{recommendation}</p>
        <p className="text-xs opacity-80">
          {rating.rating ? `${rating.rating}` : ""}
          {rating.ratingScore != null ? ` · score ${rating.ratingScore}/5` : ""}
          {rating.date ? ` · ${rating.date}` : ""}
        </p>
      </div>
    </div>
  );
}

function EstimatesTable({
  rows,
}: {
  rows: NonNullable<NonNullable<ResearchPayload["researchDepth"]>["estimates"]>;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">Forward estimates</p>
      <ul className="mt-1 space-y-1 text-sm tabular-nums">
        {rows.slice(0, 4).map((row, idx) => (
          <li
            key={`${row.date ?? idx}-${idx}`}
            className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          >
            <span className="text-xs text-slate-400">{row.date ?? "—"}</span>
            <span className="text-xs">
              EPS {row.estimatedEpsAvg != null ? row.estimatedEpsAvg.toFixed(2) : "—"}
              {row.numberAnalystsEstimatedEps
                ? ` · n=${row.numberAnalystsEstimatedEps}`
                : ""}
            </span>
            <span className="text-xs">
              Rev {row.estimatedRevenueAvg ? formatLarge(row.estimatedRevenueAvg) : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CashflowTable({
  rows,
}: {
  rows: NonNullable<NonNullable<ResearchPayload["researchDepth"]>["cashflow"]>;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">Cash flow</p>
      <ul className="mt-1 space-y-1 text-sm tabular-nums">
        {rows.slice(0, 4).map((row, idx) => (
          <li
            key={`${row.date ?? idx}-${idx}`}
            className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          >
            <span className="text-xs text-slate-400">{row.date ?? "—"}</span>
            <span className="text-xs">
              FCF {row.freeCashFlow ? formatLarge(row.freeCashFlow) : "—"}
            </span>
            <span className="text-xs text-slate-500">
              CapEx {row.capitalExpenditure ? formatLarge(Math.abs(row.capitalExpenditure)) : "—"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DebtTable({
  rows,
}: {
  rows: NonNullable<NonNullable<ResearchPayload["researchDepth"]>["debt"]>;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">Debt &amp; equity</p>
      <ul className="mt-1 space-y-1 text-sm tabular-nums">
        {rows.slice(0, 4).map((row, idx) => {
          const ratio =
            row.totalDebt != null && row.totalEquity != null && row.totalEquity > 0
              ? row.totalDebt / row.totalEquity
              : null;
          return (
            <li
              key={`${row.date ?? idx}-${idx}`}
              className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-2 py-1.5"
            >
              <span className="text-xs text-slate-400">{row.date ?? "—"}</span>
              <span className="text-xs">
                Debt {row.totalDebt ? formatLarge(row.totalDebt) : "—"}
              </span>
              <span className="text-xs text-slate-500">
                D/E {ratio != null ? ratio.toFixed(2) : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ResearchSignalsSection({ signals }: { signals: ResearchSignals | undefined }) {
  if (!signals) return null;

  const insiderTrades = signals.insiderTrades ?? [];
  const insiderSummary = signals.insiderSummary ?? {};
  const institutional = signals.institutionalHoldings ?? [];
  const surprises = signals.earningsSurprises ?? [];
  const upcoming = signals.upcomingEarnings ?? null;

  const hasAnyData =
    insiderTrades.length > 0 ||
    institutional.length > 0 ||
    surprises.length > 0 ||
    upcoming;

  if (!hasAnyData) return null;

  const beatRatePct =
    signals.earningsBeatRate != null ? Math.round(signals.earningsBeatRate * 100) : null;
  const insiderNetValue = insiderSummary.netValue90d ?? 0;
  const insiderNetSign = insiderNetValue > 0 ? "+" : insiderNetValue < 0 ? "−" : "";

  return (
    <section className="card space-y-3" data-testid="research-signals-section">
      <header>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Research signals
        </h2>
        <p className="text-xs text-slate-500">
          Insider activity, institutional ownership, earnings beat history, next earnings.
        </p>
      </header>

      <dl className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Insider net value (90d)
          </dt>
          <dd className="mt-1 font-mono text-base">
            {insiderNetSign}
            {Math.abs(insiderNetValue).toLocaleString(undefined, {
              maximumFractionDigits: 0,
            })}
          </dd>
          <dd className="mt-1 text-xs text-slate-400">
            Buys {Math.round(insiderSummary.buys90dShares ?? 0)} sh /
            Sells {Math.round(insiderSummary.sells90dShares ?? 0)} sh
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Earnings beat rate
          </dt>
          <dd className="mt-1 font-mono text-base">
            {beatRatePct != null ? `${beatRatePct}%` : "—"}
          </dd>
          <dd className="mt-1 text-xs text-slate-400">
            {surprises.length > 0
              ? `${surprises.length} reported quarter${surprises.length === 1 ? "" : "s"}`
              : "no quarters reported"}
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Next earnings
          </dt>
          <dd className="mt-1 font-mono text-base">
            {upcoming?.date ?? "—"}
          </dd>
          <dd className="mt-1 text-xs text-slate-400">
            {signals.daysUntilEarnings != null
              ? `${signals.daysUntilEarnings} days, ${upcoming?.time ?? "tbd"}`
              : "no upcoming event"}
          </dd>
        </div>
      </dl>

      {insiderTrades.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Recent insider transactions
          </h3>
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Date</th>
                <th>Insider</th>
                <th>Type</th>
                <th className="text-right">Shares</th>
                <th className="text-right">Price</th>
                <th className="text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              {insiderTrades.slice(0, 8).map((tx, idx) => (
                <tr key={idx} className="border-t border-slate-800">
                  <td className="py-1">{tx.date ?? "—"}</td>
                  <td>{tx.name ?? "—"}</td>
                  <td className={tx.isBuy ? "text-bergt-green" : "text-red-300"}>
                    {tx.isBuy ? "BUY" : "SELL"}
                  </td>
                  <td className="text-right">{tx.shares?.toLocaleString() ?? "—"}</td>
                  <td className="text-right">
                    {tx.price != null ? tx.price.toFixed(2) : "—"}
                  </td>
                  <td className="text-right">
                    {tx.value != null
                      ? tx.value.toLocaleString(undefined, { maximumFractionDigits: 0 })
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {institutional.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Top institutional holders
          </h3>
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Holder</th>
                <th className="text-right">Shares</th>
                <th className="text-right">Weight %</th>
                <th className="text-right">Δ Shares</th>
                <th>As of</th>
              </tr>
            </thead>
            <tbody>
              {institutional.slice(0, 6).map((row, idx) => (
                <tr key={idx} className="border-t border-slate-800">
                  <td className="py-1">{row.holder ?? "—"}</td>
                  <td className="text-right">{row.shares?.toLocaleString() ?? "—"}</td>
                  <td className="text-right">
                    {row.weightPct != null ? row.weightPct.toFixed(2) : "—"}
                  </td>
                  <td
                    className={
                      "text-right " +
                      ((row.changeShares ?? 0) > 0
                        ? "text-bergt-green"
                        : (row.changeShares ?? 0) < 0
                        ? "text-red-300"
                        : "")
                    }
                  >
                    {row.changeShares != null
                      ? row.changeShares.toLocaleString()
                      : "—"}
                  </td>
                  <td>{row.dateReported ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {surprises.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Earnings beat history
          </h3>
          <table className="mt-2 w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Date</th>
                <th className="text-right">Actual EPS</th>
                <th className="text-right">Estimated</th>
                <th className="text-right">Surprise %</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {surprises.map((row, idx) => (
                <tr key={idx} className="border-t border-slate-800">
                  <td className="py-1">{row.date ?? "—"}</td>
                  <td className="text-right">
                    {row.actual != null ? row.actual.toFixed(2) : "—"}
                  </td>
                  <td className="text-right">
                    {row.estimated != null ? row.estimated.toFixed(2) : "—"}
                  </td>
                  <td className="text-right">
                    {row.surprisePct != null ? `${row.surprisePct.toFixed(1)}%` : "—"}
                  </td>
                  <td className={row.beat ? "text-bergt-green" : "text-red-300"}>
                    {row.beat == null ? "—" : row.beat ? "BEAT" : "MISS"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function CryptoMetricsSection({ metrics }: { metrics: CryptoMetrics | null | undefined }) {
  if (!metrics) return null;

  const fmtUsd = (value: number | null | undefined): string => {
    if (value == null) return "—";
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    if (Math.abs(value) >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
    return `$${value.toFixed(2)}`;
  };

  const fmtPct = (value: number | null | undefined): string => {
    if (value == null) return "—";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return `${sign}${Math.abs(value).toFixed(2)}%`;
  };

  const fmtCount = (value: number | null | undefined): string => {
    if (value == null) return "—";
    return Math.round(value).toLocaleString();
  };

  return (
    <section className="card space-y-3" data-testid="crypto-metrics-section">
      <header>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Crypto metrics
        </h2>
        <p className="text-xs text-slate-500">
          Market depth, ATH/ATL distance, developer + community activity (CoinGecko).
        </p>
      </header>
      <dl className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Market cap
          </dt>
          <dd className="mt-1 font-mono text-base">{fmtUsd(metrics.marketCapUsd)}</dd>
          <dd className="mt-1 text-xs text-slate-400">
            {metrics.marketCapRank != null ? `Rank #${metrics.marketCapRank}` : "—"}
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            24h volume
          </dt>
          <dd className="mt-1 font-mono text-base">{fmtUsd(metrics.totalVolumeUsd)}</dd>
          <dd className="mt-1 text-xs text-slate-400">
            24h {fmtPct(metrics.priceChange24hPct)} · 7d {fmtPct(metrics.priceChange7dPct)} · 30d {fmtPct(metrics.priceChange30dPct)}
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            ATH / ATL
          </dt>
          <dd className="mt-1 font-mono text-base">
            {fmtUsd(metrics.ath?.valueUsd)}
          </dd>
          <dd className="mt-1 text-xs text-slate-400">
            From ATH {fmtPct(metrics.ath?.changePct)} · From ATL {fmtPct(metrics.atl?.changePct)}
          </dd>
        </div>
      </dl>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="text-xs uppercase tracking-wide text-slate-500">
            Developer activity
          </h3>
          <dl className="mt-1 grid grid-cols-2 gap-1 text-xs">
            <dt className="text-slate-500">Stars</dt>
            <dd className="font-mono">{fmtCount(metrics.developer?.stars)}</dd>
            <dt className="text-slate-500">Forks</dt>
            <dd className="font-mono">{fmtCount(metrics.developer?.forks)}</dd>
            <dt className="text-slate-500">Commits 4w</dt>
            <dd className="font-mono">{fmtCount(metrics.developer?.commitCount4Weeks)}</dd>
            <dt className="text-slate-500">Subscribers</dt>
            <dd className="font-mono">{fmtCount(metrics.developer?.subscribers)}</dd>
          </dl>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <h3 className="text-xs uppercase tracking-wide text-slate-500">
            Community activity
          </h3>
          <dl className="mt-1 grid grid-cols-2 gap-1 text-xs">
            <dt className="text-slate-500">Twitter</dt>
            <dd className="font-mono">{fmtCount(metrics.community?.twitterFollowers)}</dd>
            <dt className="text-slate-500">Reddit subs</dt>
            <dd className="font-mono">{fmtCount(metrics.community?.redditSubscribers)}</dd>
            <dt className="text-slate-500">Reddit 48h</dt>
            <dd className="font-mono">{fmtCount(metrics.community?.redditActive48h)}</dd>
            <dt className="text-slate-500">Sentiment up</dt>
            <dd className="font-mono">{fmtPct(metrics.sentimentVotesUpPct)}</dd>
          </dl>
        </div>
      </div>
    </section>
  );
}

function SocialSentimentSection({ social }: { social: SocialSentiment | null | undefined }) {
  if (!social) return null;
  const st = social.stocktwits ?? {};
  const rd = social.reddit ?? {};
  const combined = social.combined ?? {};

  const stMessages = st.messageCount ?? 0;
  const rdMentions = rd.mentionCount24h ?? 0;
  const totalMessages = combined.totalMessages ?? stMessages + rdMentions;
  if (totalMessages === 0) return null;

  const fmtPct = (value: number | null | undefined): string => {
    if (value == null) return "—";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return `${sign}${Math.abs(value).toFixed(2)}%`;
  };

  const fmtScore = (value: number | null | undefined): string => {
    if (value == null) return "—";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return `${sign}${Math.abs(value).toFixed(2)}`;
  };

  const sentimentColor = (value: number | null | undefined): string => {
    if (value == null) return "text-slate-400";
    if (value > 0.05) return "text-bergt-green";
    if (value < -0.05) return "text-red-300";
    return "text-slate-400";
  };

  const bullishRatio =
    (st.bullishCount ?? 0) + (st.bearishCount ?? 0) > 0
      ? ((st.bullishCount ?? 0) /
          ((st.bullishCount ?? 0) + (st.bearishCount ?? 0))) *
        100
      : null;

  return (
    <section className="card space-y-3" data-testid="social-sentiment-section">
      <header>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Retail sentiment
        </h2>
        <p className="text-xs text-slate-500">
          Combined StockTwits + Reddit chatter from the last 24 hours.
        </p>
      </header>

      <dl className="grid gap-3 md:grid-cols-3">
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Combined sentiment
          </dt>
          <dd className={`mt-1 font-mono text-base ${sentimentColor(combined.avgSentiment)}`}>
            {fmtScore(combined.avgSentiment)}
          </dd>
          <dd className="mt-1 text-xs text-slate-400">
            {totalMessages} messages weighted across sources
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            StockTwits stream
          </dt>
          <dd className="mt-1 font-mono text-base">{stMessages}</dd>
          <dd className="mt-1 text-xs text-slate-400">
            {bullishRatio != null
              ? `${bullishRatio.toFixed(0)}% bullish · ${st.bearishCount ?? 0} bearish`
              : `${st.bullishCount ?? 0} bullish / ${st.bearishCount ?? 0} bearish`}
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
          <dt className="text-xs uppercase tracking-wide text-slate-500">
            Reddit mentions 24h
          </dt>
          <dd className="mt-1 font-mono text-base">{rdMentions}</dd>
          <dd className="mt-1 text-xs text-slate-400">
            7d {rd.mentionCount7d ?? 0} · trend {fmtPct(rd.mentionTrendPct)}
          </dd>
        </div>
      </dl>

      {(rd.topPosts && rd.topPosts.length > 0) || (st.topPosts && st.topPosts.length > 0) ? (
        <div className="grid gap-3 md:grid-cols-2">
          {rd.topPosts && rd.topPosts.length > 0 ? (
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <h3 className="text-xs uppercase tracking-wide text-slate-500">
                Top Reddit posts
              </h3>
              <ul className="mt-2 space-y-1 text-xs">
                {rd.topPosts.slice(0, 4).map((post, idx) => (
                  <li key={idx} className="border-t border-slate-800 pt-1">
                    {post.permalink ? (
                      <a
                        href={post.permalink}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-bergt-green"
                      >
                        {post.title}
                      </a>
                    ) : (
                      <span>{post.title}</span>
                    )}
                    <div className="text-[10px] text-slate-500">
                      r/{post.subreddit} · {post.score ?? 0}↑ · {post.comments ?? 0}💬 · {fmtScore(post.vader)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {st.topPosts && st.topPosts.length > 0 ? (
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <h3 className="text-xs uppercase tracking-wide text-slate-500">
                Top StockTwits posts
              </h3>
              <ul className="mt-2 space-y-1 text-xs">
                {st.topPosts.slice(0, 4).map((post, idx) => (
                  <li key={idx} className="border-t border-slate-800 pt-1">
                    <span>{post.body}</span>
                    <div className="text-[10px] text-slate-500">
                      {post.tag ? `${post.tag.toUpperCase()} · ` : ""}
                      VADER {fmtScore(post.vader)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function MacroContextSection({
  macro,
  fearGreed,
}: {
  macro: MacroContext | undefined;
  fearGreed: FearGreedIndex | null | undefined;
}) {
  const items: Array<[string, MacroInstrument | undefined]> = [
    ["VIX", macro?.vix],
    ["10Y Yield", macro?.yield10y],
    ["DXY", macro?.dxy],
  ];
  const hasMacroData = items.some(([, v]) => v && v.value != null);
  const hasFearGreed = fearGreed != null && fearGreed.value != null;
  if (!hasMacroData && !hasFearGreed) return null;

  return (
    <section className="card space-y-2" data-testid="macro-context-section">
      <header>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Macro context
        </h2>
        <p className="text-xs text-slate-500">
          Market-wide weather report. Read every per-symbol signal in this context.
        </p>
      </header>
      <dl className="grid gap-3 sm:grid-cols-4">
        {items.map(([label, instr]) => {
          const value = instr?.value;
          const changePct = instr?.changePct;
          const changeSign = changePct != null && changePct > 0 ? "+" : "";
          const changeColor =
            changePct == null
              ? "text-slate-400"
              : changePct > 0
              ? "text-bergt-green"
              : changePct < 0
              ? "text-red-300"
              : "text-slate-400";
          return (
            <div key={label} className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
              <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
              <dd className="mt-1 font-mono text-base">
                {value != null ? value.toFixed(2) : "—"}
              </dd>
              <dd className={`mt-1 text-xs ${changeColor}`}>
                {changePct != null
                  ? `${changeSign}${changePct.toFixed(2)}% (${instr?.asOf ?? "—"})`
                  : "no quote"}
              </dd>
            </div>
          );
        })}
        {hasFearGreed ? (
          <div
            className="rounded-md border border-slate-800 bg-slate-900/40 p-3"
            data-testid="fear-greed-card"
          >
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Crypto Fear &amp; Greed
            </dt>
            <dd className="mt-1 font-mono text-base">
              {fearGreed?.value != null ? fearGreed.value : "—"}
            </dd>
            <dd className="mt-1 text-xs text-slate-400">
              {fearGreed?.classification ?? "—"}
            </dd>
          </div>
        ) : null}
      </dl>
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
