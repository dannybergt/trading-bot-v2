import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";
import { useOnboarding } from "../auth/useOnboarding";

type WatchlistItem = {
  symbol: string;
  name?: string;
  tags?: string[];
  assetClass?: string;
  assetLabel?: string;
};

type Watchlist = {
  id: string;
  name: string;
  is_default?: boolean;
  items: WatchlistItem[];
};

type TrackedAsset = {
  symbol: string;
  name?: string;
  assetClass?: string;
  assetLabel?: string;
  tags?: string[];
  provider?: { status?: string; source?: string } | null;
};

type AlertsSummary = {
  rules: number;
  events: Array<unknown>;
  summary: {
    rules: number;
    enabledRules: number;
    openEvents: number;
  };
};

type WatchlistAlertSummary = {
  rules?: number;
  trackedSymbols?: number;
  providerLive?: number;
  providerPartial?: number;
  providerUnavailable?: number;
  providerResearch?: number;
  providerMovers?: number;
  high?: number;
  medium?: number;
  low?: number;
};

type WatchlistAlertsPayload = {
  watchlist: { id: string; name: string };
  trackedAssets: TrackedAsset[];
  summary: WatchlistAlertSummary;
};

type WatchlistNewsItem = {
  symbol: string;
  name?: string;
  title?: string;
  summary?: string;
  label?: string;
  score?: number;
  timestamp?: string;
  url?: string;
  source?: string;
};

type WatchlistNewsPayload = {
  items: WatchlistNewsItem[];
};

