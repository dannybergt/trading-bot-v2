import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ACCESS_TOKEN_KEY, ApiError, apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

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
      <UsersSection />
      <BackupsSection />
      <ExportSection />
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
    queryFn: () => apiFetch<BackupListItem[]>("/api/admin/backups"),
  });

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
        {(backupsQuery.data ?? []).map((backup) => (
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
        {backupsQuery.data && backupsQuery.data.length === 0 ? (
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
