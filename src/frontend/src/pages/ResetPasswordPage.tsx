import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const initialToken = params.get("token") ?? "";

  const [token, setToken] = useState(initialToken);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t("auth.passwordsMismatch"));
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/api/auth/password-reset/confirm", {
        method: "POST",
        body: { token, new_password: password },
        skipAuth: true,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.resetFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <form
        onSubmit={handleSubmit}
        className="card w-full max-w-sm space-y-4"
        aria-label="reset password form"
      >
        <div>
          <h1 className="text-xl font-semibold">{t("auth.resetTitle")}</h1>
          <p className="text-sm text-slate-400">
            {t("auth.resetSubtitle")}
          </p>
        </div>
        {done ? (
          <p className="rounded-md border border-bergt-green/40 bg-bergt-green/10 p-3 text-sm text-bergt-green">
            {t("auth.resetSuccess")}{" "}
            <Link to="/login" className="underline">
              {t("auth.signIn")}
            </Link>
          </p>
        ) : (
          <>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-300">{t("auth.resetToken")}</span>
              <input
                className="input"
                required
                value={token}
                onChange={(event) => setToken(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-300">{t("auth.newPassword")}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                className="input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-300">{t("auth.confirmPassword")}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                className="input"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
            </label>
            {error ? (
              <p className="rounded-md border border-red-700/50 bg-red-950/40 p-2 text-sm text-red-300">
                {error}
              </p>
            ) : null}
            <button type="submit" className="btn btn-primary w-full" disabled={busy}>
              {busy ? t("auth.resetting") : t("auth.resetSubmit")}
            </button>
          </>
        )}
        <p className="text-center text-sm text-slate-400">
          <Link to="/login" className="text-bergt-green hover:underline">
            {t("auth.backToLogin")}
          </Link>
        </p>
      </form>
    </div>
  );
}
