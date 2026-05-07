import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";

type Watchlist = { id: string; name: string };

type ScannerRow = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  assetClass?: string;
  assetLabel?: string;
  market?: string;
  exchange?: string;
  type?: string;
  isCrypto?: boolean;
  history?: Array<{ close: number }>;
  provider?: {
    status?: string;
    source?: string;
  } | null;
};

export function ScannerPage() {
  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<Watchlist[]>("/api/watchlists"),
  });
  const watchlists = watchlistsQuery.data ?? [];
  const [watchlistId, setWatchlistId] = useState<string>("");

  const effectiveWatchlistId = watchlistId || watchlists[0]?.id || "";

  const scannerQuery = useQuery({
    queryKey: ["scanner", effectiveWatchlistId],
    queryFn: () =>
      apiFetch<ScannerRow[]>(
        effectiveWatchlistId
          ? `/api/scanner?watchlist_id=${encodeURIComponent(effectiveWatchlistId)}`
          : "/api/scanner",
      ),
    enabled: watchlistsQuery.isSuccess,
    refetchInterval: 60_000,
  });

  const rows = scannerQuery.data ?? [];
  const sorted = useMemo(
    () => [...rows].sort((a, b) => (b.changePercent ?? 0) - (a.changePercent ?? 0)),
    [rows],
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Scanner</h1>
          <p className="text-sm text-slate-400">
            Latest snapshot for the selected watchlist. Refreshes every 60 s.
          </p>
        </div>
        <label className="text-sm">
          <span className="mr-2 text-slate-400">Watchlist</span>
          <select
            className="input inline-block w-auto"
            value={watchlistId}
            onChange={(event) => setWatchlistId(event.target.value)}
          >
            <option value="">(default)</option>
            {watchlists.map((wl) => (
              <option key={wl.id} value={wl.id}>
                {wl.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      {scannerQuery.error ? (
        <p className="text-sm text-red-300">
          Failed to load scanner: {(scannerQuery.error as ApiError).message}
        </p>
      ) : null}
      {scannerQuery.isLoading ? (
        <p className="text-sm text-slate-400">Loading scanner snapshot…</p>
      ) : null}

      {sorted.length === 0 && !scannerQuery.isLoading ? (
        <p className="text-sm text-slate-500">
          No symbols in this watchlist. Add some on the Watchlists page.
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead className="bg-slate-900/60 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-left">Asset</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Change</th>
              <th className="px-3 py-2 text-right">% change</th>
              <th className="px-3 py-2 text-left">Provider</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {sorted.map((row) => (
              <tr key={row.symbol} className="hover:bg-slate-900/40">
                <td className="px-3 py-2 font-medium">
                  <Link to={`/analysis/${encodeURIComponent(row.symbol)}`} className="hover:text-bergt-green">
                    {row.symbol}
                  </Link>
                  {row.name ? (
                    <p className="text-xs text-slate-500">{row.name}</p>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {row.assetLabel ?? row.assetClass ?? "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {row.price ? row.price.toFixed(2) : "—"}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${changeClass(row.change)}`}
                >
                  {row.change ? row.change.toFixed(2) : "—"}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${changeClass(row.changePercent)}`}
                >
                  {row.changePercent ? `${row.changePercent.toFixed(2)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-slate-300">
                  {row.provider ? (
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs ${providerClass(row.provider.status)}`}
                    >
                      {row.provider.status ?? "n/a"}
                      {row.provider.source ? ` · ${row.provider.source}` : ""}
                    </span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function changeClass(value: number): string {
  if (!value) return "text-slate-400";
  return value > 0 ? "text-bergt-green" : "text-red-400";
}

function providerClass(status?: string): string {
  switch (status) {
    case "live":
      return "border-bergt-green/40 bg-bergt-green/10 text-bergt-green";
    case "partial":
      return "border-amber-700/50 bg-amber-900/30 text-amber-200";
    case "unavailable":
      return "border-slate-700 bg-slate-800 text-slate-300";
    default:
      return "border-slate-700 bg-slate-900 text-slate-400";
  }
}
