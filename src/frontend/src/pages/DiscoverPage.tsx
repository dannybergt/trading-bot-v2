import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { apiFetch } from "../api/client";

type TrendingSymbol = {
  symbol: string;
  mentionCountRecent: number;
  mentionCountBaseline: number;
  mentionTrendPct: number | null;
  avgSentimentRecent: number;
  sentimentBurst: number;
  sampleTitle?: string | null;
  sampleUrl?: string | null;
};

type Mover = {
  symbol: string;
  name?: string | null;
  price?: number | null;
  change?: number | null;
  changesPercentage?: number | null;
};

type InsiderCluster = {
  symbol: string;
  uniqueInsiders: number;
  buyCount: number;
  sellCount: number;
  netValue: number;
  direction: "buy_cluster" | "sell_cluster" | "mixed";
  lastTransactionDate?: string | null;
};

type DiscoveryDashboard = {
  trending: TrendingSymbol[];
  topMovers: {
    gainers?: Mover[];
    losers?: Mover[];
    actives?: Mover[];
  };
  insiderClusters: InsiderCluster[];
};

function fmtPct(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

function fmtScore(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

function fmtPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toFixed(2);
}

function fmtUsd(value: number | null | undefined): string {
  if (value == null) return "—";
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(2)}K`;
  return `$${value.toFixed(2)}`;
}

const directionClass: Record<InsiderCluster["direction"], string> = {
  buy_cluster: "border-bergt-green/40 bg-bergt-green/10 text-bergt-green",
  sell_cluster: "border-red-700/50 bg-red-900/40 text-red-200",
  mixed: "border-slate-700 bg-slate-900 text-slate-300",
};

export function DiscoverPage() {
  const { t } = useTranslation();
  const directionLabel: Record<InsiderCluster["direction"], string> = {
    buy_cluster: t("discover.clusters.labelBuy"),
    sell_cluster: t("discover.clusters.labelSell"),
    mixed: t("discover.clusters.labelMixed"),
  };
  const query = useQuery({
    queryKey: ["discover-dashboard"],
    queryFn: () => apiFetch<DiscoveryDashboard>("/api/discover"),
    refetchInterval: 15 * 60_000,
  });

  const data = query.data;
  const trending = data?.trending ?? [];
  const movers = data?.topMovers ?? {};
  const clusters = data?.insiderClusters ?? [];

  return (
    <div className="space-y-6" data-testid="discover-page">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{t("discover.title")}</h1>
        <p className="text-sm text-slate-400">{t("discover.subtitle")}</p>
      </header>

      {query.isLoading ? <p className="text-sm text-slate-400">{t("discover.loading")}</p> : null}

      <section className="card space-y-3" data-testid="discover-trending">
        <header>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            {t("discover.trending.title")}
          </h2>
          <p className="text-xs text-slate-500">{t("discover.trending.subtitle")}</p>
        </header>
        {trending.length === 0 ? (
          <p className="text-xs text-slate-500">{t("discover.trending.empty")}</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Symbol</th>
                <th className="text-right">Mentions 24h</th>
                <th className="text-right">Trend</th>
                <th className="text-right">Sentiment</th>
                <th className="text-right">Burst</th>
                <th>Sample headline</th>
              </tr>
            </thead>
            <tbody>
              {trending.map((row) => (
                <tr key={row.symbol} className="border-t border-slate-800">
                  <td className="py-1">
                    <Link
                      to={`/analysis/${encodeURIComponent(row.symbol)}`}
                      className="font-medium hover:text-bergt-green"
                    >
                      ${row.symbol}
                    </Link>
                  </td>
                  <td className="text-right">{row.mentionCountRecent}</td>
                  <td className="text-right">{fmtPct(row.mentionTrendPct)}</td>
                  <td className="text-right">{fmtScore(row.avgSentimentRecent)}</td>
                  <td
                    className={`text-right ${
                      row.sentimentBurst > 0
                        ? "text-bergt-green"
                        : row.sentimentBurst < 0
                        ? "text-red-300"
                        : "text-slate-400"
                    }`}
                  >
                    {fmtScore(row.sentimentBurst)}
                  </td>
                  <td className="text-slate-400">
                    {row.sampleUrl && row.sampleTitle ? (
                      <a
                        href={row.sampleUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-bergt-green"
                      >
                        {row.sampleTitle.slice(0, 80)}
                      </a>
                    ) : (
                      row.sampleTitle ?? ""
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card space-y-3" data-testid="discover-movers">
        <header>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            {t("discover.movers.title")}
          </h2>
          <p className="text-xs text-slate-500">{t("discover.movers.subtitle")}</p>
        </header>
        <div className="grid gap-3 md:grid-cols-3">
          {(["gainers", "losers", "actives"] as const).map((bucket) => (
            <div
              key={bucket}
              className="rounded-md border border-slate-800 bg-slate-900/40 p-3"
              data-testid={`discover-movers-${bucket}`}
            >
              <h3 className="text-xs uppercase tracking-wide text-slate-500">
                {bucket}
              </h3>
              <ul className="mt-2 space-y-1 text-xs">
                {(movers[bucket] ?? []).slice(0, 10).map((row) => (
                  <li key={row.symbol} className="flex justify-between gap-2">
                    <Link
                      to={`/analysis/${encodeURIComponent(row.symbol)}`}
                      className="font-medium hover:text-bergt-green"
                    >
                      ${row.symbol}
                    </Link>
                    <span className="text-slate-400">{fmtPrice(row.price)}</span>
                    <span
                      className={
                        (row.changesPercentage ?? 0) > 0
                          ? "text-bergt-green"
                          : (row.changesPercentage ?? 0) < 0
                          ? "text-red-300"
                          : "text-slate-400"
                      }
                    >
                      {fmtPct(row.changesPercentage)}
                    </span>
                  </li>
                ))}
                {(movers[bucket] ?? []).length === 0 ? (
                  <li className="text-slate-500">{t("discover.movers.noData")}</li>
                ) : null}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="card space-y-3" data-testid="discover-clusters">
        <header>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            {t("discover.clusters.title")}
          </h2>
          <p className="text-xs text-slate-500">{t("discover.clusters.subtitle")}</p>
        </header>
        {clusters.length === 0 ? (
          <p className="text-xs text-slate-500">{t("discover.clusters.empty")}</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Symbol</th>
                <th className="text-right">Insiders</th>
                <th className="text-right">Buy / Sell</th>
                <th className="text-right">Net value</th>
                <th>Direction</th>
                <th>Last filing</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <tr key={cluster.symbol} className="border-t border-slate-800">
                  <td className="py-1">
                    <Link
                      to={`/analysis/${encodeURIComponent(cluster.symbol)}`}
                      className="font-medium hover:text-bergt-green"
                    >
                      ${cluster.symbol}
                    </Link>
                  </td>
                  <td className="text-right">{cluster.uniqueInsiders}</td>
                  <td className="text-right">
                    {cluster.buyCount} / {cluster.sellCount}
                  </td>
                  <td
                    className={`text-right ${
                      cluster.netValue > 0
                        ? "text-bergt-green"
                        : cluster.netValue < 0
                        ? "text-red-300"
                        : "text-slate-400"
                    }`}
                  >
                    {fmtUsd(cluster.netValue)}
                  </td>
                  <td>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                        directionClass[cluster.direction]
                      }`}
                    >
                      {directionLabel[cluster.direction]}
                    </span>
                  </td>
                  <td className="text-slate-400">{cluster.lastTransactionDate ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
