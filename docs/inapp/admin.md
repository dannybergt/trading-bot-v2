<!-- page: /admin -->
# Administration

Admin-only surface. Visible to users with the `is_admin` flag.

## Sections

The page is available in German and English; it follows the language toggle in
the header like every other page.

- **Users** — list every account with role, status, and MFA flag. Actions: create new user, set password (recovery), reset MFA (when a user lost their authenticator), toggle active flag (ban/unban). Self-deactivation is blocked.
- **Data sources** — which providers feed the recommendation engine, whether each one is configured, and what the next paid tier would buy. Providers with an API key can be set here: the value is stored encrypted (Fernet / `APP_ENCRYPTION_KEY`), read order is database > environment variable > unconfigured, and a 60-second cache picks a new value up without a restart. "Save & test" probes the real upstream provider.
- **Composite decision weights** — relative weight of each source (technical/ML, analyst consensus, fundamentals, news sentiment) in the combined BUY/HOLD/SELL verdict, normalised to 100%. The calibration run only writes new weights when they beat the current hit-rate on the forward-collected samples.
- **Backups** — every snapshot the scheduled backup task or the manual "Create manual backup" button has produced. Download as JSON.
- **Export** — single-shot full database snapshot (every table, including `audit_events`). Used for migrations and disaster recovery.

The audit trail described below is written by the backend and covered by the
export, but it has **no** browser in this page — read it via
`GET /api/admin/audit-events`.

## Audit-action vocabulary

The `action` column follows `<resource>.<verb>`. Notable entries:

- `auth.login` / `auth.login_failed` — login attempts (failure rows include the reason: invalid_credentials / account_inactive / invalid_mfa)
- `auth.register`, `auth.password_reset_confirm`, `auth.mfa_enable`, `auth.mfa_disable`, `auth.mfa_reset`
- `settings.alpaca_update`, `settings.portfolio_update`
- `paper_order.place`, `paper_order.place_rejected`, `paper_order.cancel`
- `backup.create`, `backup.restore`, `backup.export`, `backup.import`
- `admin.user_create`, `admin.user_password_reset`, `admin.user_toggle_active`

## How the audit log persists

The audit trail lives in the same database as everything else and is covered by every snapshot. A failed audit write logs and continues — the audit trail must never block the request path it is annotating.
