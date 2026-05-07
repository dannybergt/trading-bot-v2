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
      label: "Broker (Alpaca)",
      description:
        "Required for portfolio reads and (later) automated execution.",
      completed: !!alpaca?.api_key,
      required: true,
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

  const completedCount = steps.filter((s) => s.completed).length;
  const total = steps.length;
  const requiredOpenCount = steps.filter((s) => s.required && !s.completed).length;
  const allRequiredDone = requiredOpenCount === 0;

  return {
    isLoading,
    steps,
    completedCount,
    total,
    requiredOpenCount,
    allRequiredDone,
    isComplete: completedCount === total,
  };
}
