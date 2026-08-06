import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ACCESS_TOKEN_KEY, ApiError, apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { InfoTooltip } from "../components/InfoTooltip";

type AdminUser = {
  id: number;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  mfa_enabled: boolean;
};

type BackupListItem = {
  filename: string;
  size_bytes: number;
  modified_at: string;
};

export function AdminPage() {
  const { user } = useAuth();
  const { t } = useTranslation();
  if (!user) {
    return null;
  }
  if (!user.is_admin) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">{t("admin.title")}</h1>
        <p className="text-sm text-slate-400">{t("admin.subtitle")}</p>
      </header>
      <ErrorBoundary variant="section" scope="admin-users">
        <UsersSection />
      </ErrorBoundary>
      <ErrorBoundary variant="section" scope="admin-data-sources">
        <DataSourcesSection />
      </ErrorBoundary>
      <ErrorBoundary variant="section" scope="admin-composite-weights">
        <CompositeWeightsSection />
      </ErrorBoundary>
      <ErrorBoundary variant="section" scope="admin-backups">
        <BackupsSection />
      </ErrorBoundary>
      <ErrorBoundary variant="section" scope="admin-export">
        <ExportSection />
      </ErrorBoundary>
    </div>
  );
}

type DataSourceCatalogueEntry = {
  key: string;
  label: string;
  covers: string[];
  freeTierLimit: string;
  upgradeTier: string | null;
  upgradeCostUsdMonthly: number;
  upgradeBenefit: string;
  envFlag: string | null;
  configured: boolean;
};

type CompositeWeights = {
  technical: number;
  analyst: number;
  fundamentals: number;
  news: number;
};

const COMPOSITE_AXES: (keyof CompositeWeights)[] = [
  "technical",
  "analyst",
  "fundamentals",
  "news",
];

// Axis labels live in the i18n bundle (`admin.composite.axis.*`) so the page
// carries no second, untranslated copy of them.
const COMPOSITE_AXIS_KEY: Record<keyof CompositeWeights, string> = {
  technical: "admin.composite.axis.technical",
  analyst: "admin.composite.axis.analyst",
  fundamentals: "admin.composite.axis.fundamentals",
  news: "admin.composite.axis.news",
};

