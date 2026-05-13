import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
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

  const deleteWatchlist = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/watchlists/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!newName.trim()) return;
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
          <WatchlistCard
            key={wl.id}
            watchlist={wl}
            onDelete={() => {
              if (
                window.confirm(
                  `Delete watchlist "${wl.name}" and all its symbols?`,
                )
              ) {
                deleteWatchlist.mutate(wl.id);
              }
            }}
          />
        ))}
      </div>
    </div>
  );
}

function WatchlistCard({
  watchlist,
  onDelete,
}: {
  watchlist: Watchlist;
  onDelete: () => void;
}) {
  const queryClient = useQueryClient();
  const [symbolInput, setSymbolInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [tagsInput, setTagsInput] = useState("");

  const addItem = useMutation({
    mutationFn: () =>
      apiFetch(`/api/watchlists/${encodeURIComponent(watchlist.id)}/items`, {
        method: "POST",
        body: {
          symbol: symbolInput.trim().toUpperCase(),
          name: nameInput.trim(),
          tags: tagsInput
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: () => {
      setSymbolInput("");
      setNameInput("");
      setTagsInput("");
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const removeItem = useMutation({
    mutationFn: (symbol: string) =>
      apiFetch(
        `/api/watchlists/${encodeURIComponent(watchlist.id)}/items/${encodeURI(
          symbol,
        )}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  function handleAdd(event: FormEvent) {
    event.preventDefault();
    if (!symbolInput.trim()) return;
    addItem.mutate();
  }

  return (
    <article className="card">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">
          {watchlist.name}{" "}
          {watchlist.is_default ? (
            <span className="ml-1 rounded-full border border-bergt-green/40 px-2 py-0.5 text-xs text-bergt-green">
              default
            </span>
          ) : null}
        </h2>
        {!watchlist.is_default ? (
          <button
            type="button"
            className="btn text-xs"
            onClick={onDelete}
            title="Delete watchlist"
          >
            Delete
          </button>
        ) : null}
      </header>
      <p className="mt-1 text-xs text-slate-400">
        {watchlist.items.length} symbol
        {watchlist.items.length === 1 ? "" : "s"} · id: {watchlist.id}
      </p>

      <form onSubmit={handleAdd} className="mt-3 grid gap-2 sm:grid-cols-3">
        <input
          className="input sm:col-span-1"
          placeholder="Symbol (e.g. AAPL or BTC/USD)"
          value={symbolInput}
          onChange={(event) => setSymbolInput(event.target.value)}
          required
        />
        <input
          className="input sm:col-span-1"
          placeholder="Name (optional)"
          value={nameInput}
          onChange={(event) => setNameInput(event.target.value)}
        />
        <input
          className="input sm:col-span-1"
          placeholder="tags, comma separated"
          value={tagsInput}
          onChange={(event) => setTagsInput(event.target.value)}
        />
        <div className="sm:col-span-3 flex items-center gap-3">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!symbolInput.trim() || addItem.isPending}
          >
            {addItem.isPending ? "Adding…" : "Add symbol"}
          </button>
          {addItem.error ? (
            <span className="text-xs text-red-300">
              {(addItem.error as ApiError).message}
            </span>
          ) : null}
        </div>
      </form>

      {watchlist.items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No symbols yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {watchlist.items.map((item) => (
            <li
              key={item.symbol}
              className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm transition hover:border-bergt-green/50"
            >
              <Link
                to={`/analysis/${encodeURIComponent(item.symbol)}`}
                className="flex-1 min-w-0 -mx-3 -my-2 px-3 py-2 hover:text-bergt-green focus:outline-none focus:text-bergt-green"
                title={`Analyse fuer ${item.symbol} oeffnen`}
              >
                <p className="font-medium">{item.symbol}</p>
                {item.name ? (
                  <p className="text-xs text-slate-500">{item.name}</p>
                ) : null}
              </Link>
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
                <button
                  type="button"
                  className="btn text-xs"
                  onClick={() => {
                    if (window.confirm(`Remove ${item.symbol}?`)) {
                      removeItem.mutate(item.symbol);
                    }
                  }}
                  disabled={removeItem.isPending}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
