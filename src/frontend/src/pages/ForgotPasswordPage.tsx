import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError, apiFetch } from "../api/client";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/api/auth/password-reset/request", {
        method: "POST",
        body: { email },
        skipAuth: true,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <form
        onSubmit={handleSubmit}
        className="card w-full max-w-sm space-y-4"
        aria-label="forgot password form"
      >
        <div>
          <h1 className="text-xl font-semibold">Forgot password</h1>
          <p className="text-sm text-slate-400">
            We email a reset link if the address has an account.
          </p>
        </div>
        {submitted ? (
          <p className="rounded-md border border-bergt-green/40 bg-bergt-green/10 p-3 text-sm text-bergt-green">
            If the email exists, reset instructions are on their way.
          </p>
        ) : (
          <>
            <label className="block text-sm">
              <span className="mb-1 block text-slate-300">Email</span>
              <input
                type="email"
                autoComplete="email"
                required
                className="input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            {error ? (
              <p className="rounded-md border border-red-700/50 bg-red-950/40 p-2 text-sm text-red-300">
                {error}
              </p>
            ) : null}
            <button type="submit" className="btn btn-primary w-full" disabled={busy}>
              {busy ? "Requesting…" : "Send reset link"}
            </button>
          </>
        )}
        <p className="text-center text-sm text-slate-400">
          <Link to="/login" className="text-bergt-green hover:underline">
            Back to login
          </Link>
        </p>
      </form>
    </div>
  );
}
