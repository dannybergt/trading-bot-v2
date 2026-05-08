import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";

type PaperOrder = {
  id: number;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  limitPrice: number | null;
  status: "pending" | "filled" | "cancelled";
  source: "manual" | "auto-recommendation";
  rejectionReason: string | null;
  placedAt: string | null;
  filledAt: string | null;
};

type PaperTransaction = {
  id: number;
  orderId: number;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  feeAbsolute: number;
  feePercentAmount: number;
  feeTotal: number;
  taxAmount: number;
  realizedPnl: number;
  realizedPnlPct: number | null;
  executedAt: string | null;
};

type PaperPosition = {
  symbol: string;
  qty: number;
  avgEntryPrice: number;
  lastPrice: number | null;
  unrealizedPnl: number | null;
  unrealizedPnlPct: number | null;
  realizedPnl: number;
  feeTotal: number;
  taxTotal: number;
};

type PaperSummary = {
  realizedPnl: number;
  unrealizedPnl: number;
  feeTotal: number;
  taxTotal: number;
  openExposure: number;
  openPositions: number;
  transactionCount: number;
};

type GateBreakdown = {
  grossTargetPct?: number;
  feeRoundTripPct?: number;
  taxDragPct?: number;
  netTargetPct?: number;
  minTargetYieldPct?: number | null;
  meetsMinimum?: boolean;
};

