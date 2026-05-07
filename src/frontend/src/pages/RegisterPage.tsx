import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export function RegisterPage() {
  const { user, register, isLoading } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return null;
  }
  if (user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await register(email, password);
      // Send freshly-registered users straight into onboarding so the
      // required broker / fees / tax inputs are captured up front.
      navigate("/onboarding", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Registration failed. Try again.");
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
        aria-label="register form"
      >
        <div>
          <h1 className="text-xl font-semibold">Create account</h1>
          <p className="text-sm text-slate-400">
            First registered user becomes admin.
          </p>
        </div>
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
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">Password</span>
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
          <span className="mb-1 block text-slate-300">Confirm password</span>
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
        <button type="submit" className="btn btn-primary w-full" disabled={submitting}>
          {submitting ? "Creating..." : "Register"}
        </button>
        <p className="text-center text-sm text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="text-bergt-green hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
