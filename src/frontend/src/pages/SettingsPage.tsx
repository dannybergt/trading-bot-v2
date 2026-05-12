import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiFetch } from "../api/client";
import { useAuth } from "../auth/AuthContext";

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
  const { user, refresh } = useAuth();

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-400">
          Configure account, broker, portfolio defaults, and multi-factor
          authentication.
        </p>
      </header>

      <section className="card">
        <h2 className="text-lg font-semibold">Profile</h2>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-400">Email</dt>
          <dd>{user?.email}</dd>
          <dt className="text-slate-400">Role</dt>
          <dd>{user?.is_admin ? "Admin" : "Member"}</dd>
          <dt className="text-slate-400">MFA</dt>
          <dd>{user?.mfa_enabled ? "Enabled" : "Disabled"}</dd>
        </dl>
      </section>

      <AlpacaSection />
      <PortfolioSection />
      <MfaSection mfaEnabled={!!user?.mfa_enabled} onChange={refresh} />
    </div>
  );
}

function AlpacaSection() {
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
      <h2 className="text-lg font-semibold">Alpaca broker</h2>
      <p className="text-sm text-slate-400">
        Used for portfolio reads and (later) order placement. Secret key is
        encrypted at rest and never returned in plaintext after save.
      </p>
      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">API key</span>
          <input
            className="input"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="PK…"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">Secret key</span>
          <input
            className="input"
            value={secretKey}
            onChange={(event) => setSecretKey(event.target.value)}
            placeholder="enter to replace; *** keeps the existing one"
          />
        </label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox"
            checked={isPaper}
            onChange={(event) => setIsPaper(event.target.checked)}
          />
          <span>Paper-trading endpoint</span>
        </label>
        <div className="sm:col-span-2 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save"}
          </button>
          {mutation.error ? (
            <span className="text-sm text-red-300">
              {(mutation.error as ApiError).message}
            </span>
          ) : null}
          {mutation.isSuccess ? (
            <span className="text-sm text-bergt-green">Saved.</span>
          ) : null}
        </div>
      </form>
    </section>
  );
}

function PortfolioSection() {
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
      <h2 className="text-lg font-semibold">Portfolio defaults &amp; taxes</h2>
      <p className="text-sm text-slate-400">
        Used to project net yield. The system only flags a trade as
        actionable when the projected net return (after broker fees and
        capital-gains tax) clears your minimum.
      </p>
      <form onSubmit={handleSubmit} className="mt-4 grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">Fee absolute / trade</span>
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
          <span className="mb-1 block text-slate-300">Fee percent</span>
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
          <span className="mb-1 block text-slate-300">Min net yield (%)</span>
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
            Capital-gains tax (%)
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            className="input"
            value={capitalGainsPct}
            onChange={(event) => setCapitalGainsPct(Number(event.target.value))}
            placeholder="e.g. 26.375 (DE Abgeltungssteuer)"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">
            Income tax fallback (%)
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            className="input"
            value={incomeTaxPct}
            onChange={(event) => setIncomeTaxPct(Number(event.target.value))}
            placeholder="0 if not applicable"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-300">Display currency</span>
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
          Capital-gains rate dominates if both are set; income-tax fallback
          is only used when the broker treats short-term gains as ordinary
          income.
        </div>
        <div className="sm:col-span-3 flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save"}
          </button>
          {mutation.error ? (
            <span className="text-sm text-red-300">
              {(mutation.error as ApiError).message}
            </span>
          ) : null}
          {mutation.isSuccess ? (
            <span className="text-sm text-bergt-green">Saved.</span>
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
      setError(err instanceof ApiError ? err.message : "Setup failed.");
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
      setError(err instanceof ApiError ? err.message : "Enable failed.");
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
      setError(err instanceof ApiError ? err.message : "Disable failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2 className="text-lg font-semibold">Multi-factor authentication</h2>
      {mfaEnabled ? (
        <form onSubmit={handleDisable} className="mt-3 flex flex-wrap items-end gap-3">
          <p className="basis-full text-sm text-slate-400">
            MFA is enabled. Disabling requires a valid code.
          </p>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">Current code</span>
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
            Disable MFA
          </button>
          {error ? <span className="text-sm text-red-300">{error}</span> : null}
        </form>
      ) : setup ? (
        <form onSubmit={handleEnable} className="mt-3 space-y-3">
          <p className="text-sm text-slate-300">
            Add this account to your authenticator app, then enter a generated
            code to confirm.
          </p>
          <div className="rounded-md border border-slate-700 bg-slate-950/40 p-3 text-xs">
            <p className="text-slate-400">Secret</p>
            <p className="font-mono break-all">{setup.secret}</p>
            <p className="mt-2 text-slate-400">Provisioning URI</p>
            <p className="font-mono break-all">{setup.provisioning_uri}</p>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-300">Confirmation code</span>
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
            Enable MFA
          </button>
          {error ? <span className="ml-3 text-sm text-red-300">{error}</span> : null}
        </form>
      ) : (
        <div className="mt-3 flex items-center gap-3">
          <p className="text-sm text-slate-400">MFA is not enabled.</p>
          <button type="button" className="btn btn-primary" onClick={handleSetup} disabled={busy}>
            Set up MFA
          </button>
          {error ? <span className="text-sm text-red-300">{error}</span> : null}
        </div>
      )}
    </section>
  );
}