type Tab = "openOrders" | "journal" | "positions" | "summary";

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function PaperTradingPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("openOrders");

  const ordersQuery = useQuery({
    queryKey: ["paper-orders"],
    queryFn: () => apiFetch<{ orders: PaperOrder[] }>("/api/paper-trading/orders"),
    refetchInterval: 30_000,
  });
  const transactionsQuery = useQuery({
    queryKey: ["paper-transactions"],
    queryFn: () =>
      apiFetch<{ transactions: PaperTransaction[] }>("/api/paper-trading/transactions"),
    refetchInterval: 30_000,
  });
  const positionsQuery = useQuery({
    queryKey: ["paper-positions"],
    queryFn: () => apiFetch<{ positions: PaperPosition[] }>("/api/paper-trading/positions"),
    refetchInterval: 30_000,
  });
  const summaryQuery = useQuery({
    queryKey: ["paper-summary"],
    queryFn: () => apiFetch<PaperSummary>("/api/paper-trading/summary"),
    refetchInterval: 30_000,
  });

  const orders = ordersQuery.data?.orders ?? [];
  const transactions = transactionsQuery.data?.transactions ?? [];
  const positions = positionsQuery.data?.positions ?? [];
  const summary = summaryQuery.data;
  const openOrders = useMemo(
    () => orders.filter((o) => o.status === "pending"),
    [orders],
  );

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [source, setSource] = useState<"manual" | "auto-recommendation">("manual");
  const [formError, setFormError] = useState<string | null>(null);

  const placeMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiFetch<PaperOrder>("/api/paper-trading/orders", {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      setSymbol("");
      setQty("");
      setLimitPrice("");
      setTargetPrice("");
      setFormError(null);
      queryClient.invalidateQueries({ queryKey: ["paper-orders"] });
      queryClient.invalidateQueries({ queryKey: ["paper-transactions"] });
      queryClient.invalidateQueries({ queryKey: ["paper-positions"] });
      queryClient.invalidateQueries({ queryKey: ["paper-summary"] });
    },
    onError: (error: unknown) => {
      if (error instanceof ApiError && error.status === 400 && error.detail) {
        const detail = error.detail as { reason?: string; breakdown?: GateBreakdown } | string;
        if (typeof detail === "object" && detail.reason === "net_target_below_minimum") {
          const bd = detail.breakdown ?? {};
          setFormError(
            t("paperTrading.form.rejectionDetail", {
              net: bd.netTargetPct?.toFixed(2) ?? "—",
              minimum: bd.minTargetYieldPct?.toFixed(2) ?? "—",
              gross: bd.grossTargetPct?.toFixed(2) ?? "—",
              fees: bd.feeRoundTripPct?.toFixed(2) ?? "—",
              tax: bd.taxDragPct?.toFixed(2) ?? "—",
            }),
          );
          return;
        }
        setFormError(typeof detail === "string" ? detail : t("paperTrading.form.errorGeneric"));
        return;
      }
      setFormError(t("paperTrading.form.errorGeneric"));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (orderId: number) =>
      apiFetch(`/api/paper-trading/orders/${orderId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["paper-orders"] });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    const payload: Record<string, unknown> = {
      symbol: symbol.trim().toUpperCase(),
      side,
      qty: Number(qty),
      source,
    };
    if (limitPrice.trim()) payload.limitPrice = Number(limitPrice);
    if (targetPrice.trim()) payload.targetPrice = Number(targetPrice);
    placeMutation.mutate(payload);
  };

  const journalTotals = useMemo(() => {
    const totalRealized = transactions.reduce((acc, tx) => acc + tx.realizedPnl, 0);
    const totalFees = transactions.reduce((acc, tx) => acc + tx.feeTotal, 0);
    const totalTax = transactions.reduce((acc, tx) => acc + tx.taxAmount, 0);
    return { totalRealized, totalFees, totalTax };
  }, [transactions]);

  return (
    <div className="space-y-6" data-testid="paper-trading-page">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{t("paperTrading.title")}</h1>
        <p className="text-sm text-slate-400">{t("paperTrading.subtitle")}</p>
      </header>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          {t("paperTrading.form.title")}
        </h2>
        <form className="grid gap-3 md:grid-cols-6" onSubmit={submit}>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.symbol")}</span>
            <input
              className="input"
              required
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="AAPL"
            />
          </label>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.side")}</span>
            <select
              className="input"
              value={side}
              onChange={(e) => setSide(e.target.value as "buy" | "sell")}
            >
              <option value="buy">{t("paperTrading.form.buy")}</option>
              <option value="sell">{t("paperTrading.form.sell")}</option>
            </select>
          </label>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.qty")}</span>
            <input
              className="input"
              required
              type="number"
              min="0"
              step="any"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
          </label>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.limitPrice")}</span>
            <input
              className="input"
              type="number"
              min="0"
              step="any"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
            />
          </label>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.targetPrice")}</span>
            <input
              className="input"
              type="number"
              min="0"
              step="any"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
            />
          </label>
          <label className="md:col-span-1 space-y-1 text-xs">
            <span className="text-slate-400">{t("paperTrading.form.source")}</span>
            <select
              className="input"
              value={source}
              onChange={(e) => setSource(e.target.value as "manual" | "auto-recommendation")}
            >
              <option value="manual">{t("paperTrading.form.sourceManual")}</option>
              <option value="auto-recommendation">{t("paperTrading.form.sourceAuto")}</option>
            </select>
          </label>
          <div className="md:col-span-6 flex items-center gap-3">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={placeMutation.isPending}
            >
              {placeMutation.isPending
                ? t("paperTrading.form.submitting")
                : t("paperTrading.form.submit")}
            </button>
            {formError ? (
              <span className="text-xs text-amber-300" data-testid="paper-form-error">
                {formError}
              </span>
            ) : null}
          </div>
        </form>
      </section>

      <nav className="flex flex-wrap gap-2" role="tablist" aria-label={t("paperTrading.title")}>
        {(["openOrders", "journal", "positions", "summary"] as Tab[]).map((tabKey) => (
          <button
            type="button"
            key={tabKey}
            role="tab"
            aria-selected={tab === tabKey}
            data-testid={`paper-tab-${tabKey}`}
            onClick={() => setTab(tabKey)}
            className={`btn ${tab === tabKey ? "btn-primary" : ""}`}
          >
            {t(`paperTrading.tabs.${tabKey}`)}
          </button>
        ))}
      </nav>

      {tab === "openOrders" ? (
        <section className="card" data-testid="paper-tab-content-openOrders">
          {openOrders.length === 0 ? (
            <p className="text-sm text-slate-400">{t("paperTrading.openOrders.empty")}</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2">{t("paperTrading.openOrders.headers.placedAt")}</th>
                  <th>{t("paperTrading.openOrders.headers.symbol")}</th>
                  <th>{t("paperTrading.openOrders.headers.side")}</th>
                  <th className="text-right">{t("paperTrading.openOrders.headers.qty")}</th>
                  <th className="text-right">{t("paperTrading.openOrders.headers.limit")}</th>
                  <th>{t("paperTrading.openOrders.headers.status")}</th>
                  <th>{t("paperTrading.openOrders.headers.source")}</th>
                  <th className="text-right">{t("paperTrading.openOrders.headers.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {openOrders.map((order) => (
                  <tr key={order.id} className="border-t border-slate-800">
                    <td className="py-2 text-slate-400">{formatDateTime(order.placedAt)}</td>
                    <td className="font-medium">{order.symbol}</td>
                    <td>{order.side === "buy" ? t("paperTrading.form.buy") : t("paperTrading.form.sell")}</td>
                    <td className="text-right">{order.qty}</td>
                    <td className="text-right">
                      {order.limitPrice !== null ? order.limitPrice.toFixed(2) : "—"}
                    </td>
                    <td>{order.status}</td>
                    <td className="text-slate-400">{order.source}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn"
                        onClick={() => cancelMutation.mutate(order.id)}
                        disabled={cancelMutation.isPending}
                      >
                        {t("paperTrading.openOrders.cancel")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}

      {tab === "journal" ? (
        <section className="card space-y-4" data-testid="paper-tab-content-journal">
          {transactions.length === 0 ? (
            <p className="text-sm text-slate-400">{t("paperTrading.journal.empty")}</p>
          ) : (
            <>
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="py-2">{t("paperTrading.journal.headers.executedAt")}</th>
                    <th>{t("paperTrading.journal.headers.symbol")}</th>
                    <th>{t("paperTrading.journal.headers.side")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.qty")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.price")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.fees")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.tax")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.pnlNominal")}</th>
                    <th className="text-right">{t("paperTrading.journal.headers.pnlPct")}</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id} className="border-t border-slate-800">
                      <td className="py-2 text-slate-400">{formatDateTime(tx.executedAt)}</td>
                      <td className="font-medium">{tx.symbol}</td>
                      <td>{tx.side === "buy" ? t("paperTrading.form.buy") : t("paperTrading.form.sell")}</td>
                      <td className="text-right">{tx.qty}</td>
                      <td className="text-right">{tx.price.toFixed(2)}</td>
                      <td className="text-right">{tx.feeTotal.toFixed(2)}</td>
                      <td className="text-right">{tx.taxAmount.toFixed(2)}</td>
                      <td className="text-right">{formatCurrency(tx.realizedPnl)}</td>
                      <td className="text-right">{formatPct(tx.realizedPnlPct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {t("paperTrading.journal.totalsTitle")}
                </h3>
                <dl className="mt-2 grid gap-2 sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-slate-500">{t("paperTrading.journal.totalRealized")}</dt>
                    <dd className="font-mono">{formatCurrency(journalTotals.totalRealized)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">{t("paperTrading.journal.totalFees")}</dt>
                    <dd className="font-mono">{journalTotals.totalFees.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">{t("paperTrading.journal.totalTax")}</dt>
                    <dd className="font-mono">{journalTotals.totalTax.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">{t("paperTrading.journal.totalCount")}</dt>
                    <dd className="font-mono">{transactions.length}</dd>
                  </div>
                </dl>
              </div>
            </>
          )}
        </section>
      ) : null}

      {tab === "positions" ? (
        <section className="card" data-testid="paper-tab-content-positions">
          {positions.length === 0 ? (
            <p className="text-sm text-slate-400">{t("paperTrading.positions.empty")}</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2">{t("paperTrading.positions.headers.symbol")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.qty")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.avgEntry")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.lastPrice")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.unrealized")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.unrealizedPct")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.realized")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.feeTotal")}</th>
                  <th className="text-right">{t("paperTrading.positions.headers.taxTotal")}</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.symbol} className="border-t border-slate-800">
                    <td className="py-2 font-medium">{pos.symbol}</td>
                    <td className="text-right">{pos.qty}</td>
                    <td className="text-right">{pos.avgEntryPrice.toFixed(2)}</td>
                    <td className="text-right">
                      {pos.lastPrice !== null ? pos.lastPrice.toFixed(2) : "—"}
                    </td>
                    <td className="text-right">{formatCurrency(pos.unrealizedPnl)}</td>
                    <td className="text-right">{formatPct(pos.unrealizedPnlPct)}</td>
                    <td className="text-right">{formatCurrency(pos.realizedPnl)}</td>
                    <td className="text-right">{pos.feeTotal.toFixed(2)}</td>
                    <td className="text-right">{pos.taxTotal.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}

      {tab === "summary" ? (
        <section className="card" data-testid="paper-tab-content-summary">
          {!summary ? (
            <p className="text-sm text-slate-400">{t("app.loading")}</p>
          ) : (
            <dl className="grid gap-3 sm:grid-cols-3">
              {(
                [
                  ["realizedPnl", summary.realizedPnl, formatCurrency],
                  ["unrealizedPnl", summary.unrealizedPnl, formatCurrency],
                  ["feeTotal", summary.feeTotal, (v: number) => v.toFixed(2)],
                  ["taxTotal", summary.taxTotal, (v: number) => v.toFixed(2)],
                  ["openExposure", summary.openExposure, (v: number) => v.toFixed(2)],
                  ["openPositions", summary.openPositions, (v: number) => `${v}`],
                  ["transactionCount", summary.transactionCount, (v: number) => `${v}`],
                ] as const
              ).map(([key, value, fmt]) => (
                <div key={key} className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
                  <dt className="text-xs uppercase tracking-wide text-slate-500">
                    {t(`paperTrading.summary.${key}`)}
                  </dt>
                  <dd className="mt-1 font-mono text-lg">{fmt(value as number)}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      ) : null}
    </div>
  );
}
