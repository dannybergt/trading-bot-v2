/**
 * "Warum wird hier nicht gehandelt?" — die Gate-Kette einzeln begruendet.
 *
 * `POST /api/auto-execution/proposals/evaluate` faehrt einen Trockenlauf durch
 * jedes Risiko-Gate und jeden Halt-Trigger und begruendet **jede** Ablehnung
 * einzeln. Der Endpunkt existierte, und keine Seite hat ihn je aufgerufen.
 *
 * Damit war der einzige Ort, an dem ein Nutzer nachvollziehen kann, warum die
 * Automatik nicht kauft, unerreichbar — ein direkter Widerspruch zu Punkt 6
 * der Produktvision ("Erklaerbarkeit ist Kern, nicht Beiwerk") und zur
 * Operationalisierung von TBV2-Z06 Lesart (d).
 *
 * Bewusst auf Knopfdruck statt automatisch: der Trockenlauf zieht live FRED,
 * FMP-SEC-Filings und Sektor-Kontext. Das ist nichts, was beim Oeffnen jeder
 * Analyse-Seite ungefragt passieren sollte.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";

type GateDecision = {
  allowed: boolean;
  reasons: string[];
  haltTriggers: string[];
  breakdown: Record<string, unknown>;
};

type Props = {
  symbol: string;
  assetClass?: string | null;
  limitPrice?: number | null;
  targetPrice?: number | null;
  side?: "buy" | "sell";
};

export function TradeGatePanel({
  symbol,
  assetClass,
  limitPrice,
  targetPrice,
  side = "buy",
}: Props) {
  const { t } = useTranslation();
  const [decision, setDecision] = useState<GateDecision | null>(null);

  const evaluate = useMutation({
    mutationFn: () =>
      apiFetch<GateDecision>("/api/auto-execution/proposals/evaluate", {
        method: "POST",
        body: {
          symbol,
          assetClass: assetClass ?? undefined,
          side,
          limitPrice: limitPrice ?? undefined,
          targetPrice: targetPrice ?? undefined,
        },
      }),
    onSuccess: setDecision,
  });

  const blocking = decision ? [...decision.reasons] : [];
  const halts = decision ? decision.haltTriggers : [];

  return (
    <section className="card" data-testid="trade-gate-panel">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          {t("analysis.gates.title")}
        </h2>
        <button
          type="button"
          className="btn"
          onClick={() => evaluate.mutate()}
          disabled={evaluate.isPending}
          data-testid="trade-gate-run"
        >
          {evaluate.isPending ? t("analysis.gates.running") : t("analysis.gates.run")}
        </button>
      </header>

      <p className="mt-1 text-xs text-slate-500">{t("analysis.gates.hint")}</p>

      {evaluate.error ? (
        <p className="mt-2 text-sm text-red-300">{(evaluate.error as ApiError).message}</p>
      ) : null}

      {decision ? (
        <div className="mt-3 space-y-2">
          <p
            className={`text-sm font-medium ${
              decision.allowed ? "text-bergt-green" : "text-amber-200"
            }`}
            data-testid="trade-gate-verdict"
          >
            {decision.allowed
              ? t("analysis.gates.allowed")
              : t("analysis.gates.blocked", { count: blocking.length })}
          </p>

          {blocking.length > 0 ? (
            <ul className="space-y-1 text-xs" data-testid="trade-gate-reasons">
              {blocking.map((reason) => (
                <li key={reason} className="flex gap-2">
                  <span aria-hidden="true" className="text-amber-300">
                    •
                  </span>
                  <span>
                    {/* Jeder Grund bekommt einen eigenen Satz. Faellt ein neuer
                        Code aus dem Backend durch, steht wenigstens der Code da
                        statt gar nichts. */}
                    {t(`analysis.gates.reason.${reason}`, { defaultValue: reason })}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {halts.length > 0 ? (
            <div className="rounded border border-red-700/40 bg-red-900/20 px-2 py-1">
              <p className="text-xs font-medium text-red-200">
                {t("analysis.gates.haltTitle")}
              </p>
              {/* Eigener Anker: ohne ihn war ein roh durchgereichter
                  Halt-Code am UI unbewacht (Verifikationsbefund 2026-08-06). */}
              <ul
                className="mt-1 space-y-1 text-xs text-red-200/90"
                data-testid="trade-gate-halts"
              >
                {halts.map((trigger) => (
                  <li key={trigger}>
                    {t(`analysis.gates.reason.${trigger}`, { defaultValue: trigger })}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {decision.allowed && blocking.length === 0 && halts.length === 0 ? (
            <p className="text-xs text-slate-400">{t("analysis.gates.allowedHint")}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