export function DashboardPage() {
  const { t } = useTranslation();
  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<Watchlist[]>("/api/watchlists"),
  });
  const alertsSummaryQuery = useQuery({
    queryKey: ["alerts-summary"],
    queryFn: () => apiFetch<AlertsSummary>("/api/alerts"),
  });

  const watchlists = watchlistsQuery.data ?? [];
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    if (!activeId && watchlists.length > 0) {
      const def = watchlists.find((wl) => wl.is_default) ?? watchlists[0];
      setActiveId(def.id);
    }
  }, [activeId, watchlists]);

  const totalSymbols = useMemo(
    () => watchlists.reduce((acc, wl) => acc + (wl.items?.length ?? 0), 0),
    [watchlists],
  );

  const watchlistAlertsQuery = useQuery({
    queryKey: ["watchlist-alerts", activeId],
    queryFn: () =>
      apiFetch<WatchlistAlertsPayload>(
        `/api/watchlists/${encodeURIComponent(activeId)}/alerts`,
      ),
    enabled: !!activeId,
    refetchInterval: 90_000,
  });

  const watchlistNewsQuery = useQuery({
    queryKey: ["watchlist-news", activeId],
    queryFn: () =>
      apiFetch<WatchlistNewsPayload>(
        `/api/watchlists/${encodeURIComponent(activeId)}/news`,
      ),
    enabled: !!activeId,
    refetchInterval: 120_000,
  });

  return (
    <div className="space-y-6">
      <OnboardingCard />
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("dashboard.title")}</h1>
          <p className="text-sm text-slate-400">{t("dashboard.subtitle")}</p>
        </div>
        {watchlists.length > 0 ? (
          <label className="text-sm">
            <span className="mr-2 text-slate-400">{t("dashboard.activeWatchlist")}</span>
            <select
              className="input inline-block w-auto"
              value={activeId}
              onChange={(event) => setActiveId(event.target.value)}
            >
              {watchlists.map((wl) => (
                <option key={wl.id} value={wl.id}>
                  {wl.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label={t("dashboard.stats.watchlists")}
          value={watchlistsQuery.isLoading ? "…" : String(watchlists.length)}
        />
        <Stat
          label={t("dashboard.stats.trackedSymbols")}
          value={watchlistsQuery.isLoading ? "…" : String(totalSymbols)}
        />
        <Stat
          label={t("dashboard.stats.alertRules")}
          value={
            alertsSummaryQuery.isLoading
              ? "…"
              : String(alertsSummaryQuery.data?.summary.rules ?? 0)
          }
          hint={
            alertsSummaryQuery.data
              ? t("dashboard.stats.enabled", {
                  count: alertsSummaryQuery.data.summary.enabledRules,
                })
              : undefined
          }
        />
        <Stat
          label={t("dashboard.stats.openEvents")}
          value={
            alertsSummaryQuery.isLoading
              ? "…"
              : String(alertsSummaryQuery.data?.summary.openEvents ?? 0)
          }
        />
      </section>

      <TrackedAssets data={watchlistAlertsQuery.data} />
      <ProviderCoverage data={watchlistAlertsQuery.data} />
      <MacroCalendarCard />
      <NewsTicker data={watchlistNewsQuery.data} />

      {watchlistAlertsQuery.error ? (
        <p className="text-xs text-red-300">
          Failed to load watchlist alerts:{" "}
          {(watchlistAlertsQuery.error as ApiError).message}
        </p>
      ) : null}
    </div>
  );
}

function OnboardingCard() {
  const { t } = useTranslation();
  const { steps, completedCount, total, isComplete, requiredOpenCount } = useOnboarding();
  if (isComplete) return null;
  const pct = total === 0 ? 0 : (completedCount / total) * 100;
  const openLabels = steps.filter((s) => !s.completed).map((s) => s.label);
  const requiredText =
    requiredOpenCount === 0
      ? t("dashboard.onboarding.allRequiredDone")
      : requiredOpenCount === 1
      ? t("dashboard.onboarding.requiredOpenOne")
      : t("dashboard.onboarding.requiredOpen", { count: requiredOpenCount });
  return (
    <section className="card border-bergt-green/40">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("dashboard.onboarding.title")}</h2>
          <p className="text-sm text-slate-400">
            {t("dashboard.onboarding.configured", { completed: completedCount, total })}
            {" · "}
            {requiredText}
          </p>
        </div>
        <Link to="/onboarding" className="btn btn-primary">
          {t("dashboard.onboarding.continue")}
        </Link>
      </header>
      <div className="mt-3 h-2 w-full rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-bergt-green/70 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      {openLabels.length > 0 ? (
        <p className="mt-2 text-xs text-slate-400">
          {t("dashboard.onboarding.stillOpen", { labels: openLabels.join(" · ") })}
        </p>
      ) : null}
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="card">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

function TrackedAssets({ data }: { data: WatchlistAlertsPayload | undefined }) {
  if (!data) return null;
  const tracked = data.trackedAssets ?? [];
  const classCounts = new Map<string, number>();
  const tagCounts = new Map<string, number>();
  for (const item of tracked) {
    const key = item.assetLabel ?? item.assetClass ?? "Other";
    classCounts.set(key, (classCounts.get(key) ?? 0) + 1);
    for (const tag of item.tags ?? []) {
      tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
    }
  }
  const sortedTags = Array.from(tagCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Tracked assets</h2>
      <p className="text-xs text-slate-500">
        Watchlist “{data.watchlist.name}” · {tracked.length} symbol
        {tracked.length === 1 ? "" : "s"}
      </p>
      {tracked.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No symbols.</p>
      ) : (
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Asset mix
            </p>
            <ul className="mt-1 space-y-1 text-sm">
              {Array.from(classCounts.entries()).map(([label, count]) => (
                <li key={label} className="flex justify-between">
                  <span>{label}</span>
                  <span className="tabular-nums text-slate-300">{count}</span>
                </li>
              ))}
            </ul>
          </div>
          {sortedTags.length > 0 ? (
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">
                Top tags
              </p>
              <ul className="mt-1 flex flex-wrap gap-1.5 text-xs">
                {sortedTags.map(([tag, count]) => (
                  <li
                    key={tag}
                    className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300"
                  >
                    #{tag} <span className="text-slate-500">({count})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
      {tracked.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm">
          {tracked.slice(0, 8).map((item) => (
            <li
              key={item.symbol}
              className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-3 py-1.5"
            >
              <Link
                to={`/analysis/${encodeURIComponent(item.symbol)}`}
                className="font-medium hover:text-bergt-green"
              >
                {item.symbol}
              </Link>
              <span className="text-xs text-slate-400">
                {item.assetLabel ?? item.assetClass ?? ""}
                {item.provider?.status
                  ? ` · provider: ${item.provider.status}`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ProviderCoverage({
  data,
}: {
  data: WatchlistAlertsPayload | undefined;
}) {
  if (!data) return null;
  const summary = data.summary ?? {};
  const live = summary.providerLive ?? 0;
  const partial = summary.providerPartial ?? 0;
  const unavailable = summary.providerUnavailable ?? 0;
  const research = summary.providerResearch ?? 0;
  const movers = summary.providerMovers ?? 0;
  if (live + partial + unavailable + research + movers === 0) {
    return null;
  }
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Provider coverage</h2>
      <div className="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
        <Mini label="Live" value={live} accent="text-bergt-green" />
        <Mini label="Partial" value={partial} accent="text-amber-300" />
        <Mini label="Unavailable" value={unavailable} accent="text-slate-400" />
        <Mini label="Research" value={research} />
        <Mini label="Movers" value={movers} />
      </div>
    </section>
  );
}

function Mini({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-2">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-0.5 text-xl font-semibold tabular-nums ${accent ?? "text-slate-200"}`}>
        {value}
      </p>
    </div>
  );
}

type MacroCalendarPayload = {
  configured: boolean;
  treasury: {
    two?: { value: number | null; changePct: number | null; asOf?: string | null };
    ten?: { value: number | null; changePct: number | null; asOf?: string | null };
    spread?: { value: number | null; changePct: number | null; asOf?: string | null };
    spreadInverted?: boolean;
  };
  upcomingReleases: Array<{
    releaseId: number;
    name: string;
    category: string;
    date: string;
    daysUntil: number;
  }>;
};

function MacroCalendarCard() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["macro-calendar"],
    queryFn: () => apiFetch<MacroCalendarPayload>("/api/macro/calendar"),
    refetchInterval: 30 * 60_000,
  });
  const data = query.data;
  if (!data) return null;
  if (!data.configured) {
    return (
      <section className="card" data-testid="dashboard-macro-calendar">
        <h2 className="text-lg font-semibold">{t("macroCalendar.title")}</h2>
        <p className="mt-1 text-xs text-slate-500">{t("macroCalendar.unconfigured")}</p>
      </section>
    );
  }
  const ten = data.treasury?.ten;
  const two = data.treasury?.two;
  const spread = data.treasury?.spread;
  const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(2)}%`);
  return (
    <section className="card" data-testid="dashboard-macro-calendar">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{t("macroCalendar.title")}</h2>
        {data.treasury?.spreadInverted ? (
          <span className="rounded-full border border-amber-500/40 bg-amber-900/30 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-200">
            {t("macroCalendar.inverted")}
          </span>
        ) : null}
      </header>
      <div className="mt-2 grid gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">{t("macroCalendar.tenYear")}</p>
          <p className="text-sm font-medium">{fmtPct(ten?.value)}</p>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">{t("macroCalendar.twoYear")}</p>
          <p className="text-sm font-medium">{fmtPct(two?.value)}</p>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-2">
          <p className="text-slate-500">{t("macroCalendar.spread")}</p>
          <p className={`text-sm font-medium ${data.treasury?.spreadInverted ? "text-amber-300" : ""}`}>
            {fmtPct(spread?.value)}
          </p>
        </div>
      </div>
      {data.upcomingReleases.length === 0 ? null : (
        <ul className="mt-3 space-y-1 text-xs">
          {data.upcomingReleases.slice(0, 5).map((r) => (
            <li key={`${r.releaseId}-${r.date}`} className="flex justify-between gap-2">
              <span className="font-medium">{r.name}</span>
              <span className="text-slate-400">
                {r.date} · {t("macroCalendar.daysUntil", { days: r.daysUntil })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NewsTicker({ data }: { data: WatchlistNewsPayload | undefined }) {
  const items = data?.items ?? [];
  if (items.length === 0) return null;
  return (
    <section className="card">
      <h2 className="text-lg font-semibold">News ticker</h2>
      <ul className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-2">
        {items.map((item, idx) => (
          <li key={`${item.symbol}-${idx}`} className="text-sm">
            <p>
              <Link
                to={`/analysis/${encodeURIComponent(item.symbol)}`}
                className="mr-2 font-medium hover:text-bergt-green"
              >
                {item.symbol}
              </Link>
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
                <span>{item.title}</span>
              )}
            </p>
            <p className="text-xs text-slate-500">
              {[item.source, item.label, item.timestamp ? formatDate(item.timestamp) : ""]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}
