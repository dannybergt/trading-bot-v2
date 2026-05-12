import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

type PortfolioSettings = {
  display_currency?: string;
};

export const SUPPORTED_DISPLAY_CURRENCIES = [
  "USD",
  "EUR",
  "GBP",
  "CHF",
  "JPY",
  "CAD",
  "AUD",
  "CNY",
] as const;

const LS_KEY = "displayCurrency";

function readLocalStorage(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(LS_KEY);
    return value && (SUPPORTED_DISPLAY_CURRENCIES as readonly string[]).includes(value)
      ? value
      : null;
  } catch {
    return null;
  }
}

function writeLocalStorage(value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, value);
  } catch {
    /* private browsing or quota; the auth-backed copy is still authoritative */
  }
}

/**
 * Current display currency for the signed-in user. Reads from
 * `/api/auth/me/portfolio-settings` (authoritative) and mirrors to
 * `localStorage` so the first paint after a reload doesn't flicker.
 *
 * Falls back to USD when the user isn't signed in or the request fails.
 */
export function useDisplayCurrency(): string {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["portfolio-settings"],
    queryFn: () => apiFetch<PortfolioSettings>("/api/auth/me/portfolio-settings"),
    enabled: !!user,
    staleTime: 5 * 60_000,
  });
  const serverValue = query.data?.display_currency;
  if (serverValue && (SUPPORTED_DISPLAY_CURRENCIES as readonly string[]).includes(serverValue)) {
    if (typeof window !== "undefined") writeLocalStorage(serverValue);
    return serverValue;
  }
  return readLocalStorage() ?? "USD";
}
