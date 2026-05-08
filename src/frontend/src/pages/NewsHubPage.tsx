import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { apiFetch } from "../api/client";

type NewsItem = {
  title?: string;
  summary?: string;
  url?: string | null;
  timestamp?: string | null;
  source?: string | null;
  score?: number | null;
  label?: "bullish" | "bearish" | "neutral" | string | null;
  tickers?: string[];
};

type FeedResponse = {
  items: NewsItem[];
  total: number;
  limit: number;
  offset: number;
  sources: string[];
};

type SentimentFilter = "" | "bullish" | "bearish" | "neutral";

const TIME_WINDOW_KEYS: Array<{ value: string; key: string }> = [
  { value: "", key: "news.filters.windowAny" },
  { value: "1h", key: "news.filters.window1h" },
  { value: "6h", key: "news.filters.window6h" },
  { value: "24h", key: "news.filters.window24h" },
  { value: "3d", key: "news.filters.window3d" },
  { value: "7d", key: "news.filters.window7d" },
];

function windowToSinceIso(value: string): string | undefined {
  if (!value) return undefined;
  const now = Date.now();
  const ms =
    value === "1h"
      ? 1 * 60 * 60 * 1000
      : value === "6h"
      ? 6 * 60 * 60 * 1000
      : value === "24h"
      ? 24 * 60 * 60 * 1000
      : value === "3d"
      ? 3 * 24 * 60 * 60 * 1000
      : value === "7d"
      ? 7 * 24 * 60 * 60 * 1000
      : 0;
  if (!ms) return undefined;
  return new Date(now - ms).toISOString();
}

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "—";
  try {
    return new Date(raw).toLocaleString();
  } catch {
    return raw;
  }
}

function sentimentClass(label: string | null | undefined): string {
  if (label === "bullish") return "border-bergt-green/40 bg-bergt-green/10 text-bergt-green";
  if (label === "bearish") return "border-red-700/50 bg-red-900/40 text-red-300";
  return "border-slate-700 bg-slate-900 text-slate-300";
}

const PAGE_SIZE = 50;

export function NewsHubPage() {
  const { t } = useTranslation();
  const [source, setSource] = useState("");
  const [sentiment, setSentiment] = useState<SentimentFilter>("");
  const [timeWindow, setTimeWindow] = useState("");
  const [symbol, setSymbol] = useState("");
  const [offset, setOffset] = useState(0);

  const since = useMemo(() => windowToSinceIso(timeWindow), [timeWindow]);

  const queryKey = [
    "news-feed",
    { source, sentiment, timeWindow, symbol: symbol.trim().toUpperCase(), offset },
  ];

  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (source) params.set("sources", source);
  if (sentiment) params.set("sentiment", sentiment);
  if (since) params.set("since", since);
  if (symbol.trim()) params.set("symbol", symbol.trim().toUpperCase());

  const feedQuery = useQuery({
    queryKey,
    queryFn: () => apiFetch<FeedResponse>(`/api/news/feed?${params.toString()}`),
    refetchInterval: 5 * 60_000,
  });

  const data = feedQuery.data;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const availableSources = data?.sources ?? [];

  return (
    <div className="space-y-4" data-testid="news-hub-page">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{t("news.title")}</h1>
        <p className="text-sm text-slate-400">{t("news.subtitle")}</p>
      </header>

      <section className="card space-y-3">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("news.filters.source")}</span>
            <select
              className="input"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">{t("news.filters.sourceAll")}</option>
              <option value="fmp">FMP</option>
              <option value="alpha_vantage">Alpha Vantage</option>
              <option value="rss">RSS feeds</option>
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("news.filters.sentiment")}</span>
            <select
              className="input"
              value={sentiment}
              onChange={(e) => {
                setSentiment(e.target.value as SentimentFilter);
                setOffset(0);
              }}
            >
              <option value="">{t("news.filters.sentimentAny")}</option>
              <option value="bullish">{t("news.filters.sentimentBullish")}</option>
              <option value="bearish">{t("news.filters.sentimentBearish")}</option>
              <option value="neutral">{t("news.filters.sentimentNeutral")}</option>
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("news.filters.timeWindow")}</span>
            <select
              className="input"
              value={timeWindow}
              onChange={(e) => {
                setTimeWindow(e.target.value);
                setOffset(0);
              }}
            >
              {TIME_WINDOW_KEYS.map((w) => (
                <option key={w.value} value={w.value}>
                  {t(w.key)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("news.filters.symbolContains")}</span>
            <input
              className="input"
              value={symbol}
              onChange={(e) => {
                setSymbol(e.target.value);
                setOffset(0);
              }}
              placeholder="AAPL"
            />
          </label>
        </div>
        <p className="text-xs text-slate-500">
          {feedQuery.isLoading
            ? t("news.loading")
            : t("news.matchSummary", {
                count: total,
                sources: availableSources.join(", ") || "—",
              })}
        </p>
      </section>

      <section className="space-y-3" data-testid="news-hub-feed">
        {items.length === 0 && !feedQuery.isLoading ? (
          <p className="text-sm text-slate-500">{t("news.empty")}</p>
        ) : null}
        {items.map((item, idx) => (
          <article key={`${item.url ?? "noUrl"}-${idx}`} className="card space-y-2">
            <header className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-medium">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-bergt-green">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </h2>
              <span className="text-xs text-slate-500">{formatTimestamp(item.timestamp)}</span>
            </header>
            {item.summary ? <p className="text-xs text-slate-300">{item.summary}</p> : null}
            <footer className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide">
              {item.source ? (
                <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                  {item.source}
                </span>
              ) : null}
              {item.label ? (
                <span className={`rounded-full border px-2 py-0.5 ${sentimentClass(item.label)}`}>
                  {item.label}
                  {item.score != null ? ` · ${item.score.toFixed(2)}` : ""}
                </span>
              ) : null}
              {(item.tickers ?? []).map((ticker) => (
                <Link
                  key={ticker}
                  to={`/analysis/${encodeURIComponent(ticker)}`}
                  className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300 hover:text-bergt-green"
                >
                  ${ticker}
                </Link>
              ))}
            </footer>
          </article>
        ))}
      </section>

      <nav className="flex items-center justify-between text-xs text-slate-400">
        <button
          type="button"
          className="btn"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          {t("news.newer")}
        </button>
        <span>
          {t("news.showing", {
            from: offset + 1,
            to: Math.min(offset + items.length, total),
            total,
          })}
        </span>
        <button
          type="button"
          className="btn"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          {t("news.older")}
        </button>
      </nav>
    </div>
  );
}
