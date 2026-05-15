import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ACCESS_TOKEN_KEY, ApiError, apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ErrorBoundary } from "../components/ErrorBoundary";

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
  if (!user) {
    return null;
  }
  if (!user.is_admin) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Administration</h1>
        <p className="text-sm text-slate-400">
          Admin-only surface for user lifecycle and platform backups.
        </p>
      </header>
      <ErrorBoundary variant="section" scope="admin-users">
        <UsersSection />
      </ErrorBoundary>
      <ErrorBoundary variant="section" scope="admin-data-sources">
        <DataSourcesSection />
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
        <h2 className="text-lg font-semibold">Data sources</h2>
        <p className="text-sm text-slate-400">
          Which providers feed the recommendation engine. Recommended upgrades
          point at the next sensible tier per provider so you can decide where
          paid tiers would actually move the needle for buy/sell decisions.
          Providers with an API key can be configured in place — values are
          encrypted at rest and a 60s cache picks them up without a restart.
        </p>
      </header>
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-2">Provider</th>
              <th>Configured</th>
              <th>Source</th>
              <th>Covers</th>
              <th>Free-tier limit</th>
              <th>Upgrade</th>
              <th className="text-right">USD/mo</th>
              <th>Why upgrade</th>
              <th className="text-right">Action</th>
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
                      {entry.configured ? "yes" : "no"}
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
                        Configure
                      </button>
                    ) : entry.key === "alpaca" ? (
                      <span className="text-xs text-slate-500">
                        per-user (Settings)
                      </span>
                    ) : (
                      <span className="text-xs text-slate-500">no key</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        If every recommended upgrade were activated for currently-configured
        providers, the additional monthly cost would be approximately
        <span className="ml-1 font-mono text-slate-200">${monthlyTotal}</span>.
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
          <h3 className="text-lg font-semibold">Configure {configKey}</h3>
          <p className="text-xs text-slate-500">
            Current source:{" "}
            <span className="font-mono text-slate-300">
              {currentStatus?.source ?? "unconfigured"}
            </span>
            {currentStatus?.lastUpdatedAt ? (
              <>
                {" · last set "}
                <span className="font-mono text-slate-300">
                  {new Date(currentStatus.lastUpdatedAt).toLocaleString()}
                </span>
              </>
            ) : null}
          </p>
        </header>
        <p className="text-xs text-slate-400">
          Stored encrypted in the database (Fernet / APP_ENCRYPTION_KEY).
          Read order: DB &gt; environment variable &gt; unconfigured.
          Saving a new value invalidates the 60s cache so the next provider
          call sees it immediately. "Test" probes the actual upstream
          provider with the value below — does not persist anything.
        </p>
        <label className="block text-sm">
          <span className="text-slate-300">New value</span>
          <input
            className="input mt-1 w-full"
            type="password"
            placeholder="paste value…"
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
            test: {testResult.detail}
          </p>
        ) : null}
        {saveMutation.error ? (
          <p className="text-xs text-red-300">
            save: {(saveMutation.error as ApiError).message}
          </p>
        ) : null}
        {deleteMutation.error ? (
          <p className="text-xs text-red-300">
            unset: {(deleteMutation.error as ApiError).message}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!value || saveMutation.isPending}
            onClick={() => saveMutation.mutate(value)}
          >
            {saveMutation.isPending ? "Saving…" : "Save"}
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
            {testMutation.isPending ? "Testing…" : "Save & test"}
          </button>
          {currentStatus?.source === "db" ? (
            <button
              type="button"
              className="btn"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? "Unsetting…" : "Unset (fall back to env)"}
            </button>
          ) : null}
          <button type="button" className="btn ml-auto" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function UsersSection() {
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
    const pwd = window.prompt("New password (min 8 chars):");
    if (!pwd || pwd.length < 8) return;
    const alsoMfa = window.confirm(
      "Also reset MFA? Click OK to clear MFA secret, Cancel to keep MFA.",
    );
    resetPassword.mutate({ userId, newPassword: pwd, resetMfa: alsoMfa });
  }

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Users</h2>
      <form onSubmit={handleCreate} className="card mb-4 grid gap-3 sm:grid-cols-4">
        <input
          className="input sm:col-span-2"
          type="email"
          placeholder="email"
          required
          value={newEmail}
          onChange={(event) => setNewEmail(event.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="password (min 8)"
          required
          minLength={8}
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={newIsAdmin}
            onChange={(event) => setNewIsAdmin(event.target.checked)}
          />
          Admin
        </label>
        <div className="sm:col-span-4 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={createUser.isPending}>
            {createUser.isPending ? "Creating…" : "Create user"}
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
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">Email</th>
              <th className="px-3 py-2 text-left">Role</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">MFA</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {(usersQuery.data ?? []).map((u) => (
              <tr key={u.id}>
                <td className="px-3 py-2 tabular-nums">{u.id}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{u.is_admin ? "Admin" : "Member"}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      u.is_active
                        ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
                        : "border-red-700/50 bg-red-900/30 text-red-200"
                    }`}
                  >
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-3 py-2">{u.mfa_enabled ? "On" : "Off"}</td>
                <td className="px-3 py-2 text-right space-x-2">
                  <button
                    type="button"
                    className="btn"
                    disabled={resetMfa.isPending || !u.mfa_enabled}
                    onClick={() => resetMfa.mutate(u.id)}
                  >
                    Reset MFA
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => handleResetPassword(u.id)}
                  >
                    Set password
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() =>
                      setStatus.mutate({ userId: u.id, active: !u.is_active })
                    }
                    disabled={setStatus.isPending}
                  >
                    {u.is_active ? "Deactivate" : "Activate"}
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
      window.alert(`Download failed: ${response.status}`);
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
      <h2 className="mb-3 text-lg font-semibold">Backups</h2>
      <div className="card mb-4 flex items-center gap-3">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => createBackup.mutate()}
          disabled={createBackup.isPending}
        >
          {createBackup.isPending ? "Creating…" : "Create manual backup"}
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
              Download
            </button>
          </li>
        ))}
        {backupsQuery.data && backups.length === 0 ? (
          <p className="text-sm text-slate-500">No backups yet.</p>
        ) : null}
      </ul>
    </section>
  );
}

function ExportSection() {
  async function handleExport() {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    const response = await fetch("/api/admin/export", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      window.alert(`Export failed: ${response.status}`);
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
      <h2 className="mb-3 text-lg font-semibold">Export</h2>
      <div className="card flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-400">
          Streams the full snapshot (users, watchlists, alert rules, alert
          events, push subs) as JSON.
        </p>
        <button type="button" className="btn btn-primary" onClick={handleExport}>
          Download platform export
        </button>
      </div>
    </section>
  );
}
