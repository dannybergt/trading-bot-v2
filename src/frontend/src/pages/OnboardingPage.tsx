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
import { Trans, useTranslation } from "react-i18next";

import { useOnboarding, type OnboardingStep } from "../auth/useOnboarding";

const STEP_ORDER: OnboardingStep["id"][] = ["mfa", "alpaca", "trading", "taxes"];

export function OnboardingPage() {
  const { t } = useTranslation();
  const { steps, completedCount, total, allRequiredDone, isLoading } = useOnboarding();
  const [stepIndex, setStepIndex] = useState(0);

  if (isLoading) {
    return <p className="text-sm text-slate-400">{t("app.loading")}</p>;
  }

  const orderedSteps = STEP_ORDER.map((id) => steps.find((s) => s.id === id)!).filter(
    Boolean,
  );
  const current = orderedSteps[stepIndex];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("onboarding.headline")}</h1>
        <p className="text-sm text-slate-400">{t("onboarding.intro")}</p>
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
              {t("onboarding.step", { index: idx + 1 })}
              {s.required ? ` · ${t("onboarding.required")}` : ` · ${t("onboarding.optional")}`}
            </p>
            <p className="mt-0.5 font-medium">
              {s.completed ? "✓ " : ""}
              {translateStepLabel(t, s.id) ?? s.label}
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
          {t("app.back")}
        </button>
        {stepIndex < orderedSteps.length - 1 ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setStepIndex((i) => Math.min(orderedSteps.length - 1, i + 1))}
          >
            {t("app.next")}
          </button>
        ) : (
          <Link
            to="/"
            className={`btn btn-primary ${
              allRequiredDone ? "" : "opacity-60 hover:opacity-80"
            }`}
          >
            {allRequiredDone
              ? t("onboarding.continueDashboard")
              : t("onboarding.skip")}
          </Link>
        )}
      </div>

      <p className="text-xs text-slate-500">
        <Trans
          i18nKey="onboarding.revisitHint"
          values={{ settingsLink: "" }}
          components={{
            // eslint-disable-next-line jsx-a11y/anchor-has-content
            a: <Link to="/settings" className="text-bergt-green hover:underline" />,
          }}
        >
          You can revisit and change every value later under{" "}
          <Link to="/settings" className="text-bergt-green hover:underline">
            Settings
          </Link>
          . The dashboard shows your remaining steps so you can finish at any
          time.
        </Trans>
      </p>
    </div>
  );
}

function translateStepLabel(
  t: ReturnType<typeof useTranslation>["t"],
  id: OnboardingStep["id"],
): string | null {
  const key = `onboarding.steps.${id}.label`;
  const translated = t(key);
  return translated && translated !== key ? translated : null;
}

function ProgressIndicator({
  completed,
  total,
}: {
  completed: number;
  total: number;
}) {
  const { t } = useTranslation();
  const pct = total === 0 ? 0 : (completed / total) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-300">
          {t("dashboard.onboarding.title")}: {t("dashboard.onboarding.configured", {
            completed,
            total,
          })}
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
  const { t } = useTranslation();
  const target = step.id === "mfa" ? "/settings#mfa" : "/settings";
  const labelKey = `onboarding.steps.${step.id}.label`;
  const descKey = `onboarding.steps.${step.id}.description`;
  const ctaKey = step.completed
    ? `onboarding.steps.${step.id}.ctaConfigured`
    : `onboarding.steps.${step.id}.ctaOpen`;
  const fallbackCtaKey = `onboarding.steps.${step.id}.cta`;
  const translatedLabel = t(labelKey);
  const translatedDesc = t(descKey);
  const translatedCta = t(ctaKey);
  const ctaText =
    translatedCta && translatedCta !== ctaKey
      ? translatedCta
      : (() => {
          const fallback = t(fallbackCtaKey);
          return fallback && fallback !== fallbackCtaKey ? fallback : step.cta;
        })();
  return (
    <article className="card">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {step.completed ? "✓ " : ""}
            {translatedLabel && translatedLabel !== labelKey ? translatedLabel : step.label}
          </h2>
          <p className="text-sm text-slate-400">
            {translatedDesc && translatedDesc !== descKey ? translatedDesc : step.description}
          </p>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs ${
            step.completed
              ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
              : "border-amber-700/40 bg-amber-900/20 text-amber-200"
          }`}
        >
          {step.completed
            ? t("onboarding.configured")
            : step.required
            ? t("onboarding.required")
            : t("onboarding.optional")}
        </span>
      </header>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <Link to={target} className="btn btn-primary">
          {ctaText}
        </Link>
      </div>
    </article>
  );
}
