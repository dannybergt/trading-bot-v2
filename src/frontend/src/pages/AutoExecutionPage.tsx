import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";

type Limits = {
  enabled: boolean;
  mode: "paper" | "live";
  liveModeAvailable: boolean;
  maxPositionSizeUsd: number;
  maxDailyLossUsd: number;
  maxOpenPositions: number;
  maxPortfolioBeta: number;
  allowedAssetClasses: string[];
  perStrategyBudgetPct: Record<string, number>;
  updatedAt?: string | null;
};

type AutoExecutionEvent = {
  id: number;
  proposalId?: string | null;
  symbol?: string | null;
  side?: string | null;
  status: string;
  reason?: string | null;
  createdAt?: string | null;
};

type EventsPayload = { items: AutoExecutionEvent[] };

const ASSET_CLASS_OPTIONS = ["stock", "etf", "crypto"] as const;

export function AutoExecutionPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Limits | null>(null);
  const [confirmEnable, setConfirmEnable] = useState(false);
  const [confirmHalt, setConfirmHalt] = useState(false);
  const [confirmLiveMode, setConfirmLiveMode] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const limitsQuery = useQuery({
    queryKey: ["auto-execution-limits"],
    queryFn: () => apiFetch<Limits>("/api/auto-execution/limits"),
  });

  const eventsQuery = useQuery({
    queryKey: ["auto-execution-events"],
    queryFn: () => apiFetch<EventsPayload>("/api/auto-execution/events?limit=25"),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (limitsQuery.data) setDraft(limitsQuery.data);
  }, [limitsQuery.data]);

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<Limits>) =>
      apiFetch<Limits>("/api/auto-execution/limits", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setDraft(data);
      queryClient.invalidateQueries({ queryKey: ["auto-execution-limits"] });
      queryClient.invalidateQueries({ queryKey: ["auto-execution-events"] });
      setFeedback(t("autoExecution.feedback.saved"));
    },
    onError: (err) => setFeedback((err as ApiError).message),
  });

  const haltMutation = useMutation({
    mutationFn: () =>
      apiFetch<{ halted: boolean; openOrdersAtHalt: number }>("/api/auto-execution/halt", {
        method: "POST",
        body: JSON.stringify({ reason: "manual_user_halt" }),
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["auto-execution-limits"] });
      queryClient.invalidateQueries({ queryKey: ["auto-execution-events"] });
      setFeedback(t("autoExecution.feedback.halted", { count: data.openOrdersAtHalt }));
      setConfirmHalt(false);
    },
    onError: (err) => setFeedback((err as ApiError).message),
  });

  const isDirty = useMemo(() => {
    if (!draft || !limitsQuery.data) return false;
    return JSON.stringify(draft) !== JSON.stringify(limitsQuery.data);
  }, [draft, limitsQuery.data]);

  if (!draft) {
    return (
      <div className="card" data-testid="auto-execution-page">
        <p className="text-sm text-slate-400">{t("autoExecution.loading")}</p>
      </div>
    );
  }

  const toggleAssetClass = (cls: string) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            allowedAssetClasses: prev.allowedAssetClasses.includes(cls)
              ? prev.allowedAssetClasses.filter((c) => c !== cls)
              : [...prev.allowedAssetClasses, cls],
          }
        : prev,
    );
  };

  const handleEnableChange = (next: boolean) => {
    if (next && !draft.enabled) {
      setConfirmEnable(true);
      return;
    }
    setDraft({ ...draft, enabled: next });
  };

  const confirmEnableNow = () => {
    setDraft({ ...draft, enabled: true });
    setConfirmEnable(false);
  };

  const handleModeChange = (next: "paper" | "live") => {
    if (next === draft.mode) return;
    if (next === "live") {
      // Hard refusal at the UI layer too — backend would silently drop the
      // value back to paper anyway, but we don't even let the modal open
      // until liveModeAvailable is true.
      if (!draft.liveModeAvailable) return;
      setConfirmLiveMode(true);
      return;
    }
    setDraft({ ...draft, mode: next });
  };

  const confirmLiveModeNow = () => {
    setDraft({ ...draft, mode: "live" });
    setConfirmLiveMode(false);
  };

  const save = () => {
    updateMutation.mutate({
      enabled: draft.enabled,
      mode: draft.mode,
      maxPositionSizeUsd: draft.maxPositionSizeUsd,
      maxDailyLossUsd: draft.maxDailyLossUsd,
      maxOpenPositions: draft.maxOpenPositions,
      maxPortfolioBeta: draft.maxPortfolioBeta,
      allowedAssetClasses: draft.allowedAssetClasses,
    });
  };

  const events = eventsQuery.data?.items ?? [];

  return (
    <div className="space-y-4" data-testid="auto-execution-page">
      <header>
        <h1 className="text-2xl font-semibold">{t("autoExecution.title")}</h1>
        <p className="text-sm text-slate-400">{t("autoExecution.subtitle")}</p>
      </header>

      <section
        className={`card ${
          !draft.enabled
            ? "border-amber-500/40"
            : draft.mode === "live"
            ? "border-red-700/50"
            : "border-bergt-green/40"
        }`}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">
              {draft.enabled
                ? draft.mode === "live"
                  ? t("autoExecution.statusEnabledLive")
                  : t("autoExecution.statusEnabledPaper")
                : t("autoExecution.statusDisabled")}
            </h2>
            <p className="text-xs text-slate-500">
              {draft.enabled
                ? draft.mode === "live"
                  ? t("autoExecution.statusEnabledLiveHelp")
                  : t("autoExecution.statusEnabledPaperHelp")
                : t("autoExecution.statusDisabledHelp")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => handleEnableChange(e.target.checked)}
                data-testid="auto-execution-enabled-toggle"
              />
              <span>{t("autoExecution.toggleLabel")}</span>
            </label>
            <button
              type="button"
              className="btn border-red-700/50 text-red-200"
              onClick={() => setConfirmHalt(true)}
              data-testid="auto-execution-halt-btn"
            >
              {t("autoExecution.haltButton")}
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-slate-800 pt-3">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            {t("autoExecution.modeLabel")}
          </span>
          <label className="flex items-center gap-1 text-sm">
            <input
              type="radio"
              name="auto-execution-mode"
              value="paper"
              checked={draft.mode === "paper"}
              onChange={() => handleModeChange("paper")}
              data-testid="auto-execution-mode-paper"
            />
            <span>{t("autoExecution.modePaper")}</span>
          </label>
          <label
            className={`flex items-center gap-1 text-sm ${
              draft.liveModeAvailable ? "" : "opacity-40"
            }`}
            title={draft.liveModeAvailable ? "" : t("autoExecution.modeLiveLockedHint")}
          >
            <input
              type="radio"
              name="auto-execution-mode"
              value="live"
              checked={draft.mode === "live"}
              disabled={!draft.liveModeAvailable}
              onChange={() => handleModeChange("live")}
              data-testid="auto-execution-mode-live"
            />
            <span>{t("autoExecution.modeLive")}</span>
            {!draft.liveModeAvailable ? (
              <span className="ml-1 rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[9px] uppercase tracking-wide text-slate-400">
                {t("autoExecution.modeLockedBadge")}
              </span>
            ) : null}
          </label>
          <span className="text-[10px] text-slate-500">
            {draft.mode === "paper"
              ? draft.liveModeAvailable
                ? t("autoExecution.modePaperHint")
                : t("autoExecution.modeLiveLockedHint")
              : t("autoExecution.modeLiveHint")}
          </span>
        </div>
      </section>

      <section className="card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          {t("autoExecution.limits.title")}
        </h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("autoExecution.limits.maxPositionSize")}</span>
            <input
              type="number"
              className="input"
              min={0}
              step={50}
              value={draft.maxPositionSizeUsd}
              onChange={(e) =>
                setDraft({ ...draft, maxPositionSizeUsd: Number(e.target.value) })
              }
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("autoExecution.limits.maxDailyLoss")}</span>
            <input
              type="number"
              className="input"
              min={0}
              step={50}
              value={draft.maxDailyLossUsd}
              onChange={(e) => setDraft({ ...draft, maxDailyLossUsd: Number(e.target.value) })}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("autoExecution.limits.maxOpenPositions")}</span>
            <input
              type="number"
              className="input"
              min={0}
              step={1}
              value={draft.maxOpenPositions}
              onChange={(e) =>
                setDraft({ ...draft, maxOpenPositions: Number(e.target.value) })
              }
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-400">{t("autoExecution.limits.maxPortfolioBeta")}</span>
            <input
              type="number"
              className="input"
              min={0}
              step={0.1}
              value={draft.maxPortfolioBeta}
              onChange={(e) =>
                setDraft({ ...draft, maxPortfolioBeta: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <div>
          <p className="text-xs text-slate-400">
            {t("autoExecution.limits.allowedAssetClasses")}
          </p>
          <div className="mt-1 flex gap-3 text-sm">
            {ASSET_CLASS_OPTIONS.map((cls) => (
              <label key={cls} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={draft.allowedAssetClasses.includes(cls)}
                  onChange={() => toggleAssetClass(cls)}
                />
                <span>{cls}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!isDirty || updateMutation.isPending}
            onClick={save}
            data-testid="auto-execution-save-btn"
          >
            {updateMutation.isPending ? t("autoExecution.saving") : t("autoExecution.save")}
          </button>
          {feedback ? <span className="text-xs text-slate-400">{feedback}</span> : null}
        </div>
      </section>

      <section className="card space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          {t("autoExecution.events.title")}
        </h2>
        <p className="text-xs text-slate-500">{t("autoExecution.events.subtitle")}</p>
        {events.length === 0 ? (
          <p className="text-xs text-slate-500">{t("autoExecution.events.empty")}</p>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">When</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Status</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-t border-slate-800">
                  <td className="py-1 text-slate-400">
                    {event.createdAt ? new Date(event.createdAt).toLocaleString() : "—"}
                  </td>
                  <td>{event.symbol ?? "—"}</td>
                  <td>{event.side ?? "—"}</td>
                  <td>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${
                        event.status === "accepted"
                          ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
                          : event.status === "halted"
                          ? "border-red-700/50 bg-red-900/40 text-red-200"
                          : "border-slate-700 bg-slate-900 text-slate-300"
                      }`}
                    >
                      {event.status}
                    </span>
                  </td>
                  <td className="text-slate-400">{event.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {confirmEnable ? (
        <ConfirmModal
          title={t("autoExecution.confirmEnable.title")}
          body={t("autoExecution.confirmEnable.body")}
          confirmLabel={t("autoExecution.confirmEnable.confirm")}
          cancelLabel={t("autoExecution.confirmEnable.cancel")}
          onConfirm={confirmEnableNow}
          onCancel={() => setConfirmEnable(false)}
        />
      ) : null}
      {confirmHalt ? (
        <ConfirmModal
          title={t("autoExecution.confirmHalt.title")}
          body={t("autoExecution.confirmHalt.body")}
          confirmLabel={t("autoExecution.confirmHalt.confirm")}
          cancelLabel={t("autoExecution.confirmHalt.cancel")}
          danger
          onConfirm={() => haltMutation.mutate()}
          onCancel={() => setConfirmHalt(false)}
        />
      ) : null}
      {confirmLiveMode ? (
        <ConfirmModal
          title={t("autoExecution.confirmLiveMode.title")}
          body={t("autoExecution.confirmLiveMode.body")}
          confirmLabel={t("autoExecution.confirmLiveMode.confirm")}
          cancelLabel={t("autoExecution.confirmLiveMode.cancel")}
          danger
          onConfirm={confirmLiveModeNow}
          onCancel={() => setConfirmLiveMode(false)}
        />
      ) : null}
    </div>
  );
}

function ConfirmModal({
  title,
  body,
  confirmLabel,
  cancelLabel,
  danger,
  onConfirm,
  onCancel,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-md border border-slate-700 bg-slate-900 p-4 shadow-xl">
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="mt-2 text-sm text-slate-300">{body}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${danger ? "border-red-700/50 text-red-200" : "btn-primary"}`}
            onClick={onConfirm}
            data-testid="auto-execution-confirm-btn"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
