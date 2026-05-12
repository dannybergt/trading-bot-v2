import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/client";

export type FxRatesPayload = {
  base: string;
  date: string | null;
  rates: Record<string, number>;
  supported: string[];
  degraded?: boolean;
};

/**
 * ECB reference rates relative to `base` (default USD). Cached for 30
 * minutes — the upstream refresh cadence is once per business day, so
 * polling more often is wasted budget.
 */
export function useFxRates(base = "USD") {
  return useQuery({
    queryKey: ["fx-rates", base],
    queryFn: () =>
      apiFetch<FxRatesPayload>(`/api/fx/rates?base=${encodeURIComponent(base)}`, {
        skipAuth: true,
      }),
    staleTime: 30 * 60_000,
    refetchInterval: 60 * 60_000,
  });
}

/**
 * Convert `amount` from `fromCurrency` to `toCurrency` using the rates
 * dict served by `/api/fx/rates`. Returns the original amount unchanged
 * if either currency is unknown — the caller's UI then renders as if
 * conversion was a no-op.
 */
export function convertMoney(
  amount: number | null | undefined,
  fromCurrency: string | null | undefined,
  toCurrency: string | null | undefined,
  rates: Record<string, number> | undefined,
): number | null {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return null;
  const from = (fromCurrency || "").toUpperCase();
  const to = (toCurrency || "").toUpperCase();
  if (!from || !to || from === to) return amount;
  if (!rates) return amount;
  const fromRate = rates[from];
  const toRate = rates[to];
  if (typeof fromRate !== "number" || typeof toRate !== "number" || fromRate === 0) {
    return amount;
  }
  // rates are quoted against the base of the request: amount in `from`
  // converts to base via `/fromRate`, then base to `to` via `*toRate`.
  return (amount / fromRate) * toRate;
}
