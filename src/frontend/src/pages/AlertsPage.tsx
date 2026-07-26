import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";

type WatchlistItem = { symbol: string };

type Watchlist = {
  id: string;
  name: string;
  items: WatchlistItem[];
};

type AlertRule = {
  id: number;
  watchlistId: string;
  symbol: string;
  name: string;
  ruleType: "provider_move" | "news_sentiment" | "signal_direction" | "tag_priority";
  threshold: number | null;
  direction: string | null;
  tag: string | null;
  enabled: boolean;
  snoozedUntil: string | null;
  lastTriggeredAt: string | null;
};

type AlertEvent = {
  id: number;
  ruleId: number;
  watchlistId: string;
  symbol: string;
  eventType: string;
  severity: string;
  status: "open" | "acknowledged";
  title: string;
  message: string;
  triggeredAt: string | null;
  acknowledgedAt: string | null;
};

type AlertsResponse = {
  rules: AlertRule[];
  events: AlertEvent[];
  summary: {
    rules: number;
    enabledRules: number;
    openEvents: number;
    createdEvents: number;
  };
};

const RULE_TYPES: AlertRule["ruleType"][] = [
  "provider_move",
  "news_sentiment",
  "signal_direction",
  "tag_priority",
];

export function AlertsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => apiFetch<Watchlist[]>("/api/watchlists"),
  });
  const alertsQuery = useQuery({
    queryKey: ["alerts"],
    queryFn: () => apiFetch<AlertsResponse>("/api/alerts"),
    refetchInterval: 60_000,
  });

  const watchlists = watchlistsQuery.data ?? [];
  const [watchlistId, setWatchlistId] = useState("");
  const [symbol, setSymbol] = useState("");
  const [ruleType, setRuleType] = useState<AlertRule["ruleType"]>("tag_priority");
  const [threshold, setThreshold] = useState("");
  const [direction, setDirection] = useState("");
  const [tag, setTag] = useState("priority");
  const [name, setName] = useState("");

  const symbolsForWatchlist = useMemo(() => {
    return watchlists.find((wl) => wl.id === watchlistId)?.items ?? [];
  }, [watchlistId, watchlists]);

  const createRule = useMutation({
    mutationFn: () =>
      apiFetch<AlertRule>("/api/alerts/rules", {
        method: "POST",
        body: {
          watchlistId,
          symbol,
          ruleType,
          name: name.trim(),
          threshold: threshold === "" ? undefined : Number(threshold),
          direction: direction.trim() || undefined,
          tag: ruleType === "tag_priority" ? tag.trim() || undefined : undefined,
        },
      }),
    onSuccess: () => {
      setSymbol("");
      setName("");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const deleteRule = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/alerts/rules/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const ackEvent = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/alerts/events/${id}/ack`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!watchlistId || !symbol || !ruleType) {
      return;
    }
    createRule.mutate();
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("alerts.title")}</h1>
        <p className="text-sm text-slate-400">
          {t("alerts.subtitle")}
        </p>
      </header>

      <form onSubmit={handleCreate} className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("alerts.form.watchlist")}</span>
          <select
            className="input"
            value={watchlistId}
            onChange={(event) => {
              setWatchlistId(event.target.value);
              setSymbol("");
            }}
            required
          >
            <option value="">{t("alerts.form.selectWatchlist")}</option>
            {watchlists.map((wl) => (
              <option key={wl.id} value={wl.id}>
                {wl.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("alerts.form.symbol")}</span>
          <select
            className="input"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            disabled={!watchlistId}
            required
          >
            <option value="">{t("alerts.form.selectSymbol")}</option>
            {symbolsForWatchlist.map((item) => (
              <option key={item.symbol} value={item.symbol}>
                {item.symbol}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("alerts.form.ruleType")}</span>
          <select
            className="input"
            value={ruleType}
            onChange={(event) =>
              setRuleType(event.target.value as AlertRule["ruleType"])
            }
          >
            {RULE_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`alerts.ruleTypes.${type}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">
            {t("alerts.form.threshold")} {t(`alerts.thresholdHint.${ruleType}`)}
          </span>
          <input
            type="number"
            step="0.01"
            className="input"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            placeholder={thresholdPlaceholder(ruleType)}
          />
        </label>
        {(ruleType === "signal_direction" || ruleType === "news_sentiment") && (
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">{t("alerts.form.direction")}</span>
            <input
              className="input"
              value={direction}
              onChange={(event) => setDirection(event.target.value)}
              placeholder={t(`alerts.directionPlaceholder.${ruleType}`)}
            />
          </label>
        )}
        {ruleType === "tag_priority" && (
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">{t("alerts.form.tag")}</span>
            <input
              className="input"
              value={tag}
              onChange={(event) => setTag(event.target.value)}
              placeholder="priority"
            />
          </label>
        )}
        <label className="block text-sm sm:col-span-2 lg:col-span-3">
          <span className="mb-1 block text-slate-300">{t("alerts.form.name")}</span>
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={`${symbol || "Symbol"} ${ruleType.replace("_", " ")}`}
          />
        </label>
        <div className="sm:col-span-2 lg:col-span-3">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!watchlistId || !symbol || createRule.isPending}
          >
            {createRule.isPending ? t("alerts.form.adding") : t("alerts.form.add")}
          </button>
          {createRule.error ? (
            <span className="ml-3 text-sm text-red-300">
              {(createRule.error as ApiError).message}
            </span>
          ) : null}
        </div>
      </form>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("alerts.rules.title")}</h2>
        {alertsQuery.isLoading ? (
          <p className="text-sm text-slate-400">{t("alerts.loading")}</p>
        ) : null}
        {alertsQuery.data && alertsQuery.data.rules.length === 0 ? (
          <p className="text-sm text-slate-500">{t("alerts.rules.empty")}</p>
        ) : null}
        <ul className="space-y-2">
          {(alertsQuery.data?.rules ?? []).map((rule) => (
            <li key={rule.id} className="card flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{rule.name}</p>
                <p className="text-xs text-slate-400">
                  {rule.symbol} · {t(`alerts.ruleTypes.${rule.ruleType}`)}
                  {rule.threshold !== null ? ` · ≥ ${rule.threshold}` : ""}
                  {rule.direction ? ` · ${rule.direction}` : ""}
                  {rule.tag ? ` · #${rule.tag}` : ""}
                </p>
                {rule.lastTriggeredAt ? (
                  <p className="text-xs text-slate-500">
                    {t("alerts.rules.lastTriggered", {
                      when: new Date(rule.lastTriggeredAt).toLocaleString(),
                    })}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => deleteRule.mutate(rule.id)}
                disabled={deleteRule.isPending}
              >
                {t("alerts.rules.delete")}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("alerts.events.title")}</h2>
        {alertsQuery.data && alertsQuery.data.events.length === 0 ? (
          <p className="text-sm text-slate-500">{t("alerts.events.empty")}</p>
        ) : null}
        <ul className="space-y-2">
          {(alertsQuery.data?.events ?? []).map((event) => (
            <li key={event.id} className="card flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">
                  <span
                    className={`mr-2 inline-block rounded-full px-2 py-0.5 text-xs ${severityClass(
                      event.severity,
                    )}`}
                  >
                    {t(`alerts.severity.${event.severity}`, {
                      defaultValue: event.severity,
                    })}
                  </span>
                  {event.title}
                </p>
                <p className="text-sm text-slate-300">{event.message}</p>
                {event.triggeredAt ? (
                  <p className="text-xs text-slate-500">
                    {t("alerts.events.triggered", {
                      when: new Date(event.triggeredAt).toLocaleString(),
                    })}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => ackEvent.mutate(event.id)}
                disabled={ackEvent.isPending}
              >
                {t("alerts.events.acknowledge")}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}


function thresholdPlaceholder(ruleType: AlertRule["ruleType"]): string {
  switch (ruleType) {
    case "provider_move":
      return "1.0";
    case "news_sentiment":
      return "0.1";
    case "signal_direction":
      return "0.75";
    case "tag_priority":
      return "45";
  }
}


function severityClass(severity: string): string {
  switch (severity) {
    case "high":
      return "bg-red-900/60 text-red-200 border border-red-700/60";
    case "medium":
      return "bg-amber-900/40 text-amber-200 border border-amber-700/60";
    default:
      return "bg-slate-800 text-slate-300 border border-slate-700";
  }
}