// Operator control over the composite decision-score weights. The backend
// normalises whatever is entered to sum 1.0; here we present each axis as a
// percentage of the current total so admins see the effective split live.
function CompositeWeightsSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["admin-composite-weights"],
    queryFn: () =>
      apiFetch<{ weights: CompositeWeights; default: CompositeWeights; isCustom: boolean }>(
        "/api/admin/composite-weights",
      ),
  });
  const readinessQuery = useQuery({
    queryKey: ["admin-composite-readiness"],
    queryFn: () =>
      apiFetch<{
        total: number;
        labeled: number;
        fullAxisLabeled: number;
        threshold: number;
        ready: boolean;
        earliestSnapshot: string | null;
        latestSnapshot: string | null;
        horizonDays: number;
      }>("/api/admin/composite-readiness"),
  });
  const [draft, setDraft] = useState<Record<keyof CompositeWeights, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calibReport, setCalibReport] = useState<CompositeCalibrationReport | null>(null);

  const effective = query.data?.weights;
  const values: Record<keyof CompositeWeights, string> =
    draft ??
    (effective
      ? {
          technical: String(Math.round(effective.technical * 100)),
          analyst: String(Math.round(effective.analyst * 100)),
          fundamentals: String(Math.round(effective.fundamentals * 100)),
          news: String(Math.round(effective.news * 100)),
        }
      : { technical: "", analyst: "", fundamentals: "", news: "" });

  const total = COMPOSITE_AXES.reduce((acc, axis) => {
    const n = Number(values[axis]);
    return acc + (Number.isFinite(n) && n >= 0 ? n : 0);
  }, 0);

  const invalid =
    total <= 0 ||
    COMPOSITE_AXES.some((axis) => {
      const n = Number(values[axis]);
      return values[axis] === "" || !Number.isFinite(n) || n < 0;
    });

  const saveMutation = useMutation({
    mutationFn: () =>
      apiFetch("/api/admin/composite-weights", {
        method: "PUT",
        body: {
          technical: Number(values.technical),
          analyst: Number(values.analyst),
          fundamentals: Number(values.fundamentals),
          news: Number(values.news),
        },
      }),
    onSuccess: () => {
      setDraft(null);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-composite-weights"] });
    },
    onError: (err) =>
      setError(
        err instanceof ApiError ? err.message : t("admin.composite.saveFailed"),
      ),
  });

  const calibrateMutation = useMutation({
    mutationFn: () =>
      apiFetch<CompositeCalibrationReport>("/api/admin/composite-calibrate", {
        method: "POST",
        body: { apply: true },
      }),
    onSuccess: (data) => {
      setCalibReport(data);
      queryClient.invalidateQueries({ queryKey: ["admin-composite-weights"] });
      queryClient.invalidateQueries({ queryKey: ["admin-composite-readiness"] });
    },
    onError: (err) =>
      setError(
        err instanceof ApiError
          ? err.message
          : t("admin.composite.calibrationFailed"),
      ),
  });

  return (
    <section className="space-y-3" data-testid="admin-composite-weights-section">
      <header>
        <h2 className="flex items-center gap-1.5 text-lg font-medium">
          {t("admin.composite.title")}
          <InfoTooltip
            text={t("tooltips.admin.weights")}
            topic="admin"
            testId="tip-composite-weights"
          />
        </h2>
        <p className="text-sm text-slate-400">
          {t("admin.composite.description")}{" "}
          {query.data?.isCustom
            ? t("admin.composite.customActive")
            : t("admin.composite.usingDefaults")}
        </p>
      </header>
      <div className="grid gap-3 sm:grid-cols-2">
        {COMPOSITE_AXES.map((axis) => {
          const n = Number(values[axis]);
          const pct =
            total > 0 && Number.isFinite(n) && n >= 0
              ? Math.round((n / total) * 100)
              : 0;
          return (
            <label key={axis} className="flex flex-col gap-1 text-sm">
              <span className="text-slate-300">{t(COMPOSITE_AXIS_KEY[axis])}</span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  step="1"
                  value={values[axis]}
                  onChange={(event) =>
                    setDraft({ ...values, [axis]: event.target.value })
                  }
                  className="w-24 rounded border border-slate-600 bg-slate-800 px-2 py-1"
                  data-testid={`composite-weight-${axis}`}
                />
                <span className="text-xs text-slate-400">→ {pct}%</span>
              </div>
            </label>
          );
        })}
      </div>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={invalid || saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
          className="rounded bg-sky-600 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          data-testid="composite-weights-save"
        >
          {saveMutation.isPending
            ? t("admin.composite.saving")
            : t("admin.composite.save")}
        </button>
        {draft ? (
          <button
            type="button"
            onClick={() => {
              setDraft(null);
              setError(null);
            }}
            className="text-sm text-slate-400"
          >
            {t("admin.composite.reset")}
          </button>
        ) : null}
      </div>
      {readinessQuery.data ? (
        <div
          className="rounded border border-slate-700 bg-slate-900/40 p-3 text-sm"
          data-testid="composite-readiness"
        >
          <p className="flex items-center gap-1.5 font-medium text-slate-200">
            {t("admin.composite.readinessTitle")}
            <InfoTooltip
              text={t("tooltips.admin.readiness")}
              topic="admin"
              testId="tip-composite-readiness"
            />
          </p>
          <p className="text-slate-400">
            {t("admin.composite.readinessSamples", {
              fullAxis: readinessQuery.data.fullAxisLabeled,
              threshold: readinessQuery.data.threshold,
              labeled: readinessQuery.data.labeled,
              total: readinessQuery.data.total,
              horizon: readinessQuery.data.horizonDays,
            })}{" "}
            {readinessQuery.data.ready
              ? t("admin.composite.readinessReady")
              : t("admin.composite.readinessCollecting")}
          </p>
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              disabled={calibrateMutation.isPending}
              onClick={() => calibrateMutation.mutate()}
              className="rounded border border-slate-600 px-3 py-1.5 text-sm disabled:opacity-50"
              data-testid="composite-calibrate"
            >
              {calibrateMutation.isPending
                ? t("admin.composite.calibrating")
                : t("admin.composite.calibrate")}
            </button>
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              {t("admin.composite.calibrateNote")}
              <InfoTooltip
                text={t("tooltips.admin.calibrate")}
                topic="admin"
                testId="tip-composite-calibrate"
              />
            </span>
          </div>
          {calibReport ? (
            <p className="mt-2 text-xs text-slate-400" data-testid="composite-calibrate-report">
              {calibReport.applied
                ? t("admin.composite.calibrateApplied", {
                    axes: calibReport.calibratedAxes?.join(", "),
                    from: ((calibReport.currentHitRate ?? 0) * 100).toFixed(1),
                    to: ((calibReport.bestHitRate ?? 0) * 100).toFixed(1),
                    labeled: calibReport.labeled,
                  })
                : t("admin.composite.calibrateNotApplied", {
                    reason:
                      calibReport.reason ??
                      (calibReport.improved === false
                        ? t("admin.composite.calibrateNoImprovement")
                        : t("admin.composite.calibrateUnknownReason")),
                    labeled: calibReport.labeled ?? 0,
                  })}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

type CompositeCalibrationReport = {
  applied: boolean;
  labeled?: number;
  reason?: string;
  improved?: boolean;
  calibratedAxes?: string[];
  currentHitRate?: number;
  bestHitRate?: number;
};

type PlatformConfigItem = {
  key: string;
  source: "db" | "env" | "unconfigured";
  configured: boolean;
  lastUpdatedAt: string | null;
  lastUpdatedByUserId: number | null;
};

// Maps catalogue keys (`alpha_vantage`) to the platform_config key that
// stores the secret (`ALPHA_VANTAGE_API_KEY`). Providers without an entry
// are not configurable through the UI (yfinance, Reddit, StockTwits etc.
// need no key; Alpaca is per-user via `/settings`).
const PROVIDER_TO_MANAGED_KEY: Record<string, string> = {
  alpha_vantage: "ALPHA_VANTAGE_API_KEY",
  fmp: "FMP_API_KEY",
  twelve_data: "TWELVE_DATA_API_KEY",
  coingecko: "COINGECKO_API_KEY",
  fred: "FRED_API_KEY",
  rss: "RSS_NEWS_FEEDS",
  sentiment: "SENTIMENT_PROVIDER",
};

function DataSourcesSection() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["admin-data-sources"],
    queryFn: () => apiFetch<{ providers: DataSourceCatalogueEntry[] }>("/api/admin/data-sources"),
  });
  const platformConfigQuery = useQuery({
    queryKey: ["admin-platform-config"],
    queryFn: () =>
      apiFetch<{ items: PlatformConfigItem[]; managedKeys: string[] }>(
        "/api/admin/platform-config",
      ),
  });
  const [editKey, setEditKey] = useState<string | null>(null);
  const providers = query.data?.providers ?? [];
  const platformConfig = platformConfigQuery.data?.items ?? [];
  const configByKey = Object.fromEntries(
    platformConfig.map((item) => [item.key, item]),
  );

  if (providers.length === 0) {
    return null;
  }

  const monthlyTotal = providers
    .filter((p) => p.configured && p.upgradeCostUsdMonthly > 0)
    .reduce((acc, p) => acc + p.upgradeCostUsdMonthly, 0);

  return (
    <section className="space-y-3" data-testid="admin-data-sources-section">
      <header>
        <h2 className="text-lg font-semibold">{t("admin.dataSources.title")}</h2>
        <p className="text-sm text-slate-400">
          {t("admin.dataSources.description")}
        </p>
      </header>
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-2">{t("admin.dataSources.colProvider")}</th>
              <th>{t("admin.dataSources.colConfigured")}</th>
              <th>{t("admin.dataSources.colSource")}</th>
              <th>{t("admin.dataSources.colCovers")}</th>
              <th>{t("admin.dataSources.colFreeTier")}</th>
              <th>{t("admin.dataSources.colUpgrade")}</th>
              <th className="text-right">{t("admin.dataSources.colCost")}</th>
              <th>{t("admin.dataSources.colWhy")}</th>
              <th className="text-right">{t("admin.dataSources.colAction")}</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((entry) => {
              const managedKey = PROVIDER_TO_MANAGED_KEY[entry.key];
              const cfg = managedKey ? configByKey[managedKey] : undefined;
              return (
                <tr
                  key={entry.key}
                  className="border-t border-slate-800 align-top"
                >
                  <td className="py-2 font-medium">{entry.label}</td>
                  <td>
                    <span
                      className={
                        entry.configured ? "text-bergt-green" : "text-amber-300"
                      }
                    >
                      {entry.configured
                        ? t("admin.dataSources.yes")
                        : t("admin.dataSources.no")}
                    </span>
                  </td>
                  <td className="text-slate-400">
                    {cfg ? cfg.source : "—"}
                  </td>
                  <td className="text-slate-300">{entry.covers.join(", ")}</td>
                  <td className="text-slate-400">{entry.freeTierLimit}</td>
                  <td>{entry.upgradeTier ?? "—"}</td>
                  <td className="text-right font-mono">
                    {entry.upgradeCostUsdMonthly > 0
                      ? `$${entry.upgradeCostUsdMonthly}`
                      : "—"}
                  </td>
                  <td className="text-slate-400">{entry.upgradeBenefit}</td>
                  <td className="text-right">
                    {managedKey ? (
                      <button
                        type="button"
                        className="btn"
                        onClick={() => setEditKey(managedKey)}
                      >
                        {t("admin.dataSources.configure")}
                      </button>
                    ) : entry.key === "alpaca" ? (
                      <span className="text-xs text-slate-500">
                        {t("admin.dataSources.perUserSettings")}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500">
                        {t("admin.dataSources.noKey")}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        {t("admin.dataSources.monthlyTotal", { amount: `$${monthlyTotal}` })}
      </p>
      {editKey ? (
        <PlatformConfigEditor
          configKey={editKey}
          currentStatus={configByKey[editKey]}
          onClose={() => setEditKey(null)}
        />
      ) : null}
    </section>
  );
}

function PlatformConfigEditor({
  configKey,
  currentStatus,
  onClose,
}: {
  configKey: string;
  currentStatus: PlatformConfigItem | undefined;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    detail: string;
  } | null>(null);

  const saveMutation = useMutation({
    mutationFn: (next: string) =>
      apiFetch(`/api/admin/platform-config/${encodeURIComponent(configKey)}`, {
        method: "PUT",
        body: { value: next },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-platform-config"] });
      queryClient.invalidateQueries({ queryKey: ["admin-data-sources"] });
      onClose();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/api/admin/platform-config/${encodeURIComponent(configKey)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-platform-config"] });
      queryClient.invalidateQueries({ queryKey: ["admin-data-sources"] });
      onClose();
    },
  });

  const testMutation = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; detail: string }>(
        `/api/admin/platform-config/${encodeURIComponent(configKey)}/test`,
        { method: "POST" },
      ),
    onSuccess: (data) => setTestResult(data),
    onError: (err) =>
      setTestResult({ ok: false, detail: (err as ApiError).message }),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h3 className="text-lg font-semibold">
            {t("admin.platformConfig.title", { key: configKey })}
          </h3>
          <p className="text-xs text-slate-500">
            {t("admin.platformConfig.currentSource")}{" "}
            <span className="font-mono text-slate-300">
              {currentStatus?.source ?? t("admin.platformConfig.unconfigured")}
            </span>
            {currentStatus?.lastUpdatedAt ? (
              <>
                {` · ${t("admin.platformConfig.lastSet")} `}
                <span className="font-mono text-slate-300">
                  {new Date(currentStatus.lastUpdatedAt).toLocaleString()}
                </span>
              </>
            ) : null}
          </p>
        </header>
        <p className="text-xs text-slate-400">
          {t("admin.platformConfig.explainer")}
        </p>
        <label className="block text-sm">
          <span className="text-slate-300">
            {t("admin.platformConfig.newValue")}
          </span>
          <input
            className="input mt-1 w-full"
            type="password"
            placeholder={t("admin.platformConfig.valuePlaceholder")}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
        </label>
        {testResult ? (
          <p
            className={`text-xs ${
              testResult.ok ? "text-bergt-green" : "text-red-300"
            }`}
          >
            {t("admin.platformConfig.testResult", { detail: testResult.detail })}
          </p>
        ) : null}
        {saveMutation.error ? (
          <p className="text-xs text-red-300">
            {t("admin.platformConfig.saveError", {
              detail: (saveMutation.error as ApiError).message,
            })}
          </p>
        ) : null}
        {deleteMutation.error ? (
          <p className="text-xs text-red-300">
            {t("admin.platformConfig.unsetError", {
              detail: (deleteMutation.error as ApiError).message,
            })}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!value || saveMutation.isPending}
            onClick={() => saveMutation.mutate(value)}
          >
            {saveMutation.isPending
              ? t("admin.platformConfig.saving")
              : t("admin.platformConfig.save")}
          </button>
          <button
            type="button"
            className="btn"
            disabled={!value || testMutation.isPending}
            onClick={() => {
              // Save first then test, otherwise the test probe uses the
              // old stored value. We do a transient save by writing the
              // value, immediately probing, but the saved value is what
              // the user just typed.
              saveMutation.mutate(value, {
                onSuccess: () => testMutation.mutate(),
              });
            }}
          >
            {testMutation.isPending
              ? t("admin.platformConfig.testing")
              : t("admin.platformConfig.saveAndTest")}
          </button>
          {currentStatus?.source === "db" ? (
            <button
              type="button"
              className="btn"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending
                ? t("admin.platformConfig.unsetting")
                : t("admin.platformConfig.unset")}
            </button>
          ) : null}
          <button type="button" className="btn ml-auto" onClick={onClose}>
            {t("admin.platformConfig.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

function UsersSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AdminUser[]>("/api/auth/admin/users"),
  });

  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);

  const createUser = useMutation({
    mutationFn: () =>
      apiFetch<AdminUser>("/api/auth/admin/users", {
        method: "POST",
        body: { email: newEmail, password: newPassword, is_admin: newIsAdmin },
      }),
    onSuccess: () => {
      setNewEmail("");
      setNewPassword("");
      setNewIsAdmin(false);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  const resetMfa = useMutation({
    mutationFn: (userId: number) =>
      apiFetch(`/api/auth/admin/users/${userId}/reset-mfa`, { method: "PUT" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const setStatus = useMutation({
    mutationFn: ({ userId, active }: { userId: number; active: boolean }) =>
      apiFetch(`/api/auth/admin/users/${userId}/status?active=${active}`, {
        method: "PUT",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const resetPassword = useMutation({
    mutationFn: ({
      userId,
      newPassword,
      resetMfa: alsoResetMfa,
    }: {
      userId: number;
      newPassword: string;
      resetMfa: boolean;
    }) =>
      apiFetch(`/api/auth/admin/users/${userId}/password`, {
        method: "PUT",
        body: { new_password: newPassword, reset_mfa: alsoResetMfa },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!newEmail || !newPassword) return;
    createUser.mutate();
  }

  function handleResetPassword(userId: number) {
    const pwd = window.prompt(t("admin.users.promptPassword"));
    if (!pwd || pwd.length < 8) return;
    const alsoMfa = window.confirm(t("admin.users.promptResetMfa"));
    resetPassword.mutate({ userId, newPassword: pwd, resetMfa: alsoMfa });
  }

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">{t("admin.users.title")}</h2>
      <form onSubmit={handleCreate} className="card mb-4 grid gap-3 sm:grid-cols-4">
        {/* Beide Felder trugen ihre Semantik nur im placeholder: kein Label,
            kein htmlFor. Ein Screenreader las damit ein unbeschriftetes
            Eingabefeld vor, und beim Tippen verschwindet der Placeholder
            ohnehin. */}
        <label className="sm:col-span-2 block text-sm">
          <span className="mb-1 block text-slate-300">{t("admin.users.emailLabel")}</span>
          <input
            className="input"
            type="email"
            placeholder={t("admin.users.emailPlaceholder")}
            required
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("admin.users.passwordLabel")}</span>
          <input
            className="input"
            type="password"
            placeholder={t("admin.users.passwordPlaceholder")}
            required
            minLength={8}
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={newIsAdmin}
            onChange={(event) => setNewIsAdmin(event.target.checked)}
          />
          {t("admin.users.adminLabel")}
        </label>
        <div className="sm:col-span-4 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={createUser.isPending}>
            {createUser.isPending
              ? t("admin.users.creating")
              : t("admin.users.create")}
          </button>
          {createUser.error ? (
            <span className="text-sm text-red-300">
              {(createUser.error as ApiError).message}
            </span>
          ) : null}
        </div>
      </form>

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead className="bg-slate-900/60 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2 text-left">{t("admin.users.colId")}</th>
              <th className="px-3 py-2 text-left">{t("admin.users.colEmail")}</th>
              <th className="px-3 py-2 text-left">{t("admin.users.colRole")}</th>
              <th className="px-3 py-2 text-left">{t("admin.users.colStatus")}</th>
              <th className="px-3 py-2 text-left">{t("admin.users.colMfa")}</th>
              <th className="px-3 py-2 text-right">{t("admin.users.colActions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {(usersQuery.data ?? []).map((u) => (
              <tr key={u.id}>
                <td className="px-3 py-2 tabular-nums">{u.id}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">
                  {u.is_admin
                    ? t("admin.users.roleAdmin")
                    : t("admin.users.roleMember")}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      u.is_active
                        ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
                        : "border-red-700/50 bg-red-900/30 text-red-200"
                    }`}
                  >
                    {u.is_active
                      ? t("admin.users.statusActive")
                      : t("admin.users.statusInactive")}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {u.mfa_enabled ? t("admin.users.mfaOn") : t("admin.users.mfaOff")}
                </td>
                <td className="px-3 py-2 text-right space-x-2">
                  <button
                    type="button"
                    className="btn"
                    disabled={resetMfa.isPending || !u.mfa_enabled}
                    onClick={() => resetMfa.mutate(u.id)}
                  >
                    {t("admin.users.resetMfa")}
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => handleResetPassword(u.id)}
                  >
                    {t("admin.users.setPassword")}
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() =>
                      setStatus.mutate({ userId: u.id, active: !u.is_active })
                    }
                    disabled={setStatus.isPending}
                  >
                    {u.is_active
                      ? t("admin.users.deactivate")
                      : t("admin.users.activate")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BackupsSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const backupsQuery = useQuery({
    queryKey: ["admin-backups"],
    queryFn: () => apiFetch<{ items: BackupListItem[] }>("/api/admin/backups"),
  });
  const backups = backupsQuery.data?.items ?? [];

  const createBackup = useMutation({
    mutationFn: () => apiFetch("/api/admin/backups", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-backups"] }),
  });

  async function handleDownload(filename: string) {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    const response = await fetch(
      `/api/admin/backups/${encodeURIComponent(filename)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!response.ok) {
      window.alert(t("admin.backups.downloadFailed", { status: response.status }));
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">{t("admin.backups.title")}</h2>
      <div className="card mb-4 flex items-center gap-3">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => createBackup.mutate()}
          disabled={createBackup.isPending}
        >
          {createBackup.isPending
            ? t("admin.backups.creating")
            : t("admin.backups.create")}
        </button>
        {createBackup.error ? (
          <span className="text-sm text-red-300">
            {(createBackup.error as ApiError).message}
          </span>
        ) : null}
      </div>
      <ul className="space-y-2">
        {backups.map((backup) => (
          <li
            key={backup.filename}
            className="card flex flex-wrap items-center justify-between gap-3"
          >
            <div>
              <p className="font-medium">{backup.filename}</p>
              <p className="text-xs text-slate-500">
                {(backup.size_bytes / 1024).toFixed(1)} KB ·{" "}
                {new Date(backup.modified_at).toLocaleString()}
              </p>
            </div>
            <button
              type="button"
              className="btn"
              onClick={() => handleDownload(backup.filename)}
            >
              {t("admin.backups.download")}
            </button>
          </li>
        ))}
        {backupsQuery.data && backups.length === 0 ? (
          <p className="text-sm text-slate-500">{t("admin.backups.empty")}</p>
        ) : null}
      </ul>
    </section>
  );
}

function ExportSection() {
  const { t } = useTranslation();

  async function handleExport() {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    const response = await fetch("/api/admin/export", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      window.alert(t("admin.export.failed", { status: response.status }));
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `trading-bot-v2-export-${new Date()
      .toISOString()
      .replace(/[:.]/g, "")
      .slice(0, 15)}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">{t("admin.export.title")}</h2>
      <div className="card flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-400">{t("admin.export.description")}</p>
        <button type="button" className="btn btn-primary" onClick={handleExport}>
          {t("admin.export.download")}
        </button>
      </div>
    </section>
  );
}
