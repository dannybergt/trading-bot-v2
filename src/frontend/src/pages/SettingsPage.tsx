import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useTranslation } from "react-i18next";

import { ApiError, apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useHashScroll } from "../hooks/useHashScroll";

type AlpacaConfig = {
  api_key: string;
  secret_key_masked: string;
  is_paper: boolean;
};

type PortfolioSettings = {
  trade_fee_absolute: number;
  trade_fee_percent: number;
  min_target_yield: number;
  capital_gains_tax_bps: number;
  income_tax_bps: number;
  display_currency: string;
};

const SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "CNY"] as const;

type MfaSetup = {
  secret: string;
  provisioning_uri: string;
  message: string;
};

export function SettingsPage() {
  const { t } = useTranslation();
  useHashScroll();
  const { user, refresh } = useAuth();

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>
        <p className="text-sm text-slate-400">
          {t("settings.subtitle")}
        </p>
      </header>

      <section className="card">
        <h2 className="text-lg font-semibold">{t("settings.profile.title")}</h2>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-400">{t("auth.email")}</dt>
          <dd>{user?.email}</dd>
          <dt className="text-slate-400">{t("settings.profile.role")}</dt>
          <dd>
            {user?.is_admin
              ? t("settings.profile.roleAdmin")
              : t("settings.profile.roleMember")}
          </dd>
          <dt className="text-slate-400">{t("settings.profile.mfa")}</dt>
          <dd>
            {user?.mfa_enabled
              ? t("settings.profile.enabled")
              : t("settings.profile.disabled")}
          </dd>
        </dl>
      </section>

      <AlpacaSection />
      <PortfolioSection />
      <MfaSection mfaEnabled={!!user?.mfa_enabled} onChange={refresh} />
    </div>
  );
}

function AlpacaSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["alpaca-config"],
    queryFn: () => apiFetch<AlpacaConfig>("/api/auth/me/alpaca"),
  });
  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [isPaper, setIsPaper] = useState(true);

  useEffect(() => {
    if (query.data) {
      setApiKey(query.data.api_key ?? "");
      setSecretKey(query.data.secret_key_masked ?? "");
      setIsPaper(!!query.data.is_paper);
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: (payload: { api_key: string; secret_key: string; is_paper: boolean }) =>
      apiFetch<AlpacaConfig>("/api/auth/me/alpaca", {
        method: "PUT",
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alpaca-config"] });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate({
      api_key: apiKey.trim(),
      // The masked string starts with "*" — backend skips updating in that case.
      secret_key: secretKey,
      is_paper: isPaper,
    });
  }

  return (
    <section className="card">
      <h2 className="text-lg font-semibold">{t("settings.alpaca.title")}</h2>
      <p className="text-sm text-slate-400">
        {t("settings.alpaca.subtitle")}
      </p>
      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.alpaca.apiKey")}</span>
          <input
            className="input"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="PK…"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.alpaca.secretKey")}</span>
          <input
            className="input"
            value={secretKey}
            onChange={(event) => setSecretKey(event.target.value)}
            placeholder={t("settings.alpaca.secretPlaceholder")}
          />
        </label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox"
            checked={isPaper}
            onChange={(event) => setIsPaper(event.target.checked)}
          />
          <span>{t("settings.alpaca.paperEndpoint")}</span>
        </label>
        <div className="sm:col-span-2 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? t("settings.saving") : t("settings.save")}
          </button>
          {mutation.error ? (
            <span className="text-sm text-red-300">
              {(mutation.error as ApiError).message}
            </span>
          ) : null}
          {mutation.isSuccess ? (
            <span className="text-sm text-bergt-green">{t("settings.saved")}</span>
          ) : null}
        </div>
      </form>
    </section>
  );
}

function PortfolioSection() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["portfolio-settings"],
    queryFn: () => apiFetch<PortfolioSettings>("/api/auth/me/portfolio-settings"),
  });
  const [feeAbsolute, setFeeAbsolute] = useState(0);
  const [feePercent, setFeePercent] = useState(0);
  const [minYield, setMinYield] = useState(0);
  const [capitalGainsPct, setCapitalGainsPct] = useState(0);
  const [incomeTaxPct, setIncomeTaxPct] = useState(0);
  const [displayCurrency, setDisplayCurrency] = useState("USD");

  useEffect(() => {
    if (query.data) {
      setFeeAbsolute(query.data.trade_fee_absolute);
      setFeePercent(query.data.trade_fee_percent);
      setMinYield(query.data.min_target_yield);
      setCapitalGainsPct((query.data.capital_gains_tax_bps ?? 0) / 100);
      setIncomeTaxPct((query.data.income_tax_bps ?? 0) / 100);
      setDisplayCurrency(query.data.display_currency || "USD");
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: (payload: PortfolioSettings) =>
      apiFetch<PortfolioSettings>("/api/auth/me/portfolio-settings", {
        method: "PUT",
        body: payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio-settings"] });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate({
      trade_fee_absolute: Number(feeAbsolute) || 0,
      trade_fee_percent: Number(feePercent) || 0,
      min_target_yield: Number(minYield) || 0,
      capital_gains_tax_bps: Math.round((Number(capitalGainsPct) || 0) * 100),
      income_tax_bps: Math.round((Number(incomeTaxPct) || 0) * 100),
      display_currency: displayCurrency,
    });
  }

  return (
    <section className="card">
      <h2 className="text-lg font-semibold">{t("settings.portfolio.title")}</h2>
      <p className="text-sm text-slate-400">
        {t("settings.portfolio.subtitle")}
      </p>
      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.portfolio.feeAbsolute")}</span>
          <input
            type="number"
            step="1"
            min="0"
            className="input"
            value={feeAbsolute}
            onChange={(event) => setFeeAbsolute(Number(event.target.value))}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.portfolio.feePercent")}</span>
          <input
            type="number"
            step="1"
            min="0"
            max="100"
            className="input"
            value={feePercent}
            onChange={(event) => setFeePercent(Number(event.target.value))}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.portfolio.minYield")}</span>
          <input
            type="number"
            step="1"
            min="0"
            className="input"
            value={minYield}
            onChange={(event) => setMinYield(Number(event.target.value))}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">
            {t("settings.portfolio.capitalGains")}
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            className="input"
            value={capitalGainsPct}
            onChange={(event) => setCapitalGainsPct(Number(event.target.value))}
            placeholder={t("settings.portfolio.capitalGainsPlaceholder")}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">
            {t("settings.portfolio.incomeTax")}
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            className="input"
            value={incomeTaxPct}
            onChange={(event) => setIncomeTaxPct(Number(event.target.value))}
            placeholder={t("settings.portfolio.incomeTaxPlaceholder")}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">{t("settings.portfolio.displayCurrency")}</span>
          <select
            className="input"
            value={displayCurrency}
            onChange={(event) => setDisplayCurrency(event.target.value)}
            data-testid="settings-display-currency"
          >
            {SUPPORTED_CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <div className="sm:col-span-3 text-xs text-slate-500">
          {t("settings.portfolio.taxHint")}
        </div>
        <div className="sm:col-span-3 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? t("settings.saving") : t("settings.save")}
          </button>
          {mutation.error ? (
            <span className="text-sm text-red-300">
              {(mutation.error as ApiError).message}
            </span>
          ) : null}
          {mutation.isSuccess ? (
            <span className="text-sm text-bergt-green">{t("settings.saved")}</span>
          ) : null}
        </div>
      </form>
    </section>
  );
}

function MfaSection({
  mfaEnabled,
  onChange,
}: {
  mfaEnabled: boolean;
  onChange: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSetup() {
    setError(null);
    setBusy(true);
    try {
      const data = await apiFetch<MfaSetup>("/api/auth/mfa/setup", { method: "POST" });
      setSetup(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.mfa.setupFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleEnable(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/api/auth/mfa/enable", { method: "POST", body: { code } });
      setSetup(null);
      setCode("");
      await onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.mfa.enableFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDisable(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/api/auth/mfa/disable", { method: "POST", body: { code } });
      setCode("");
      await onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settings.mfa.disableFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    // id: Sprungziel fuer "/settings#mfa" aus dem Onboarding-Wizard.
    <section className="card" id="mfa">
      <h2 className="text-lg font-semibold">{t("settings.mfa.title")}</h2>
      {mfaEnabled ? (
        <form onSubmit={handleDisable} className="mt-3 flex flex-wrap items-end gap-3">
          <p className="basis-full text-sm text-slate-400">
            {t("settings.mfa.enabledHint")}
          </p>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">{t("settings.mfa.currentCode")}</span>
            <input
              className="input"
              inputMode="numeric"
              pattern="[0-9]{6}"
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>
            {t("settings.mfa.disable")}
          </button>
          {error ? <span className="text-sm text-red-300">{error}</span> : null}
        </form>
      ) : setup ? (
        <form onSubmit={handleEnable} className="mt-3 space-y-3">
          <p className="text-sm text-slate-300">
            {t("settings.mfa.setupHint")}
          </p>
          <div className="rounded-md border border-slate-700 bg-slate-950/40 p-3 text-xs">
            <p className="text-slate-400">{t("settings.mfa.secret")}</p>
            <p className="font-mono break-all">{setup.secret}</p>
            <p className="mt-2 text-slate-400">{t("settings.mfa.provisioningUri")}</p>
            <p className="font-mono break-all">{setup.provisioning_uri}</p>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">{t("settings.mfa.confirmationCode")}</span>
            <input
              className="input"
              inputMode="numeric"
              pattern="[0-9]{6}"
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {t("settings.mfa.enable")}
          </button>
          {error ? <span className="ml-3 text-sm text-red-300">{error}</span> : null}
        </form>
      ) : (
        <div className="mt-3 flex items-center gap-3">
          <p className="text-sm text-slate-400">{t("settings.mfa.notEnabled")}</p>
          <button type="button" className="btn btn-primary" onClick={handleSetup} disabled={busy}>
            {t("settings.mfa.setup")}
          </button>
          {error ? <span className="text-sm text-red-300">{error}</span> : null}
        </div>
      )}
    </section>
  );
}
