<!-- page: /settings -->
# Settings

Personal account configuration. The values here drive every recommendation and every paper-trading fill.

## Sections

- **Profile** — read-only summary of your email, role, and onboarding status.
- **Alpaca broker** — API key, secret key, paper / live toggle. Required before the broker-backed surfaces (account view, positions, real orders later) work.
- **Portfolio defaults** — broker fee model and minimum net yield:
  - **trade_fee_absolute** — flat per-leg fee in account currency
  - **trade_fee_percent** — percent fee applied to gross notional per leg
  - **min_target_yield** — minimum NET return percent (after fees and capital-gains tax) for a recommendation to count as actionable
  - **capital_gains_tax_bps** — Abgeltungssteuer / capital-gains rate in basis points (e.g. 26375 = 26.375%)
  - **income_tax_bps** — fallback income-tax rate for jurisdictions that tax short-term gains as ordinary income
- **Multi-factor authentication** — three-step lifecycle: setup (generates a secret + provisioning URI), enable (verifies a code from your authenticator), disable (also requires a current code).

## Where the values are used

- The minimum yield is the gate the recommendation card and the paper-trading order acceptance both check.
- The fee model is applied to every paper-trading fill.
- The tax rate is applied to realized profit only.
- Alpaca keys are encrypted at rest with `APP_ENCRYPTION_KEY` and never returned in cleartext.

## Audit trail

Every change to Alpaca config or portfolio defaults creates an `audit_events` row visible to admins under [Admin → Audit](/admin). Identifying values are stored as fingerprints, not plaintext.
