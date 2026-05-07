import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { LanguageToggle } from "../components/LanguageToggle";

type LocationState = { from?: { pathname?: string } };

export function LoginPage() {
  const { t } = useTranslation();
  const { user, login, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return null;
  }
  if (user) {
    const redirectTo =
      (location.state as LocationState | null)?.from?.pathname ?? "/";
    return <Navigate to={redirectTo} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password, mfaCode || undefined);
      if (result.mfaRequired) {
        setMfaRequired(true);
      } else {
        navigate("/", { replace: true });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(t("auth.loginFailed"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <form
        onSubmit={handleSubmit}
        className="card w-full max-w-sm space-y-4"
        aria-label="login form"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">{t("auth.loginTitle")}</h1>
            <p className="text-sm text-slate-400">{t("auth.loginSubtitle")}</p>
          </div>
          <LanguageToggle compact />
        </div>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("auth.email")}</span>
          <input
            type="email"
            autoComplete="email"
            required
            className="input"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("auth.password")}</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            className="input"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {mfaRequired ? (
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">{t("auth.mfaCode")}</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              autoComplete="one-time-code"
              required
              className="input"
              value={mfaCode}
              onChange={(event) => setMfaCode(event.target.value)}
            />
          </label>
        ) : null}
        {error ? (
          <p className="rounded-md border border-red-700/50 bg-red-950/40 p-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
        <button type="submit" className="btn btn-primary w-full" disabled={submitting}>
          {submitting ? t("auth.signingIn") : t("auth.signIn")}
        </button>
        <p className="text-center text-sm text-slate-400">
          {t("auth.noAccount")}{" "}
          <Link to="/register" className="text-bergt-green hover:underline">
            {t("auth.register")}
          </Link>{" "}
          ·{" "}
          <Link to="/forgot-password" className="text-bergt-green hover:underline">
            {t("auth.forgotPassword")}
          </Link>
        </p>
      </form>
    </div>
  );
}
