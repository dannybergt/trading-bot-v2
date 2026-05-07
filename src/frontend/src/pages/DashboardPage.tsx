import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/client";

type Watchlist = {
  id: string;
  name: string;
  is_default?: boolean;
  items: Array<{ symbol: string; name?: string; tags?: string[] }>;
};

type AlertsSummary = {
  rules: number;
  events: Array<unknown>;
  summary: {
    rules: number;
    enabledRules: number;
    openEvents: number;
    createdEvents: number;
  };
};

export function DashboardPage() {
  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<Watchlist[]>("/api/watchlists"),
  });
  const alertsQuery = useQuery({
    queryKey: ["alerts-summary"],
    queryFn: () => apiFetch<AlertsSummary>("/api/alerts"),
  });

  const watchlists = watchlistsQuery.data ?? [];
  const totalSymbols = watchlists.reduce(
    (acc, list) => acc + (list.items?.length ?? 0),
    0,
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-slate-400">
          Overview of watchlists, alert rules, and open events.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Watchlists"
          value={watchlistsQuery.isLoading ? "…" : String(watchlists.length)}
        />
        <Stat
          label="Tracked symbols"
          value={watchlistsQuery.isLoading ? "…" : String(totalSymbols)}
        />
        <Stat
          label="Alert rules"
          value={
            alertsQuery.isLoading
              ? "…"
              : String(alertsQuery.data?.summary.rules ?? 0)
          }
          hint={
            alertsQuery.data
              ? `${alertsQuery.data.summary.enabledRules} enabled`
              : undefined
          }
        />
        <Stat
          label="Open events"
          value={
            alertsQuery.isLoading
              ? "…"
              : String(alertsQuery.data?.summary.openEvents ?? 0)
          }
        />
      </section>

      <p className="text-xs text-slate-500">
        This dashboard is the new Vite/React source. Existing legacy panels
        (provider coverage, news ticker, scanner) are migrating from
        ui-patches.js into native components — see project-plan.md for the
        ordering.
      </p>
    </div>
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
