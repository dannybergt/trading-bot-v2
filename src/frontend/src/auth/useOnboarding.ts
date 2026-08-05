/**
 * Derive onboarding completion state from the existing /api/auth/me +
 * /api/auth/me/alpaca + /api/auth/me/portfolio-settings endpoints.
 *
 * Lives outside the component tree so any page (Dashboard card, Wizard page,
 * post-register redirect) can read the same state without prop drilling.
 *
 * The product directive is to ask the user for every setting that materially
 * affects buy/sell decisions on first login, and to surface progress on the
 * dashboard so the user always has an entry point back into the missing
 * pieces.
 */
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../api/client";

export type OnboardingStep = {
  id: "mfa" | "alpaca" | "trading" | "taxes";
  label: string;
  description: string;
  completed: boolean;
  required: boolean;
  cta: string;
};

type Me = {
  id: number;
  email: string;
  is_admin: boolean;
  mfa_enabled: boolean;
};

type AlpacaConfig = {
  api_key: string | null;
  secret_key_masked: string | null;
  is_paper: boolean;
};

type PortfolioSettings = {
  trade_fee_absolute: number;
  trade_fee_percent: number;
  min_target_yield: number;
  capital_gains_tax_bps: number;
  income_tax_bps: number;
};

export function useOnboarding() {
  const meQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: () => apiFetch<Me>("/api/auth/me"),
  });
  const alpacaQuery = useQuery({
    queryKey: ["alpaca-config"],
    queryFn: () => apiFetch<AlpacaConfig>("/api/auth/me/alpaca"),
  });
  const portfolioQuery = useQuery({
    queryKey: ["portfolio-settings"],
    queryFn: () => apiFetch<PortfolioSettings>("/api/auth/me/portfolio-settings"),
  });

  const isLoading =
    meQuery.isLoading || alpacaQuery.isLoading || portfolioQuery.isLoading;

  const me = meQuery.data;
  const alpaca = alpacaQuery.data;
  const portfolio = portfolioQuery.data;

  const steps: OnboardingStep[] = [
    {
      id: "mfa",
      label: "Two-factor authentication",
      description:
        "Protects the account that holds broker credentials and trading actions.",
      completed: !!me?.mfa_enabled,
      required: false,
      cta: me?.mfa_enabled ? "Configured" : "Set up MFA",
    },
    {
      id: "alpaca",
      // Bewusst optional (ADR 2026-08-05): die Zugangsdaten werden heute nur
      // fuer Quotes/Bars im Hintergrund genutzt. Es gibt noch keine Seite, die
      // Depot, Positionen oder echte Orders zeigt — ein Pflichtschritt ohne
      // sichtbare Gegenleistung. Sobald die Portfolio-Seite steht, wird der
      // Schritt wieder required.
      label: "Broker (Alpaca)",
      description:
        "Optional today: the keys feed background quotes. Portfolio and live execution land in a later wave.",
      completed: !!alpaca?.api_key,
      required: false,
      cta: alpaca?.api_key ? "Configured" : "Connect Alpaca",
    },
    {
      id: "trading",
      label: "Trading defaults",
      description:
        "Broker fees and your minimum net yield drive every recommendation.",
      completed:
        !!portfolio &&
        portfolio.min_target_yield > 0 &&
        (portfolio.trade_fee_absolute > 0 || portfolio.trade_fee_percent > 0),
      required: true,
      cta: "Set fees and minimum yield",
    },
    {
      id: "taxes",
      label: "Capital-gains tax",
      description:
        "Subtracted from projected gains so recommendations only fire when the NET return clears your minimum.",
      completed: !!portfolio && portfolio.capital_gains_tax_bps > 0,
      required: true,
      cta: "Set tax rate",
    },
  ];

  // Der Fortschritt zaehlt die **Pflicht**schritte, nicht alle.
  //
  // Befund des Verifikationslaufs vom 2026-08-06: die Karte zeigte
  // "1 / 4 konfiguriert" und verschwand, sobald die zwei Pflichtwerte gesetzt
  // waren — bei "2 / 4". Zahl und Verschwinden zaehlten also Verschiedenes,
  // und zwei Darstellungen derselben Tatsache widersprachen sich. Das ist
  // genau der Fall, den Regel K ausschliesst (TBV2-Z07), im Gewand einer
  // Fortschrittsanzeige. Optionale Schritte bleiben im Wizard sichtbar und
  // werden unter `optionalOpenCount` getrennt ausgewiesen, statt in eine Zahl
  // zu wandern, die etwas anderes bedeutet.
  const requiredSteps = steps.filter((s) => s.required);
  const completedCount = requiredSteps.filter((s) => s.completed).length;
  const total = requiredSteps.length;
  const requiredOpenCount = total - completedCount;
  const allRequiredDone = requiredOpenCount === 0;
  const optionalOpenCount = steps.filter((s) => !s.required && !s.completed).length;

  return {
    isLoading,
    steps,
    completedCount,
    total,
    optionalOpenCount,
    requiredOpenCount,
    allRequiredDone,
    // "Vollstaendig konfiguriert" heisst: alle Pflichtschritte sind erledigt —
    // und seit dem Verifikationsbefund vom 2026-08-06 zaehlt die Anzeige
    // daneben dieselben Schritte. Frueher stand hier completedCount === total
    // ueber alle vier Schritte, die Karte konnte damit nie verschwinden.
    isComplete: allRequiredDone,
  };
}
