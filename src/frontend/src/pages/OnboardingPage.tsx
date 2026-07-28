/**
 * Guided first run.
 *
 * The user walks the whole decision process once -- basics, find a symbol, read
 * the analysis, watch it, get alerted, trade it on paper -- performing every
 * step in the REAL application rather than in a simulation. Progress comes from
 * real artifacts (see `onboarding/tourState.ts`); nothing here marks itself done
 * because a link was clicked.
 *
 * The configuration checklist (MFA, Alpaca, fees, taxes) is not replaced: it is
 * the first step, rendered inline with the same cards `SettingsPage` uses, so
 * there is still one source of truth per input.
 *
 * Deliberately excluded from the run: switching Auto-Execution on. The last step
 * explains it and links to it, but a guided tour must not be the thing that arms
 * automated trading -- that stays an explicit, separate decision.
 */
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { useOnboarding, type OnboardingStep } from "../auth/useOnboarding";
import { useGuidedTour, type TourStep } from "../onboarding/useGuidedTour";

const CONFIG_STEP_ORDER: OnboardingStep["id"][] = ["mfa", "alpaca", "trading", "taxes"];

export function OnboardingPage() {
  const { t } = useTranslation();
  const tour = useGuidedTour();
  const [stepIndex, setStepIndex] = useState(0);

  // Follow the user forward to the first unfinished step when they come back
  // from doing something, but never drag them backwards while they are reading.
  useEffect(() => {
    if (!tour.started || tour.isLoading) return;
    const firstOpen = tour.steps.findIndex((step) => !step.completed);
    if (firstOpen > stepIndex) setStepIndex(firstOpen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tour.started, tour.isLoading, tour.completedCount]);

  if (tour.isLoading) {
    return <p className="text-sm text-slate-400">{t("app.loading")}</p>;
  }

  if (!tour.started) {
    return <TourIntro onStart={tour.start} />;
  }

  const current = tour.steps[Math.min(stepIndex, tour.steps.length - 1)];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t("tour.headline")}</h1>
          <p className="text-sm text-slate-400">{t("tour.intro")}</p>
        </div>
        <button type="button" className="btn text-xs" onClick={tour.restart}>
          {t("tour.restart")}
        </button>
      </header>

      <ProgressIndicator completed={tour.completedCount} total={tour.total} />

      <ol className="grid gap-2 sm:grid-cols-4 lg:grid-cols-7" data-testid="tour-steps">
        {tour.steps.map((step, idx) => (
          <li key={step.id}>
            <button
              type="button"
              onClick={() => setStepIndex(idx)}
              className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                idx === stepIndex
                  ? "border-bergt-green/50 bg-bergt-green/5"
                  : step.completed
                  ? "border-bergt-green/20 bg-slate-900/40 text-slate-300"
                  : "border-slate-700 bg-slate-900/40 text-slate-300"
              }`}
              aria-current={idx === stepIndex ? "step" : undefined}
            >
              <p className="text-xs uppercase tracking-wide opacity-60">
                {t("tour.stepOf", { index: idx + 1, total: tour.total })}
              </p>
              <p className="mt-0.5 font-medium">
                {step.completed ? "✓ " : ""}
                {t(`tour.steps.${step.id}.label`)}
              </p>
            </button>
          </li>
        ))}
      </ol>

      <TourStepDetail step={current} onFinish={tour.finish} finished={tour.finished} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          className="btn"
          disabled={stepIndex === 0}
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
        >
          {t("app.back")}
        </button>
        {stepIndex < tour.steps.length - 1 ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setStepIndex((i) => Math.min(tour.steps.length - 1, i + 1))}
          >
            {t("app.next")}
          </button>
        ) : (
          <Link to="/" className="btn btn-primary">
            {t("onboarding.continueDashboard")}
          </Link>
        )}
      </div>

      <p className="text-xs text-slate-500">
        <Trans
          i18nKey="onboarding.revisitHint"
          components={{
            // eslint-disable-next-line jsx-a11y/anchor-has-content
            a: <Link to="/settings" className="text-bergt-green hover:underline" />,
          }}
        />
      </p>
    </div>
  );
}

function TourIntro({ onStart }: { onStart: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("tour.headline")}</h1>
        <p className="text-sm text-slate-400">{t("tour.intro")}</p>
      </header>
      <article className="card space-y-3">
        <h2 className="text-lg font-semibold">{t("tour.whatYouWillDo")}</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-300">
          {(["basics", "findSymbol", "readAnalysis", "watchlist", "alert", "paperTrade", "autoExecution"] as const).map(
            (id) => (
              <li key={id}>{t(`tour.steps.${id}.label`)}</li>
            ),
          )}
        </ol>
        <p className="text-sm text-slate-400">{t("tour.noRealMoney")}</p>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onStart}
            data-testid="tour-start"
          >
            {t("tour.start")}
          </button>
        </div>
      </article>
    </div>
  );
}

function TourStepDetail({
  step,
  onFinish,
  finished,
}: {
  step: TourStep;
  onFinish: () => void;
  finished: boolean;
}) {
  const { t } = useTranslation();
  const onboarding = useOnboarding();

  return (
    <article className="card space-y-4" data-testid={`tour-step-${step.id}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {step.completed ? "✓ " : ""}
            {t(`tour.steps.${step.id}.label`)}
          </h2>
          <p className="text-sm text-slate-400">{t(`tour.steps.${step.id}.description`)}</p>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-xs ${
            step.completed
              ? "border-bergt-green/40 bg-bergt-green/10 text-bergt-green"
              : "border-amber-700/40 bg-amber-900/20 text-amber-200"
          }`}
        >
          {step.completed ? t("tour.done") : t("tour.open")}
        </span>
      </header>

      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
        {(t(`tour.steps.${step.id}.watchFor`, { returnObjects: true }) as unknown as string[]).map(
          (line, idx) => (
            <li key={idx}>{line}</li>
          ),
        )}
      </ul>

      {/* Say out loud what makes this step count. A progress bar the user
          cannot audit is worse than none. */}
      <p className="text-xs text-slate-500">{t(`tour.evidence.${step.evidence}`)}</p>

      {step.id === "basics" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {CONFIG_STEP_ORDER.map((id) => {
            const configStep = onboarding.steps.find((entry) => entry.id === id);
            if (!configStep) return null;
            return <ConfigCard key={id} step={configStep} />;
          })}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {step.target ? (
          <Link to={step.target} className="btn btn-primary" data-testid="tour-cta">
            {t(`tour.steps.${step.id}.cta`)}
          </Link>
        ) : null}
        {step.id === "autoExecution" ? (
          <>
            <Link to="/auto-execution" className="btn">
              {t("tour.steps.autoExecution.cta")}
            </Link>
            <button
              type="button"
              className="btn btn-primary"
              onClick={onFinish}
              disabled={finished}
              data-testid="tour-finish"
            >
              {finished ? t("tour.finished") : t("tour.finish")}
            </button>
          </>
        ) : null}
      </div>
    </article>
  );
}

function ConfigCard({ step }: { step: OnboardingStep }) {
  const { t } = useTranslation();
  const target = step.id === "mfa" ? "/settings#mfa" : "/settings";
  const labelKey = `onboarding.steps.${step.id}.label`;
  const translatedLabel = t(labelKey);
  return (
    <Link
      to={target}
      className={`rounded-lg border p-3 text-sm transition hover:border-bergt-green/50 ${
        step.completed
          ? "border-bergt-green/20 bg-slate-900/40"
          : "border-slate-700 bg-slate-900/40"
      }`}
    >
      <p className="text-xs uppercase tracking-wide opacity-60">
        {step.required ? t("onboarding.required") : t("onboarding.optional")}
      </p>
      <p className="mt-0.5 font-medium">
        {step.completed ? "✓ " : ""}
        {translatedLabel && translatedLabel !== labelKey ? translatedLabel : step.label}
      </p>
    </Link>
  );
}

function ProgressIndicator({ completed, total }: { completed: number; total: number }) {
  const { t } = useTranslation();
  const pct = total === 0 ? 0 : (completed / total) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-300" data-testid="tour-progress">
          {t("tour.progress", { completed, total })}
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
