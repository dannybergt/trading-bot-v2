/**
 * The guided first run: one pass through the whole decision process.
 *
 * Distinct from `useOnboarding`, which tracks CONFIGURATION (MFA, Alpaca,
 * fees, taxes). This hook tracks whether the user has once walked the actual
 * workflow -- find a symbol, read the analysis, watch it, get alerted, trade it
 * on paper -- and derives each step from real data instead of a click counter.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useOnboarding } from "../auth/useOnboarding";
import {
  completeTour,
  EMPTY_TOUR,
  grewSinceBaseline,
  readTour,
  resetTour,
  startTour,
  type TourCounts,
  type TourRecord,
} from "./tourState";

export type TourStepId =
  | "basics"
  | "findSymbol"
  | "readAnalysis"
  | "watchlist"
  | "alert"
  | "paperTrade"
  | "autoExecution";

export type TourStep = {
  id: TourStepId;
  /** Where the user performs this step; null for steps done inside the wizard. */
  target: string | null;
  completed: boolean;
  /** How completion is established -- surfaced in the UI so progress is never a black box. */
  evidence: "config" | "visited" | "created" | "acknowledged";
};

export const TOUR_STEP_ORDER: TourStepId[] = [
  "basics",
  "findSymbol",
  "readAnalysis",
  "watchlist",
  "alert",
  "paperTrade",
  "autoExecution",
];

type WatchlistResponse = { id: string; items: unknown[] }[];
type AlertsResponse = { rules: unknown[] };
type PaperOrdersResponse = unknown[];

function countItems(watchlists: WatchlistResponse | undefined): number {
  if (!watchlists) return 0;
  return watchlists.reduce((sum, list) => sum + (list.items?.length ?? 0), 0);
}

export function useGuidedTour() {
  const { user } = useAuth();
  const onboarding = useOnboarding();
  const userId = user?.id;

  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<WatchlistResponse>("/api/watchlists"),
    enabled: !!user,
  });
  const alertsQuery = useQuery({
    queryKey: ["alerts"],
    queryFn: () => apiFetch<AlertsResponse>("/api/alerts"),
    enabled: !!user,
  });
  const ordersQuery = useQuery({
    queryKey: ["paper-orders"],
    queryFn: () => apiFetch<PaperOrdersResponse>("/api/paper-trading/orders"),
    enabled: !!user,
  });

  const counts: TourCounts = useMemo(
    () => ({
      watchlistItems: countItems(watchlistsQuery.data),
      alertRules: alertsQuery.data?.rules?.length ?? 0,
      paperOrders: ordersQuery.data?.length ?? 0,
    }),
    [watchlistsQuery.data, alertsQuery.data, ordersQuery.data],
  );

  // The record lives in localStorage because pages mark their visit outside
  // React. Mirror it in state so writes re-render, and re-read once the user id
  // is known -- keying progress on a not-yet-loaded user would file it under the
  // wrong account and silently lose it.
  const [record, setRecord] = useState<TourRecord>(() =>
    userId === undefined ? EMPTY_TOUR : readTour(userId),
  );
  useEffect(() => {
    setRecord(userId === undefined ? EMPTY_TOUR : readTour(userId));
  }, [userId]);

  const isLoading =
    userId === undefined ||
    onboarding.isLoading ||
    watchlistsQuery.isLoading ||
    alertsQuery.isLoading ||
    ordersQuery.isLoading;

  const configDone = useMemo(() => {
    const relevant = onboarding.steps.filter((step) => step.id === "trading" || step.id === "taxes");
    return relevant.length > 0 && relevant.every((step) => step.completed);
  }, [onboarding.steps]);

  const steps: TourStep[] = useMemo(
    () => [
      { id: "basics", target: "/settings", completed: configDone, evidence: "config" },
      {
        id: "findSymbol",
        target: "/scanner",
        completed: !!record.visited.scanner,
        evidence: "visited",
      },
      {
        id: "readAnalysis",
        target: "/analysis/AAPL",
        completed: !!record.visited.analysis,
        evidence: "visited",
      },
      {
        id: "watchlist",
        target: "/watchlists",
        completed: grewSinceBaseline(record.baseline, counts.watchlistItems, "watchlistItems"),
        evidence: "created",
      },
      {
        id: "alert",
        target: "/alerts",
        completed: grewSinceBaseline(record.baseline, counts.alertRules, "alertRules"),
        evidence: "created",
      },
      {
        id: "paperTrade",
        target: "/paper-trading",
        completed: grewSinceBaseline(record.baseline, counts.paperOrders, "paperOrders"),
        evidence: "created",
      },
      {
        id: "autoExecution",
        target: null,
        completed: !!record.completedAt,
        evidence: "acknowledged",
      },
    ],
    [configDone, counts, record],
  );

  const completedCount = steps.filter((step) => step.completed).length;

  const start = useCallback(() => {
    if (userId === undefined) return;
    setRecord(startTour(userId, counts, new Date().toISOString()));
  }, [userId, counts]);

  const finish = useCallback(() => {
    if (userId === undefined) return;
    setRecord(completeTour(userId, new Date().toISOString()));
  }, [userId]);

  const restart = useCallback(() => {
    if (userId === undefined) return;
    resetTour(userId);
    setRecord(startTour(userId, counts, new Date().toISOString()));
  }, [userId, counts]);

  return {
    steps,
    completedCount,
    total: steps.length,
    started: !!record.startedAt,
    finished: !!record.completedAt,
    isLoading,
    start,
    finish,
    restart,
  };
}
