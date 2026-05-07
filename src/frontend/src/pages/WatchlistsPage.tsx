import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";

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

export function WatchlistsPage() {
  const queryClient = useQueryClient();
  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<Watchlist[]>("/api/watchlists"),
  });

  const [newName, setNewName] = useState("");

  const createWatchlist = useMutation({
    mutationFn: (name: string) =>
      apiFetch<Watchlist>("/api/watchlists", {
        method: "POST",
        body: { name },
      }),
    onSuccess: () => {
      setNewName("");
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!newName.trim()) {
      return;
    }
    createWatchlist.mutate(newName.trim());
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Watchlists</h1>
        <p className="text-sm text-slate-400">
          Lists are stored per user. Default lists are seeded automatically.
        </p>
      </header>

      <form onSubmit={handleCreate} className="card flex flex-wrap gap-3">
        <input
          className="input flex-1 min-w-[200px]"
          placeholder="Add a new watchlist…"
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!newName.trim() || createWatchlist.isPending}
        >
          {createWatchlist.isPending ? "Creating…" : "Create"}
        </button>
        {createWatchlist.error ? (
          <p className="basis-full text-sm text-red-300">
            {(createWatchlist.error as ApiError).message ??
              "Could not create watchlist."}
          </p>
        ) : null}
      </form>

      {watchlistsQuery.isLoading ? (
        <p className="text-sm text-slate-400">Loading watchlists…</p>
      ) : null}
      {watchlistsQuery.error ? (
        <p className="text-sm text-red-300">
          Failed to load watchlists:{" "}
          {(watchlistsQuery.error as ApiError).message}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {(watchlistsQuery.data ?? []).map((wl) => (
          <article key={wl.id} className="card">
            <header className="flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-semibold">
                {wl.name}{" "}
                {wl.is_default ? (
                  <span className="ml-1 rounded-full border border-bergt-green/40 px-2 py-0.5 text-xs text-bergt-green">
                    default
                  </span>
                ) : null}
              </h2>
              <span className="text-xs text-slate-500">id: {wl.id}</span>
            </header>
            <p className="mt-1 text-xs text-slate-400">
              {wl.items.length} symbol{wl.items.length === 1 ? "" : "s"}
            </p>
            {wl.items.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No symbols yet.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {wl.items.map((item) => (
                  <li
                    key={item.symbol}
                    className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm"
                  >
                    <div>
                      <p className="font-medium">{item.symbol}</p>
                      {item.name ? (
                        <p className="text-xs text-slate-500">{item.name}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      {item.assetLabel ? (
                        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
                          {item.assetLabel}
                        </span>
                      ) : null}
                      {(item.tags ?? []).map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
