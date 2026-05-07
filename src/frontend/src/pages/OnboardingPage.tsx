/**
 * Step-by-step setup wizard.
 *
 * Reuses the same forms users see in `SettingsPage` so there is one source of
 * truth for each input shape. Each step links into the relevant Settings
 * section via in-page anchors so the user can also jump there directly later
 * to revise. After every required step is complete the wizard offers a
 * "Continue to dashboard" CTA.
 */
import { Link } from "react-router-dom";
import { useState } from "react";

import { useOnboarding, type OnboardingStep } from "../auth/useOnboarding";

const STEP_ORDER: OnboardingStep["id"][] = ["mfa", "alpaca", "trading", "taxes"];

export function OnboardingPage() {
  const { steps, completedCount, total, allRequiredDone, isLoading } = useOnboarding();
  const [stepIndex, setStepIndex] = useState(0);

  if (isLoading) {
    return <p className="text-sm text-slate-400">Loading onboarding state…</p>;
  }

  const orderedSteps = STEP_ORDER.map((id) => steps.find((s) => s.id === id)!).filter(
    Boolean,
  );
  const current = orderedSteps[stepIndex];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Welcome — let's get set up</h1>
        <p className="text-sm text-slate-400">
          We'll walk through the inputs that drive every buy / sell signal:
          fundamentals, news, market trend, technical analysis, AI — combined
          into a probability-weighted recommendation that only fires when the
          NET return (after fees and capital-gains tax) clears your minimum.
        </p>
      </header>

      <ProgressIndicator completed={completedCount} total={total} />

      <ol className="grid gap-2 sm:grid-cols-4">
        {orderedSteps.map((s, idx) => (
          <li
            key={s.id}
            className={`rounded-lg border p-3 text-sm cursor-pointer transition ${
              idx === stepIndex
                ? "border-bergt-green/50 bg-bergt-green/5"
                : s.completed
                ? "border-bergt-green/20 bg-slate-900/40 text-slate-300"
                : "border-slate-700 bg-slate-900/40 text-slate-300"
            }`}
            onClick={() => setStepIndex(idx)}
          >
            <p className="text-xs uppercase tracking-wide opacity-60">
              Step {idx + 1}
              {s.required ? " · Required" : " · Optional"}
            </p>
            <p className="mt-0.5 font-medium">
              {s.completed ? "✓ " : ""}
              {s.label}
            </p>
          </li>
        ))}
      </ol>

      {current ? <StepDetail step={current} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          className="btn"
          disabled={stepIndex === 0}
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
        >
          Back
        </button>
        {stepIndex < orderedSteps.length - 1 ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setStepIndex((i) => Math.min(orderedSteps.length - 1, i + 1))}
          >
            Next
          </button>
        ) : (
          <Link
            to="/"
            className={`btn btn-primary ${
              allRequiredDone ? "" : "opacity-60 hover:opacity-80"
            }`}
          >
            {allRequiredDone ? "Continue to dashboard" : "Skip for now"}
          </Link>
        )}
      </div>

      <p className="text-xs text-slate-500">
        You can revisit and change every value later under{" "}
        <Link to="/settings" className="text-bergt-green hover:underline">
          Settings
        </Link>
        . The dashboard shows your remaining steps so you can finish at any
        time.
      </p>
    </div>
  );
}

function ProgressIndicator({
  completed,
  total,
}: {
  completed: number;
  total: number;
}) {
  const pct = total === 0 ? 0 : (completed / total) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-300">
          Setup progress: {completed} / {total}
        </span>
        <span className="text-slate-500">{pct.toFixed(0)}%</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-bergt-green/70 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StepDetail({ step }: { step: OnboardingStep }) {
  const target = step.id === "mfa" ? "/settings#mfa" : "/settings";
  return (
    <article className="card">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {step.completed ? "✓ " : ""}
            {step.label}
          </h2>
          <p className="text-sm text-slate-400">{step.description}</p>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs ${
            step.completed
              ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
              : "border-amber-700/40 bg-amber-900/20 text-amber-200"
          }`}
        >
          {step.completed ? "Configured" : step.required ? "Required" : "Optional"}
        </span>
      </header>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <Link to={target} className="btn btn-primary">
          {step.cta}
        </Link>
        {step.completed ? (
          <span className="text-xs text-slate-500">
            You can revise this in Settings later.
          </span>
        ) : null}
      </div>
    </article>
  );
}
